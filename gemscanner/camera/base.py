from abc import ABC, abstractmethod


class CameraBackend(ABC):
    @abstractmethod
    def open(self): ...
    @abstractmethod
    def close(self): ...
    @abstractmethod
    def grab(self): ...

    def set_exposure(self, us):
        pass

    def set_gain(self, gain):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False
