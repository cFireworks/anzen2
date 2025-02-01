import cv2
from .base import CameraBase

class CV2Camera(CameraBase):
    def __init__(self, device=0, resolution=(640, 480), fps=15):
        self.device = device
        self.resolution = resolution
        self.fps = fps
        self.capture = None

    def start_capture(self):
        self.capture = cv2.VideoCapture(self.device)
        if not self.capture.isOpened():
            raise RuntimeError("Failed to open camera")
        
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.capture.set(cv2.CAP_PROP_FPS, self.fps)

    def read_frame(self):
        ret, frame = self.capture.read()
        if not ret:
            raise RuntimeError("Failed to capture frame")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)

    def stop_capture(self):
        if self.capture and self.capture.isOpened():
            self.capture.release()
        self.capture = None