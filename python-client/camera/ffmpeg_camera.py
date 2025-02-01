import ffmpeg
import numpy as np
import logging
import platform
from .base import CameraBase


class FFmpegCamera(CameraBase):
    def __init__(self, device=0, resolution=(640, 480), camera_fps=15):
        self.device = device
        self.device_format, self.device_prefix = self._detect_device_format()
        self.resolution = resolution
        self.fps = camera_fps
        self.process = None

    def start_capture(self):
        """初始化视频采集设备，使用FFmpeg进行视频捕获"""
        self.process = (
            ffmpeg
            .input(f"{self.device_prefix}{self.device}", 
                   f=self.device_format, 
                   r=self.fps, 
                   s=f"{self.resolution[0]}x{self.resolution[1]}")
            .output('pipe:1', format='rawvideo', pix_fmt='bgr24')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

    def read_frame(self):
        """读取一帧视频数据并返回RGBA格式的numpy数组"""
        if not self.process:
            raise RuntimeError("Capture not started")
        
        # 从ffmpeg的stdout获取一帧数据
        in_bytes = self.process.stdout.read(self.resolution[0] * self.resolution[1] * 3)  # 每帧数据大小 (width * height * 3)

        if len(in_bytes) == 0:
            logging.error(self.process.stderr.read().decode())
            raise RuntimeError("Failed to capture frame")

        # 将原始字节数据转换为RGBA格式的numpy数组
        frame = np.frombuffer(in_bytes, np.uint8).reshape((self.resolution[1], self.resolution[0], 3))
        frame = self._bgr_to_rgba(frame)
        return frame

    def stop_capture(self):
        """释放采集资源"""
        if self.process:
            self.process.stdout.close()
            self.process.stderr.close()
            self.process.wait()
        self.process = None
    
    def _bgr_to_rgba(self, frame: np.ndarray):
        """将BGR格式帧转换为RGBA格式"""
        rgba_frame = np.zeros((frame.shape[0], frame.shape[1], 4), dtype=np.uint8)
        # 正确的 BGR -> RGB 转换
        rgba_frame[..., 0] = frame[..., 2]  # 红色通道
        rgba_frame[..., 1] = frame[..., 1]  # 绿色通道
        rgba_frame[..., 2] = frame[..., 0]  # 蓝色通道
        rgba_frame[..., 3] = 255           # Alpha 通道设置为完全不透明
        return rgba_frame
    
    def _detect_device_format(self):
        """自动检测并选择合适的视频设备和输入格式"""
        system = platform.system()
        device_prefix = ""

        if system == "Darwin":  # macOS
            input_format = "avfoundation"
        elif system == "Linux":  # Linux
            input_format = "v4l2"
            device_prefix = "/dev/video"
        elif system == "Windows":  # Windows
            input_format = "dshow"
        else:
            raise RuntimeError(f"Unsupported operating system: {system}")

        return input_format, device_prefix


if __name__ == "__main__":
    camera = FFmpegCamera(device=0, resolution=(640, 480), camera_fps=30)
    camera.start_capture()
    try:
        frame = camera.read_frame()
    except Exception as e:
        print(camera.process.stderr.read().decode())
        raise
    print(frame.shape)
    camera.start_capture()