class SerialTransport:
    """pyserial-backed transport (bench)."""

    def __init__(self, port, baud=115200, timeout=2.0):
        import serial
        self._ser = serial.Serial(port, baud, timeout=timeout)

    def write_line(self, s):
        self._ser.write((s + "\n").encode("ascii"))

    def read_line(self, timeout=None):
        if timeout is not None:
            self._ser.timeout = timeout
        raw = self._ser.readline()
        if not raw:
            return None
        return raw.decode("ascii", "replace").strip()

    def close(self):
        self._ser.close()
