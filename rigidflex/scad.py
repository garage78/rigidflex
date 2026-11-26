"""Run OpenSCAD to export each material body as its own STL."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .threemf import Triangle, read_stl

SCAD_DIR = Path(__file__).resolve().parent.parent / "scad"


def find_openscad() -> str:
    exe = shutil.which("openscad")
    if exe:
        return exe
    mac = Path("/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD")
    if mac.exists():
        return str(mac)
    raise RuntimeError("OpenSCAD not found. Install it from https://openscad.org and make sure `openscad` is on PATH.")


def _value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace('"', '\\"') + '"'
    return str(v)


def export_part(scad_file: str, part: str, params: dict[str, object]) -> list[Triangle]:
    """Export one body (`part` = "rigid" or "flex") of a .scad file and return its triangles."""
    src = SCAD_DIR / scad_file
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{part}.stl"
        cmd = [find_openscad(), "-o", str(out), "-D", f"part={_value(part)}"]
        for key, val in params.items():
            cmd += ["-D", f"{key}={_value(val)}"]
        cmd.append(str(src))
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out.exists():
            raise RuntimeError(f"OpenSCAD failed for {scad_file} ({part}):\n{res.stderr[-2000:]}")
        return read_stl(out)
