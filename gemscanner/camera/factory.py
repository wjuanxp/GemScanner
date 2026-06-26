from gemscanner.camera.mock import MockCamera


def create_camera(config):
    backend = config.camera_backend
    cam = config.camera or {}
    if backend == "mock":
        return MockCamera(frames=cam.get("frames"))
    if backend == "opencv":
        from gemscanner.camera.opencv_camera import OpenCvCamera
        return OpenCvCamera(index=cam.get("index", 0), exposure=cam.get("exposure"))
    if backend == "baumer":
        from gemscanner.camera.baumer_camera import BaumerCamera
        return BaumerCamera(**{k: v for k, v in cam.items()})
    raise ValueError(f"unknown camera_backend {backend!r}")
