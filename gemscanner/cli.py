import argparse
from gemscanner.reconstruction.pipeline import reconstruct_dataset
from gemscanner.storage.mesh_io import export_mesh


def main(argv=None):
    p = argparse.ArgumentParser(prog="gemscanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconstruct")
    r.add_argument("dataset")
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--method", choices=("strip", "soft_hull", "facet"),
                   default="strip",
                   help="reconstruction method (default: strip). strip = fast "
                        "per-slice visual hull; soft_hull = anti-aliased "
                        "volumetric hull + marching cubes; facet = planar-facet "
                        "polyhedron.")
    r.add_argument("--holder-mask-rows", type=int, default=0, metavar="N",
                   help="mask the bottom N image rows so the silhouette sees "
                        "only the gem, dropping the pedestal/stage below it "
                        "(default 0 = keep everything; gem04 rig value is 705)")
    r.add_argument("--smooth", type=int, default=0,
                   help="Taubin smoothing iterations (0 = off; ~10 removes "
                        "per-slice layering without shrinking the mesh)")
    r.add_argument("--subpixel-edges", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="locate silhouette edges on the intensity crossing "
                        "instead of the nearest whole pixel; removes the ~1 px "
                        "edge quantisation terracing feeds on (gem04: per-row "
                        "edge roughness 12.6 -> 2.2 um, mean shift +0.4 um). "
                        "On by default; --no-subpixel-edges for a whole-pixel "
                        "baseline.")

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
        from gemscanner.reconstruction.base import ReconstructionParams
        mesh = reconstruct_dataset(
            args.dataset,
            ReconstructionParams(method=args.method,
                                 holder_mask_rows=args.holder_mask_rows,
                                 subpixel_edges=args.subpixel_edges))
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
