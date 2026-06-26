from gemscanner.motion.fake_firmware import FakeFirmware


def drain(fw):
    out = []
    while True:
        line = fw.read_line(timeout=0)
        if line is None:
            break
        out.append(line)
    return out


def test_step_replies_ok_then_ready():
    fw = FakeFirmware()
    fw.write_line("STEP 100")
    assert drain(fw) == ["OK", "READY"]


def test_movedeg_blocked_until_setres():
    fw = FakeFirmware()
    fw.write_line("MOVEDEG 90")
    assert drain(fw) == ["ERR nores"]
    fw.write_line("SETRES 20000")
    assert drain(fw) == ["OK"]
    fw.write_line("MOVEDEG 90")
    assert drain(fw) == ["OK", "READY"]


def test_status_tracks_position_and_res():
    fw = FakeFirmware()
    fw.write_line("SETRES 20000"); drain(fw)
    fw.write_line("STEP 5000"); drain(fw)
    fw.write_line("STATUS")
    line = drain(fw)[0]
    assert line.startswith("STATUS ")
    assert "steps=5000" in line
    assert "res=20000" in line
    assert "angle=90.000" in line   # 5000/20000*360


def test_unknown_and_badarg():
    fw = FakeFirmware()
    fw.write_line("WIGGLE"); assert drain(fw) == ["ERR unknown"]
    fw.write_line("SETV abc"); assert drain(fw) == ["ERR badarg"]
