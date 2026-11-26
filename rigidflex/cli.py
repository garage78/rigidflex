"""rigidflex: rigid + TPU multi-material parts and bond tests for the Snapmaker U1.

  rigidflex plan -o campaign/                      # every plate + a pre-filled results sheet
  rigidflex kit coupon --type A --joint dovetail   # one plate of 5 coupons
  rigidflex kit coupon --type G --joint graded     # three materials: rigid | TPU 95A | TPU 85A
  rigidflex kit grommet --hole 25 --cable 8        # rigid ring + TPU seal, any size (--three: soft lip)
  rigidflex kit softjaw --width 100 --height 25    # magnetic vise jaw with a TPU face
  rigidflex kit rig -o rig/                        # printable parts of the pull-test rig
  rigidflex rig --port /dev/cu.usbserial-0001 info # talk to the rig (tare, cal 98.1, jog 5 ...)
  rigidflex stiffness --port ...                   # once: the rig's own stiffness (steel dummy coupon)
  rigidflex test campaign/results.csv --port ...   # guided testing: pull, save curves, fill in the sheet
  rigidflex plot campaign/curves/*.csv -o curves.svg
  rigidflex analyze campaign/results.csv [--plates campaign/print_log.csv]
  rigidflex advise campaign/results.csv --rigid PETG [--heat]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import __version__
from .advise import explain, recommend
from .analyze import load, markdown_report, summarise, waste_report, write_summary_csv
from .plan import build, write_checklist, write_print_log, write_sheet
from .scad import SCAD_DIR, export_part, find_openscad
from .threemf import Object3MF, Volume, write_3mf

JOINTS = ["flat", "sawtooth", "dovetail", "orca-beam"]
G_JOINTS = ["direct", "graded"]
ORDERS = ["tpu-on-rigid", "rigid-on-tpu"]
RIG_PARTS = ["ebox", "ebox_lid", "cell_anchor", "fork_a", "carriage", "motor_end"]


def _two_material_object(name, scad_file, params, rigid_tool, tpu_tool, offset=(0, 0, 0), settings=None):
    return Object3MF(
        name=name,
        volumes=[Volume("rigid", export_part(scad_file, "rigid", params), rigid_tool),
                 Volume("tpu", export_part(scad_file, "flex", params), tpu_tool)],
        offset=offset,
        settings=settings or {},
    )


def coupon_plate(path, kind="A", joint="flat", overlap=20.0, order="tpu-on-rigid", copies=5,
                 rigid_tool=1, tpu_tool=2, width=10.0, thickness=3.0, soft_tool=3, buffer=6.0) -> Path:
    params: dict[str, object] = {"coupon": "B" if kind == "B" else "A", "width": width, "thickness": thickness}
    settings: dict[str, str] = {}
    if kind == "G":
        # graded series: flat butt joint; "direct" = rigid + soft TPU, "graded" = rigid | TPU 95A band | soft TPU
        params["joint"] = "flat"
        params["buffer"] = buffer if joint == "graded" else 0
        volumes = [Volume("rigid", export_part("coupons.scad", "rigid", params), rigid_tool)]
        if joint == "graded":
            volumes.append(Volume("tpu95a_band", export_part("coupons.scad", "buffer", params), tpu_tool))
        volumes.append(Volume("tpu85a", export_part("coupons.scad", "flex", params), soft_tool))
        label = f"G_{joint}"
        objects = [Object3MF(f"{label}_{i + 1}", volumes, (0, i * 30, 0)) for i in range(copies)]
        return write_3mf(path, objects, title=label)
    if kind == "A":
        # "orca-beam" = flat butt joint + the slicer's own beam interlocking at the interface
        params["joint"] = "flat" if joint == "orca-beam" else joint
        if joint == "orca-beam":
            settings["interlocking_beam"] = "1"
        label = f"A_{joint}"
    else:
        params["overlap"] = overlap
        params["rigid_below"] = order == "tpu-on-rigid"
        label = f"B_overlap{overlap:g}_{order}"
    # one OpenSCAD run per material, then copies are offset on the plate
    first = _two_material_object(f"{label}_1", "coupons.scad", params, rigid_tool, tpu_tool, settings=settings)
    objects = [Object3MF(f"{label}_{i + 1}", first.volumes, (0, i * 30, 0), settings) for i in range(copies)]
    return write_3mf(path, objects, title=label)


def cmd_kit_coupon(a: argparse.Namespace) -> None:
    if a.type == "G":
        joint = a.joint if a.joint in G_JOINTS else "graded"
        label = f"G_{joint}"
    else:
        joint = a.joint if a.joint in JOINTS else "flat"
        label = f"A_{joint}" if a.type == "A" else f"B_overlap{a.overlap:g}_{a.order}"
    out = coupon_plate(a.output or f"{label}.3mf", a.type, joint, a.overlap, a.order, a.copies,
                       a.rigid_tool, a.tpu_tool, a.width, a.thickness, a.soft_tool, a.buffer)
    tools = f"rigid -> extruder {a.rigid_tool}, TPU 95A -> {a.tpu_tool}"
    if a.type == "G":
        tools = f"rigid -> extruder {a.rigid_tool}, " + (f"TPU 95A band -> {a.tpu_tool}, " if joint == "graded" else "") + f"TPU 85A -> {a.soft_tool}"
    print(f"Wrote {out}  ({a.copies} coupon(s); {tools})")


def cmd_kit_grommet(a: argparse.Namespace) -> None:
    params = {"panel_hole_d": a.hole, "panel_thick": a.panel, "cable_d": a.cable, "three": a.three}
    label = f"grommet_{a.hole:g}mm_cable{a.cable:g}mm" + ("_3mat" if a.three else "")
    obj = _two_material_object(label, "grommet.scad", params, a.rigid_tool, a.tpu_tool)
    if a.three and a.cable > 0:
        obj.volumes.append(Volume("soft_lip", export_part("grommet.scad", "soft", params), a.soft_tool))
    print(f"Wrote {write_3mf(a.output or f'{label}.3mf', [obj], title=label)}")


def cmd_kit_softjaw(a: argparse.Namespace) -> None:
    params = {"jaw_w": a.width, "jaw_h": a.height, "face": a.face}
    label = f"softjaw_{a.width:g}x{a.height:g}_{a.face}"
    objs = [_two_material_object(f"{label}_{i + 1}", "soft_jaw.scad", params, a.rigid_tool, a.tpu_tool,
                                 offset=(0, i * (a.height + 10), 0)) for i in range(2)]
    print(f"Wrote {write_3mf(a.output or f'{label}.3mf', objs, title=label)}  (a pair)")


def cmd_kit_rig(a: argparse.Namespace) -> None:
    out = Path(a.output or "rig")
    out.mkdir(parents=True, exist_ok=True)
    for p in RIG_PARTS:
        f = out / f"rig_{p}.stl"
        subprocess.run([find_openscad(), "-o", str(f), "-D", f'part="{p}"', str(SCAD_DIR / "pull_rig.scad")],
                       check=True, capture_output=True)
        print(f"Wrote {f}")
    print("Bought parts, wiring and assembly: docs/pull_rig.md. Firmware: firmware/rigidflex_rig/")


def cmd_plan(a: argparse.Namespace) -> None:
    out = Path(a.output)
    (out / "plates").mkdir(parents=True, exist_ok=True)
    plates, conds = build(t_joint=a.t_joint, tpu_low=a.tpu_low, tpu_high=a.tpu_high, tpu_default=a.tpu_temp)
    for p in plates:
        coupon_plate(out / "plates" / p.file, p.kind, p.joint, p.overlap, p.order, a.copies)
        print(f"  plate {p.file}")
    n = write_sheet(conds, out / "results.csv", a.copies)
    write_print_log(conds, out / "print_log.csv")
    write_checklist(conds, out / "checklist.md", a.copies)
    print(f"Wrote {len(plates)} plates, {out / 'results.csv'} ({n} coupons), {out / 'print_log.csv'} and {out / 'checklist.md'}")


def cmd_analyze(a: argparse.Namespace) -> None:
    rows = load(a.results)
    conds = summarise(rows)
    out_dir = Path(a.out_dir or Path(a.results).parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(a.results).stem
    write_summary_csv(conds, out_dir / f"{stem}_summary.csv")
    report = markdown_report(conds, a.results)
    if a.plates:
        report += "\n" + waste_report(a.plates)
    (out_dir / f"{stem}_report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out_dir / (stem + '_summary.csv')} and {out_dir / (stem + '_report.md')}")


def cmd_advise(a: argparse.Namespace) -> None:
    conds = summarise(load(a.results))
    best = recommend(conds, a.rigid, heat=a.heat, min_n=a.min_n)
    if not best:
        print(f"No condition for {a.rigid}{' after heat soak' if a.heat else ''} with at least {a.min_n} coupons in {a.results}.")
        sys.exit(1)
    print(f"Best measured options for {a.rigid} + TPU{' (heat-soaked)' if a.heat else ''}:")
    for i, c in enumerate(best, 1):
        print(f"{i}. {explain(c)}")


def _open_rig(a: argparse.Namespace):
    from .rig import SerialRig, SimulatedRig
    if getattr(a, "simulate", False):
        return SimulatedRig(seed=1)
    if not a.port:
        raise SystemExit("Give --port (e.g. /dev/cu.usbserial-0001 or COM3), or --simulate to try without hardware.")
    return SerialRig(a.port)


def cmd_rig(a: argparse.Namespace) -> None:
    from .rig import RigError
    rig = _open_rig(a)
    try:
        print(rig.command(" ".join(a.command), timeout=a.timeout))
    except RigError as e:
        raise SystemExit(f"rig: {e}")
    finally:
        rig.close()


def cmd_test(a: argparse.Namespace) -> None:
    from .rig import session
    rig = _open_rig(a)
    try:
        session(Path(a.results), rig, a.curves, a.max_mm, a.speed, a.rig_stiffness, a.series)
    finally:
        rig.close()


def cmd_stiffness(a: argparse.Namespace) -> None:
    from .rig import rig_stiffness
    rig = _open_rig(a)
    try:
        curve, end = rig.run(a.max_mm, a.speed)
    finally:
        rig.close()
    k = rig_stiffness(curve)
    print(f"Rig stiffness: {k:.0f} N/mm (peak {max(curve.f_n):.0f} N, stopped: {end['reason']}).")
    print(f"Use it with:  rigidflex test results.csv --port ... --rig-stiffness {k:.0f}")


def cmd_plot(a: argparse.Namespace) -> None:
    from .rig import plot
    print(f"Wrote {plot([Path(p) for p in a.curves], Path(a.output), a.title)}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="rigidflex", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"rigidflex {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    tools = argparse.ArgumentParser(add_help=False)
    tools.add_argument("--rigid-tool", type=int, default=1, help="extruder for the rigid material (default 1)")
    tools.add_argument("--tpu-tool", type=int, default=2, help="extruder for TPU 95A (default 2)")
    tools.add_argument("--soft-tool", type=int, default=3, help="extruder for the soft TPU 85A (default 3)")
    tools.add_argument("-o", "--output", help="output path")

    pl = sub.add_parser("plan", help="generate the whole test campaign")
    pl.add_argument("-o", "--output", default="campaign")
    pl.add_argument("--copies", type=int, default=5)
    pl.add_argument("--tpu-temp", type=int, default=230, help="default TPU nozzle temperature")
    pl.add_argument("--tpu-low", type=int, default=220)
    pl.add_argument("--tpu-high", type=int, default=240)
    pl.add_argument("--t-joint", choices=JOINTS, default="dovetail", help="joint used for the temperature series")
    pl.set_defaults(func=cmd_plan)

    kit = sub.add_parser("kit", help="generate printable files")
    ksub = kit.add_subparsers(dest="what", required=True)

    c = ksub.add_parser("coupon", parents=[tools], help="one plate of bond-test coupons (two-material 3MF)")
    c.add_argument("--type", choices=["A", "B", "G"], default="A",
                   help="A = in-layer butt joint, B = lap joint between layers, G = graded (three materials)")
    c.add_argument("--joint", choices=JOINTS + G_JOINTS, default="flat", help="type A joint, or direct / graded for type G")
    c.add_argument("--buffer", type=float, default=6, help="type G: width of the TPU 95A band, mm")
    c.add_argument("--overlap", type=float, default=20, help="type B overlap length, mm")
    c.add_argument("--order", choices=ORDERS, default="tpu-on-rigid", help="type B print order")
    c.add_argument("--width", type=float, default=10, help="gauge-section width, mm")
    c.add_argument("--thickness", type=float, default=3)
    c.add_argument("--copies", type=int, default=5, help="coupons per plate (default 5)")
    c.set_defaults(func=cmd_kit_coupon)

    g = ksub.add_parser("grommet", parents=[tools], help="rigid ring + TPU sealing membrane (two-material 3MF)")
    g.add_argument("--hole", type=float, required=True, help="panel hole diameter, mm")
    g.add_argument("--panel", type=float, default=1.2, help="panel thickness, mm")
    g.add_argument("--cable", type=float, default=0, help="cable diameter, mm (0 = blanking plug)")
    g.add_argument("--three", action="store_true", help="soft TPU 85A sealing lip on extruder --soft-tool")
    g.set_defaults(func=cmd_kit_grommet)

    s = ksub.add_parser("softjaw", parents=[tools], help="magnetic vise soft jaws with a TPU face (two-material 3MF)")
    s.add_argument("--width", type=float, default=100)
    s.add_argument("--height", type=float, default=25)
    s.add_argument("--face", choices=["smooth", "ribbed"], default="ribbed")
    s.set_defaults(func=cmd_kit_softjaw)

    r = ksub.add_parser("rig", help="printable STL parts of the pull-test rig")
    r.add_argument("-o", "--output", default="rig")
    r.set_defaults(func=cmd_kit_rig)

    port = argparse.ArgumentParser(add_help=False)
    port.add_argument("--port", help="serial port of the rig")
    port.add_argument("--simulate", action="store_true", help="use a simulated rig (made-up numbers)")

    rg = sub.add_parser("rig", parents=[port], help="send one command to the rig (info, tare, cal <N>, read, jog <mm>, en 0)")
    rg.add_argument("command", nargs="+")
    rg.add_argument("--timeout", type=float, default=60)
    rg.set_defaults(func=cmd_rig)

    te = sub.add_parser("test", parents=[port], help="guided testing: pull each coupon, save its curve, fill in the sheet")
    te.add_argument("results", help="results.csv from `rigidflex plan`")
    te.add_argument("--curves", help="folder for the curve files (default: curves/ next to the sheet)")
    te.add_argument("--max-mm", type=float, default=40, help="stop at this extension: 100 %% TPU strain (default 40)")
    te.add_argument("--speed", type=float, default=2, help="mm/s (default 2)")
    te.add_argument("--rig-stiffness", type=float, help="N/mm, from the steel dummy coupon (see docs/protocol.md)")
    te.add_argument("--series", help="only this series (A, B, T, H, G)")
    te.set_defaults(func=cmd_test)

    st = sub.add_parser("stiffness", parents=[port], help="measure the rig's own stiffness with a steel dummy coupon")
    st.add_argument("--max-mm", type=float, default=2)
    st.add_argument("--speed", type=float, default=0.5)
    st.set_defaults(func=cmd_stiffness)

    pt = sub.add_parser("plot", help="force-extension curves to one SVG")
    pt.add_argument("curves", nargs="+")
    pt.add_argument("-o", "--output", default="curves.svg")
    pt.add_argument("--title", default="Force vs extension")
    pt.set_defaults(func=cmd_plot)

    an = sub.add_parser("analyze", help="summarise a results CSV")
    an.add_argument("results")
    an.add_argument("--plates", help="print_log.csv, to add the material and waste summary")
    an.add_argument("--out-dir")
    an.set_defaults(func=cmd_analyze)

    ad = sub.add_parser("advise", help="recommend settings from measured data")
    ad.add_argument("results")
    ad.add_argument("--rigid", required=True, help="rigid material, e.g. PLA, PETG, ASA")
    ad.add_argument("--heat", action="store_true", help="only heat-soaked results")
    ad.add_argument("--min-n", type=int, default=3)
    ad.set_defaults(func=cmd_advise)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
