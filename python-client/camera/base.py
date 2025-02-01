from abc import ABC, abstractmethod

class CameraBase(ABC):
    @abstractmethod
    def start_capture(self):
        """初始化视频采集设备"""
        pass

    @abstractmethod
    def read_frame(self):
        """读取一帧视频数据并返回RGBA格式的numpy数组"""
        pass

    @abstractmethod
    def stop_capture(self):
        """释放采集资源"""
        pass