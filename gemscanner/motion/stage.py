class StageError(Exception):
    pass


class RotaryStage:
    def __init__(self, transport, reply_timeout=2.0, move_timeout=60.0):
        self._t = transport
        self._reply_timeout = reply_timeout
        self._move_timeout = move_timeout

    def _send_ok(self, line, timeout):
        self._t.write_line(line)
        reply = self._t.read_line(timeout=timeout)
        if reply is None:
            raise StageError(f"timeout waiting for reply to {line!r}")
        if reply.startswith("ERR"):
            raise StageError(f"{line!r} -> {reply}")
        if reply != "OK":
            raise StageError(f"{line!r} -> unexpected {reply!r}")

    def _move(self, line):
        self._send_ok(line, self._reply_timeout)
        ready = self._t.read_line(timeout=self._move_timeout)
        if ready != "READY":
            raise StageError(f"{line!r} -> expected READY, got {ready!r}")

    def set_resolution(self, steps_per_rev):
        self._send_ok(f"SETRES {int(steps_per_rev)}", self._reply_timeout)

    def set_speed(self, v):
        self._send_ok(f"SETV {int(v)}", self._reply_timeout)

    def set_accel(self, a):
        self._send_ok(f"SETACC {int(a)}", self._reply_timeout)

    def set_settle(self, ms):
        self._send_ok(f"SETSETTLE {int(ms)}", self._reply_timeout)

    def step(self, microsteps):
        self._move(f"STEP {int(microsteps)}")

    def move_deg(self, deg):
        self._move(f"MOVEDEG {deg}")

    def home(self):
        self._move("HOME")

    def status(self):
        self._t.write_line("STATUS")
        line = self._t.read_line(timeout=self._reply_timeout)
        if not line or not line.startswith("STATUS "):
            raise StageError(f"bad STATUS reply: {line!r}")
        out = {}
        for tok in line[len("STATUS "):].split():
            k, _, v = tok.partition("=")
            if k == "angle":
                out[k] = float(v)
            elif k in ("steps", "v", "a", "settle", "res"):
                out[k] = int(v)
            else:
                out[k] = v
        return out
