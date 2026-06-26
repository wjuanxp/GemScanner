from collections import deque


class FakeFirmware:
    """In-process Transport emulating the Plan B controller protocol."""

    def __init__(self):
        self._out = deque()
        self.pos_steps = 0
        self.steps_per_rev = 0
        self.v, self.a, self.settle = 4000, 20000, 150

    def write_line(self, s):
        parts = s.strip().split()
        if not parts:
            self._out.append("ERR unknown")
            return
        verb, args = parts[0].upper(), parts[1:]

        def as_int():
            return int(args[0])

        try:
            if verb == "STEP":
                self.pos_steps += as_int()
                self._out += ["OK", "READY"]
            elif verb == "MOVEDEG":
                deg = float(args[0])
                if self.steps_per_rev <= 0:
                    self._out.append("ERR nores")
                else:
                    self.pos_steps += round(deg / 360.0 * self.steps_per_rev)
                    self._out += ["OK", "READY"]
            elif verb == "SETRES":
                n = as_int()
                if n > 0:
                    self.steps_per_rev = n
                    self._out.append("OK")
                else:
                    self._out.append("ERR badarg")
            elif verb == "SETV":
                self.v = as_int()
                self._out.append("OK")
            elif verb == "SETACC":
                self.a = as_int()
                self._out.append("OK")
            elif verb == "SETSETTLE":
                self.settle = as_int()
                self._out.append("OK")
            elif verb == "HOME":
                self.pos_steps = 0
                self._out += ["OK", "READY"]
            elif verb == "STATUS":
                angle = (self.pos_steps / self.steps_per_rev * 360.0) % 360.0 if self.steps_per_rev else 0.0
                self._out.append(
                    f"STATUS angle={angle:.3f} steps={self.pos_steps} state=idle "
                    f"v={self.v} a={self.a} settle={self.settle} res={self.steps_per_rev}")
            else:
                self._out.append("ERR unknown")
        except (ValueError, IndexError):
            self._out.append("ERR badarg")

    def read_line(self, timeout=None):
        return self._out.popleft() if self._out else None

    def close(self):
        pass
