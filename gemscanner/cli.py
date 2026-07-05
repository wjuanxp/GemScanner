import argparse
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def main(argv=None):
    p = argparse.ArgumentParser(prog="gemscanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconstruct")
    r.add_argument("dataset")
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--smooth", type=int, default=0,
                   help="Taubin smoothing iterations (0 = off; ~10 removes "
                        "per-slice layering without shrinking the mesh)")

    v = sub.add_parser("view")
    v.add_argument("mesh")

    s = sub.add_parser("scan")
    s.add_argument("-c", "--config", required=True)
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--smooth", type=int, default=None,
                   help="Taubin smoothing iterations; overrides config scan.smooth")

    g = sub.add_parser("gui")
    g.add_argument("-p", "--project", default="project.yaml")

    args = p.parse_args(argv)

    if args.cmd == "reconstruct":
        from gemscanner.smoothing import smooth_mesh
        mesh = reconstruct_dataset(args.dataset)
        mesh = smooth_mesh(mesh, args.smooth)
        export_mesh(mesh, args.out)
        print(f"wrote {args.out}: watertight={mesh.is_watertight}")
        return 0
    if args.cmd == "view":
        from gemscanner.viewer import show_mesh
        show_mesh(args.mesh)
        return 0
    if args.cmd == "scan":
        from gemscanner.run_scan import run_scan_from_config   # Task 12
        return run_scan_from_config(args.config, args.out, smooth=args.smooth)
    if args.cmd == "gui":
        from gemscanner.gui.app import main as gui_main
        return gui_main(["-p", args.project])
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
