import asyncio
import websockets
import json
import os
import random
from time import time
from dotenv import load_dotenv
import logging
from camera.camera_factory import CameraFactory
from PIL import Image
import numpy as np
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

class WebSocketClient:
    def __init__(self, camera_type='cv2', fps=15, jpeg_compression=False, **camera_params):
        # 配置参数
        self.RECONNECT_INTERVAL = 5  # 重连间隔（秒）
        self.MAX_RETRIES = 5         # 最大重试次数
        self.DEVICE_ID = random.randint(1000000, 9999999)
        self.WS_URL = os.getenv("WS_SERVER", "ws://127.0.0.1:8080/ws/")
        self.RESOLUTION = (640, 480) # 与JS中的idealResolution一致
        self.FRAME_INTERVAL = 0.25   # 发送间隔（秒）
        self.MAX_CHUNK_SIZE = 64 * 1024
        self.MAX_FPS = 35
        self.fps = fps

        self.JPEG_COMPRESSION = jpeg_compression
        self.JPEG_QUALITY = 75
        
        # 状态管理
        self.ws = None
        self.capture = CameraFactory.get_camera(camera_type, resolution=self.RESOLUTION, **camera_params)
        self.running = False
        self.reconnect_attempts = 0

    async def connect_websocket(self):
        """建立WebSocket连接并处理重连"""
        while self.running and self.reconnect_attempts < self.MAX_RETRIES:
            try:
                logger.info(f"Connecting to {self.WS_URL}... (attempt {self.reconnect_attempts+1})")
                self.ws = await websockets.connect(self.WS_URL)
                await self._on_connect()
                self.reconnect_attempts = 0
                return
            except Exception as e:
                logger.error(f"Connection failed: {str(e)}")
                self.reconnect_attempts += 1
                await asyncio.sleep(self.RECONNECT_INTERVAL)
        
        logger.info("Max reconnect attempts reached")
        self.running = False

    async def _on_connect(self):
        """连接成功处理"""
        logger.info("WebSocket connected")
        await self.ws.send(json.dumps({
            "sender_id": self.DEVICE_ID,
            "connection_type": 130,
            "data": "connectDevice"
        }))

    def _prepare_frame_data(self, rgba_frame, is_message_fragmented: False):
        """准备符合服务端格式的帧数据"""
        if self.JPEG_COMPRESSION:
            # 将RGBA数组转换为JPEG字节数组
            rgba_image = Image.fromarray(rgba_frame, 'RGBA')
            with BytesIO() as byte_io:
                rgba_image.convert('RGB').save(byte_io, format='JPEG', quality=self.JPEG_QUALITY)  # 转换为RGB并保存为JPEG
                frame_byte_array = byte_io.getvalue()
        else:
            # 不使用JPEG压缩时直接转为字节数组
            frame_byte_array = rgba_frame.tobytes()
        
        # 生成设备ID字节（匹配JS的数字数组格式）
        device_id_bytes = bytes(map(int, str(self.DEVICE_ID)))
        
        # 组合图像数据+设备ID（设备ID附加在末尾）
        frame_data = frame_byte_array + device_id_bytes
        if not is_message_fragmented:
            return frame_data
        chunks = [frame_data[i:i+self.MAX_CHUNK_SIZE] for i in range(0, len(frame_data), self.MAX_CHUNK_SIZE)]
        return chunks

    async def send_frames(self):
        """持续发送视频帧"""
        try:
            last_frame_time = time()
            last_iteration_time = 0
            delay_time = 0
            while self.running and self.ws:
                iteration_start = time()

                frame_duration = iteration_start - last_frame_time

                iteration_duration = iteration_start - last_iteration_time
                if iteration_duration < (1 / self.MAX_FPS):
                    continue
                last_iteration_time = iteration_start
                
                # 1. 捕获帧耗时
                capture_start = time()
                frame = self.capture.read_frame()
                capture_duration = time() - capture_start

                if frame_duration < max(1 / self.fps, delay_time):
                    continue
                last_frame_time = iteration_start
                
                # 2. 数据处理耗时
                prepare_start = time()
                frame_data_batch = self._prepare_frame_data(frame, is_message_fragmented=True)
                prepare_duration = time() - prepare_start
                frame_size = sum([len(frame_data) for frame_data in frame_data_batch])  # 记录帧数据大小
                
                # 3. 数据发送耗时
                send_start = time()
                await self.ws.send(frame_data_batch)
                send_duration = time() - send_start
                
                # 4. 总耗时
                total_duration = time() - iteration_start
                
                # 记录指标日志
                logger.debug(
                    "[PERF] Frame Stats: "
                    f"capture={capture_duration:.3f}s, "
                    f"prepare={prepare_duration:.3f}s, "
                    f"send={send_duration:.3f}s, "
                    f"total={total_duration:.3f}s, "
                    f"size={frame_size} bytes"
                )
                                
                # 5. 帧率控制指标
                delay_time = total_duration - 1/self.fps
                if delay_time > 0:
                    logger.warning(
                        f"[PERF] Frame delayed! Processing exceeded interval by {delay_time:.3f}s"
                    )
                
        except websockets.ConnectionClosed:
            logger.warning("Connection closed, reconnecting...")
            await self.reconnect()
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            self.running = False

    async def reconnect(self):
        """处理重新连接"""
        await self.close_connection()
        await self.connect_websocket()
        if self.ws:
            await self.send_frames()

    async def close_connection(self):
        """关闭连接"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"Error during closing websocket: {e}")
        self.capture.stop_capture()
        logger.info("Connection closed")

    async def run(self):
        """主运行循环"""
        self.running = True
        self.capture.start_capture()
        
        try:
            await self.connect_websocket()
            if self.ws:
                await self.send_frames()
        finally:
            await self.close_connection()

if __name__ == "__main__":
    camera_type = os.getenv("CAMERA_TYPE", "cv2")
    client = WebSocketClient(camera_type=camera_type, fps=5, jpeg_compression=True, device=0, camera_fps=30)
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        asyncio.run(client.close_connection())
    finally:
        pass