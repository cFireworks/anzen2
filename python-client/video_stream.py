import os
import random
import cv2
import websockets
import asyncio
import json
import socket
from time import time
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

class WebSocketClient:
    def __init__(self):
        # 配置参数
        self.RECONNECT_INTERVAL = 5  # 重连间隔（秒）
        self.MAX_RETRIES = 5         # 最大重试次数
        self.DEVICE_ID = random.randint(1000000, 9999999)
        self.WS_URL = os.getenv("WS_SERVER", "ws://127.0.0.1:8080/ws/")
        self.RESOLUTION = (640, 480) # 与JS中的idealResolution一致
        self.FRAME_INTERVAL = 0.25   # 发送间隔（秒）
        self.MAX_CHUNK_SIZE = 64 * 1024
        
        # 状态管理
        self.ws = None
        self.capture = None
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

    def _init_camera(self):
        """初始化摄像头配置"""
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            raise RuntimeError("Failed to open camera")
        
        # 设置分辨率（尝试匹配JS约束）
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.RESOLUTION[0])
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.RESOLUTION[1])
        self.capture.set(cv2.CAP_PROP_FPS, 15)

    def _prepare_frame_data(self, frame, is_message_fragmented: False):
        """准备符合服务端格式的帧数据"""
        # 转换为RGBA格式（匹配JS的Canvas ImageData格式）
        rgba_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        
        # 生成设备ID字节（匹配JS的数字数组格式）
        device_id_bytes = bytes(map(int, str(self.DEVICE_ID)))
        
        # 组合图像数据+设备ID（设备ID附加在末尾）
        frame_data = rgba_frame.tobytes() + device_id_bytes
        if not is_message_fragmented:
            return frame_data
        chunks = [frame_data[i:i+self.MAX_CHUNK_SIZE] for i in range(0, len(frame_data), self.MAX_CHUNK_SIZE)]
        return chunks


    async def send_frames(self):
        """持续发送视频帧"""
        try:
            while self.running and self.ws:
                start_time = time()
                
                # 读取视频帧
                ret, frame = self.capture.read()
                if not ret:
                    print("Failed to capture frame")
                    continue

                # 准备并发送数据
                frame_data = self._prepare_frame_data(frame, is_message_fragmented=True)
                await self.ws.send(frame_data)  # 自动分片处理
                
                # 控制帧率
                elapsed = time() - start_time
                await asyncio.sleep(max(0, self.FRAME_INTERVAL - elapsed))
                
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
            await self.ws.close()
        if self.capture and self.capture.isOpened():
            self.capture.release()
        logger.info("Connection closed")

    async def run(self):
        """主运行循环"""
        self.running = True
        self._init_camera()
        
        try:
            await self.connect_websocket()
            if self.ws:
                await self.send_frames()
        finally:
            await self.close_connection()

if __name__ == "__main__":
    client = WebSocketClient()
    
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        asyncio.run(client.close_connection())
    finally:
        cv2.destroyAllWindows()