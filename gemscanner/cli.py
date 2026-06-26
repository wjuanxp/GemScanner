import argparse
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def main(argv=None):
    p = argparse.ArgumentParser(prog="gemscanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconstruct")
    r.add_argument("dataset")
    r.add_argument("-o", "--out", required=True)

    v = sub.add_parser("view")
    v.add_argument("mesh")

    s = sub.add_parser("scan")
    s.add_argument("-c", "--config", required=True)
    s.add_argument("-o", "--out", required=True)

    args = p.parse_args(argv)

    if args.cmd == "reconstruct":
        mesh = reconstruct_dataset(args.dataset)
        export_mesh(mesh, args.out)
        print(f"wrote {args.out}: watertight={mesh.is_watertight}")
        return 0
    if args.cmd == "view":
        from gemscanner.viewer import show_mesh
        show_mesh(args.mesh)
        return 0
    if args.cmd == "scan":
        from gemscanner.run_scan import run_scan_from_config   # Task 12
        return run_scan_from_config(args.config, args.out)
    return 1
