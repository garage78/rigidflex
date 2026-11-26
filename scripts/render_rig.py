"""Photo-style render of the pull rig with Blender (Cycles).

    python3 scripts/render_rig.py            # writes img/pull_rig.jpg, pull_rig_detail.jpg, pull_rig_drive.jpg [--fast]

Needs OpenSCAD and Blender 4.2+ (set BLENDER=/path/to/blender if it is not in the usual place).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rigidflex.scad import find_openscad  # noqa: E402

COMPONENTS = ["board", "rails", "ticks", "ebox", "ebox_lid", "box_screws", "button_bezel", "button_cap",
              "cell_anchor", "anchor_hw", "load_cell", "cell_potting", "cell_gland", "cell_label", "cell_label_text", "cables", "fork_a",
              "coupon_rigid", "coupon_tpu", "pins", "pin_nuts", "carriage", "brass_nut", "screw", "collar",
              "bearing", "motor_end", "pulley60", "pulley20", "belt", "motor_body", "motor_caps", "motor_shaft"]


def find_blender() -> str:
    for c in (os.environ.get("BLENDER"), shutil.which("blender"), "/Applications/Blender.app/Contents/MacOS/Blender"):
        if c and Path(c).exists():
            return c
    raise SystemExit("Blender not found; set BLENDER=/path/to/blender")


def main() -> None:
    openscad = find_openscad()
    with tempfile.TemporaryDirectory() as tmp:
        for name in COMPONENTS:
            out = Path(tmp) / f"{name}.stl"
            subprocess.run([openscad, "-o", str(out), "-D", f'component="{name}"', str(ROOT / "scad/pull_rig.scad")],
                           check=True, capture_output=True)
        subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(ROOT / "scripts/blender_scene.py"),
                        "--", tmp, tmp, *(["--fast"] if "--fast" in sys.argv else [])], check=True)
        from PIL import Image
        for name in ("pull_rig", "pull_rig_detail", "pull_rig_drive"):
            Image.open(Path(tmp) / f"{name}.png").convert("RGB").save(ROOT / "img" / f"{name}.jpg", quality=88, optimize=True)


if __name__ == "__main__":
    main()
