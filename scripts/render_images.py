"""Regenerate every image in img/ from the OpenSCAD sources.

    python3 scripts/render_images.py [--banner-only]

Needs OpenSCAD and Pillow. Two-material parts are exported body by body and
re-coloured, because OpenSCAD's preview loses colours inside intersections.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rigidflex.scad import find_openscad  # noqa: E402

SCAD = ROOT / "scad"
IMG = ROOT / "img"
OPENSCAD = find_openscad()
TOP = "0,0,0,0,0,0,0"
ISO = "0,0,0,60,0,20,0"


def _run(args: list[str]) -> None:
    subprocess.run([OPENSCAD, *args], check=True, capture_output=True)


def _defs(params: dict[str, object]) -> list[str]:
    out = []
    for k, v in params.items():
        v = f'"{v}"' if isinstance(v, str) else ("true" if v is True else "false" if v is False else v)
        out += ["-D", f"{k}={v}"]
    return out


def crop(path: Path, pad: int = 24) -> None:
    im = Image.open(path)
    if im.mode == "RGBA":  # transparent studio render: crop to what is visible (part + shadow)
        bb = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        im.crop((max(bb[0] - pad, 0), max(bb[1] - pad, 0), min(bb[2] + pad, im.width), min(bb[3] + pad, im.height))).save(path)
        return
    im = im.convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    bb = ImageChops.difference(im, bg).getbbox()
    im.crop((max(bb[0] - pad, 0), max(bb[1] - pad, 0), min(bb[2] + pad, im.width), min(bb[3] + pad, im.height))).save(path)


def two_material(scad: str, params: dict[str, object], out: str, view: str, samples: int = 160,
                 parts: dict[str, str] | None = None) -> None:
    """Studio render in Blender (scripts/blender_part.py): rigid = blue, flex = orange TPU 95A, third = yellow TPU 85A."""
    parts = parts or {"rigid": "rigid", "flex": "flex"}
    with tempfile.TemporaryDirectory() as tmp:
        for name, part in parts.items():
            _run(["-o", f"{tmp}/{name}.stl", *_defs({**params, "part": part}), str(SCAD / scad)])
        subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(ROOT / "scripts/blender_part.py"),
                        "--", tmp, str(IMG / out), view, str(samples)], check=True, capture_output=True)
    crop(IMG / out, pad=10)


def find_blender() -> str:
    import os
    import shutil
    for c in (os.environ.get("BLENDER"), shutil.which("blender"), "/Applications/Blender.app/Contents/MacOS/Blender"):
        if c and Path(c).exists():
            return c
    raise SystemExit("Blender not found; set BLENDER=/path/to/blender")


def single(scad: str, params: dict[str, object], out: str, camera: str, size=(2400, 1200)) -> None:
    _run(["-o", str(IMG / out), "--preview", f"--imgsize={size[0]},{size[1]}", "--viewall", "--autocenter",
          f"--camera={camera}", "--colorscheme=Tomorrow", *_defs(params), str(SCAD / scad)])
    crop(IMG / out)


def banner() -> None:
    try:
        font = lambda s, i: ImageFont.truetype("/System/Library/Fonts/Avenir Next.ttc", s, index=i)  # noqa: E731
        font(10, 0)
    except OSError:
        font = lambda s, i: ImageFont.load_default(size=s)  # noqa: E731
    W, H = 1600, 700
    im = Image.new("RGB", (W, H), (18, 24, 32))
    d = ImageDraw.Draw(im)

    def card(name: str, box: tuple[int, int, int, int]) -> None:
        r = Image.open(IMG / name).convert("RGBA")
        r.thumbnail((box[2] - 24, box[3] - 24))
        c = Image.new("RGB", box[2:], (247, 247, 247))
        c.paste(r, ((box[2] - r.width) // 2, (box[3] - r.height) // 2), r)
        m = Image.new("L", c.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, c.width - 1, c.height - 1], 16, fill=255)
        im.paste(c, box[:2], m)

    def photo(name: str, box: tuple[int, int, int, int], radius: int = 14, region=None, top_align=False, pad=0) -> None:
        # fill the box (cover crop), rounded corners
        r = Image.open(IMG / name).convert("RGB")
        if region:
            r = r.crop(region)
        if pad:  # breathing room around a screenshot, in the page's own background colour
            bg = Image.new("RGB", (r.width + 2 * pad, r.height + pad), r.getpixel((r.width // 2, r.height - 2)))
            bg.paste(r, (pad, pad))
            r = bg
        scale = max(box[2] / r.width, box[3] / r.height)
        r = r.resize((round(r.width * scale), round(r.height * scale)), Image.LANCZOS)
        left = (r.width - box[2]) // 2
        top = 0 if top_align else (r.height - box[3]) // 2
        r = r.crop((left, top, left + box[2], top + box[3]))
        m = Image.new("L", r.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, r.width - 1, r.height - 1], radius, fill=255)
        im.paste(r, box[:2], m)

    orange, grey, white = (234, 107, 40), (150, 162, 176), (255, 255, 255)
    d.text((80, 62), "SNAPMAKER U1 · RIGID + TPU", font=font(24, 2), fill=orange)
    d.text((76, 94), "rigidflex", font=font(100, 2), fill=white)
    d.text((80, 228), "Rigid + TPU in one print, measured.", font=font(38, 0), fill=(225, 231, 238))
    # call to action: the live configurator
    d.rounded_rectangle([80, 292, 652, 366], 37, fill=orange)
    d.polygon([(112, 313), (112, 345), (138, 329)], fill=white)
    d.text((154, 329), "Try it in your browser", font=font(32, 2), fill=white, anchor="lm")
    d.text((80, 396), "Configure · see it in 3D · download a U1-ready 3MF", font=font(24, 0), fill=grey)
    d.text((80, 430), "Motorised pull rig · 180 coupons · open data", font=font(24, 0), fill=grey)
    # simulated test frame and the three-material coupon
    photo("pull_test_frame.jpg", (80, 486, 360, 158), region=(0, 30, 1920, 870))
    card("G_graded.png", (460, 486, 300, 158))
    d.text((80, 652), "Pull rig, simulated test", font=font(18, 0), fill=grey)
    d.text((460, 652), "Graded joint · 3 materials", font=font(18, 0), fill=grey)
    # the configurator in a browser frame
    bx, by, bw, bh = 840, 62, 690, 582
    d.rounded_rectangle([bx, by, bx + bw, by + bh], 16, fill=(236, 233, 226))
    for i, c in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse([bx + 20 + i * 22, by + 16, bx + 32 + i * 22, by + 28], fill=c)
    d.rounded_rectangle([bx + 100, by + 10, bx + bw - 20, by + 34], 12, fill=(255, 255, 255))
    d.text((bx + 116, by + 22), "garage78.github.io/rigidflex", font=font(16, 0), fill=(93, 102, 114), anchor="lm")
    photo("web_grommet.png", (bx + 1, by + 44, bw - 2, bh - 45), radius=12, top_align=True, pad=18)
    im.save(IMG / "banner.jpg", quality=90)


def main() -> None:
    IMG.mkdir(exist_ok=True)
    if "--banner-only" in sys.argv:
        banner()
        return
    for joint in ("flat", "sawtooth", "dovetail"):
        two_material("coupons.scad", {"coupon": "A", "joint": joint}, f"A_{joint}.png", "top")
    two_material("coupons.scad", {"coupon": "B", "rigid_below": False}, "B.png", "iso")
    two_material("coupons.scad", {"coupon": "A", "joint": "flat", "buffer": 6}, "G_graded.png", "top",
                 parts={"rigid": "rigid", "flex": "buffer", "third": "flex"})
    two_material("grommet.scad", {}, "grommet.png", "iso")
    two_material("grommet.scad", {"three": True}, "grommet_3mat.png", "iso", parts={"rigid": "rigid", "flex": "flex", "third": "soft"})
    two_material("soft_jaw.scad", {}, "soft_jaw.png", "iso")
    # img/pull_rig*.jpg come from scripts/render_rig.py (Blender)
    banner()
    print("Images written to", IMG)


if __name__ == "__main__":
    main()
