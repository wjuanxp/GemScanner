from gemscanner.gui.project import GemJob, Project


def test_project_roundtrip(tmp_path):
    p = Project(
        camera_backend="gentl",
        camera={"cti_path": "x.cti", "exposure_us": 500, "gain": 5},
        serial_port="COM3", serial_baud=115200,
        mm_per_px=0.017, steps_per_rev=90000,
        gems=[
            GemJob(name="ruby-01", holder_mask_rows=660, axis_column=1214.0, out="scans/ruby-01"),
            GemJob(name="emerald-02", holder_mask_rows=705, axis_column=1216.0,
                   exposure_us=400.0, out="scans/emerald-02"),
        ],
        calibration_path="calibration.json",
    )
    path = tmp_path / "project.yaml"
    p.save(str(path))
    q = Project.load(str(path))
    assert q.mm_per_px == 0.017
    assert q.steps_per_rev == 90000
    assert [g.name for g in q.gems] == ["ruby-01", "emerald-02"]
    assert q.gems[1].exposure_us == 400.0
    assert isinstance(q.gems[0], GemJob)


def test_to_scanner_config_merges_gem_overrides():
    p = Project(
        camera_backend="gentl", camera={"exposure_us": 500, "gain": 5},
        serial_port="COM3", serial_baud=115200,
        mm_per_px=0.017, steps_per_rev=90000,
        gems=[GemJob(name="g", holder_mask_rows=660, axis_column=1214.0,
                     exposure_us=400.0, out="scans/g")],
        calibration_path="calibration.json",
    )
    cfg = p.to_scanner_config(p.gems[0])
    assert cfg.camera_backend == "gentl"
    assert cfg.camera["exposure_us"] == 400.0   # gem override wins
    assert cfg.camera["gain"] == 5              # project value kept
    assert cfg.scan["holder_mask_rows"] == 660
