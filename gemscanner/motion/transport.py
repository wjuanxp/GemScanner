class SerialTransport:
    """pyserial-backed transport (bench).

    The ESP32-C6's USB-CDC resets / re-enumerates when the port is opened, so the
    board isn't ready for ~1-2 s after ``serial.Serial(...)`` returns. Without a
    settle the first command (e.g. ``SETRES``) is dropped and times out. We wait
    ``settle_s`` and flush any boot banner before returning.
    """

    def __init__(self, port, baud=115200, timeout=2.0, settle_s=2.0):
        import time
        import serial
        self._ser = serial.Serial(port, baud, timeout=timeout)
        if settle_s:
            time.sleep(settle_s)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

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
