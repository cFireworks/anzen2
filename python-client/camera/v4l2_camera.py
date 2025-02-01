import os
import mmap
import fcntl
from .base import CameraBase
import v4l2
import ctypes, select
import numpy as np
import logging

class V4L2Camera(CameraBase):
    def __init__(self, device="/dev/video0", resolution=(640, 480), camera_fps=15, pixel_format=v4l2.V4L2_PIX_FMT_YUYV):
        self.device = device
        self.resolution = resolution
        self.pixel_format = pixel_format
        self.fps = 15
        self.fd = None
        self.mmapped = None
        self.buf = None
        self.stream_type = None

    def start_capture(self):
        """初始化视频采集设备"""
        # 打开设备
        self.fd = os.open(self.device, os.O_RDWR)
        
        # 配置摄像头格式
        v4l2_format = v4l2.v4l2_format()
        v4l2_format.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        v4l2_format.fmt.pix.width = self.resolution[0]
        v4l2_format.fmt.pix.height = self.resolution[1]
        v4l2_format.fmt.pix.pixelformat = self.pixel_format
        fcntl.ioctl(self.fd, v4l2.VIDIOC_S_FMT, v4l2_format)

        # 请求4个缓冲区
        reqbuf = v4l2.v4l2_requestbuffers()
        reqbuf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        reqbuf.memory = v4l2.V4L2_MEMORY_MMAP
        reqbuf.count = 8  # 使用4个缓冲区
        fcntl.ioctl(self.fd, v4l2.VIDIOC_REQBUFS, reqbuf)
        logging.debug(f"已分配 {reqbuf.count} 个缓冲区")

        # 初始化所有缓冲区并存入列表
        self.buffers = []
        for i in range(reqbuf.count):
            # 查询缓冲区
            buf = v4l2.v4l2_buffer()
            buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
            buf.memory = v4l2.V4L2_MEMORY_MMAP
            buf.index = i
            fcntl.ioctl(self.fd, v4l2.VIDIOC_QUERYBUF, buf)
            # 内存映射缓冲区
            mmapped = mmap.mmap(self.fd, buf.length, offset=buf.m.offset)
            self.buffers.append((buf, mmapped))  # 存储缓冲区对象和内存映射
            # 将缓冲区队列入队
            fcntl.ioctl(self.fd, v4l2.VIDIOC_QBUF, buf)  # 初始入队

        # 启动视频流
        self.stream_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
        fcntl.ioctl(self.fd, v4l2.VIDIOC_STREAMON, self.stream_type)

    def read_frame(self):
        """读取一帧视频数据并返回RGBA格式的numpy数组"""
        # 等待缓冲区可用
        poll = select.poll()
        poll.register(self.fd, select.POLLIN)
        if not poll.poll(3000):  # 增加超时判断
            raise TimeoutError("等待视频帧超时")

        # 动态获取已填充的缓冲区索引
        buf = v4l2.v4l2_buffer()
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP
        try:
            fcntl.ioctl(self.fd, v4l2.VIDIOC_DQBUF, buf)
            logging.debug(f"DQBUF成功: buffers[{buf.index}]")
        except IOError as e:
            logging.error(f"DQBUF失败: {e}")
            raise
        
        # 校验数据有效性
        if buf.bytesused <= 0:
            logging.warning("无效帧数据(bytesused=0)，跳过")
            fcntl.ioctl(self.fd, v4l2.VIDIOC_QBUF, buf)  # 立即重新入队
            return None  # 返回空或抛异常
        
        # 根据索引获取对应的内存映射区域
        _, target_mmap = self.buffers[buf.index]
        target_mmap.seek(0)  # 关键修复：重置指针
        frame_data = target_mmap.read(buf.bytesused)
        
        # 将视频帧数据转换为numpy数组并进行像素格式转换
        frame = np.frombuffer(frame_data, dtype=np.uint8).reshape(self.resolution[1], self.resolution[0]*2)
        rgba_frame = self._yuyv_to_rgba(frame)
        
        # 重新入队缓冲区
        try:
            fcntl.ioctl(self.fd, v4l2.VIDIOC_QBUF, buf)
        except IOError as e:
            logging.error(f"QBUF失败: {e}")
            raise
        
        return rgba_frame

    def stop_capture(self):
        """释放采集资源"""
        # 停止视频流
        fcntl.ioctl(self.fd, v4l2.VIDIOC_STREAMOFF, self.stream_type)

        # 关闭文件描述符
        os.close(self.fd)
    
    def _yuyv_to_rgba(self, yuyv_array: np.ndarray) -> np.ndarray:
        # 确保输入的数组是二维的（高度，宽度）
        if yuyv_array.ndim != 2:
            raise ValueError("输入的yuyv_array必须是二维数组")
        
        h, w = yuyv_array.shape
        # 计算每行中的四元组数目，每个四元组对应两个像素
        num_quads = w // 4
        if num_quads * 4 != w:
            raise ValueError("输入的yuyv_array宽度必须是4的倍数")
        
        # 将输入的数组重新调整为（高度，四元组数目，4）的形状
        yuyv_blocks = yuyv_array.reshape((h, num_quads, 4))
        
        # 提取Y分量（Y0和Y1）
        y_pairs = yuyv_blocks[:, :, [0, 2]]  # 形状为（h, num_quads, 2）
        y_plane = y_pairs.reshape((h, num_quads * 2))  # 合并成连续的Y值
        
        # 提取U和V分量，并每个重复两次以匹配像素数量
        u_plane = np.repeat(yuyv_blocks[:, :, 1], 2, axis=1)
        v_plane = np.repeat(yuyv_blocks[:, :, 3], 2, axis=1)
        
        # 转换为浮点数并进行YUV到RGB的转换
        y = y_plane.astype(np.float32)
        u = u_plane.astype(np.float32) - 128.0
        v = v_plane.astype(np.float32) - 128.0
        
        # 应用转换公式（基于BT.601标准）
        r = y + 1.403 * v
        g = y - 0.344 * u - 0.714 * v
        b = y + 1.773 * u
        
        # 将结果限制在0-255范围内，并转换为uint8类型
        r = np.clip(r, 0, 255).astype(np.uint8)
        g = np.clip(g, 0, 255).astype(np.uint8)
        b = np.clip(b, 0, 255).astype(np.uint8)
        a = np.full_like(r, 255, dtype=np.uint8)  # Alpha通道全为255
        
        # 合并RGBA通道
        rgba_array = np.stack((r, g, b, a), axis=-1)
        logging.debug(f"YUYV converted to RGBA: shape {rgba_array.shape}")
        return rgba_array