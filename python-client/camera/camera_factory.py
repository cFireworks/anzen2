class CameraFactory:
    @staticmethod
    def get_camera(camera_type='cv2', **kwargs):
        """根据摄像头类型选择不同的实现"""
        if camera_type == 'cv2':
            from .cv2_camera import CV2Camera
            return CV2Camera(**kwargs)
        elif camera_type == 'v4l2':
            from .v4l2_camera import V4L2Camera
            return V4L2Camera(**kwargs)
        else:
            raise ValueError(f"Unknown camera type: {camera_type}")
