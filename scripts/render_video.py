"""Video of a simulated pull test on the rig: Blender (EEVEE) frames + a live force plot, encoded with ffmpeg.

    python3 scripts/render_video.py [--fast] [--frames=A:B] [--keep DIR]

Writes img/pull_test.mp4 (1080p) and img/pull_test.gif (small, for the README).
Needs OpenSCAD, Blender 4.2+, Pillow and ffmpeg. The values shown are illustrative (scripts/pull_sim.py), not measured.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import pull_sim as sim  # noqa: E402
from render_rig import COMPONENTS, find_blender  # noqa: E402
from rigidflex.scad import find_openscad  # noqa: E402

INK = (27, 33, 41)
MUTED = (93, 102, 114)
TPU = (232, 119, 46)
RIGID = (79, 126, 168)
RED = (196, 43, 28)


def font(size: int, bold: bool = False):
    for path, idx in (("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0),
                      ("/usr/share/fonts/truetype/dejavu/DejaVuSans" + ("-Bold" if bold else "") + ".ttf", 0)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except OSError:
            continue
    return ImageFont.load_default()


def overlay(frame: Image.Image, t: float, data) -> Image.Image:
    W, H = frame.size
    broken = t > sim.T_BREAK + sim.STOP_AFTER / 2
    s = W / 1920
    img = frame.convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    px = lambda v: int(round(v * s))  # noqa: E731

    # one card, top left: title, live readout and the force plot (fades in when the motor starts)
    a = max(0.0, min(1.0, (t - (sim.T_IDLE - 0.5)) / 0.5))
    x0, y0 = px(48), px(44)
    x1, y1 = x0 + px(600), y0 + (px(500) if a > 0 else px(112))
    d.rounded_rectangle([x0, y0, x1, y1], px(18), fill=(255, 254, 251, 232))
    d.rounded_rectangle([x0 + px(28), y0 + px(30), x0 + px(42), y0 + px(52)], px(3), fill=RIGID)
    d.rounded_rectangle([x0 + px(44), y0 + px(30), x0 + px(58), y0 + px(52)], px(3), fill=TPU)
    d.text((x0 + px(72), y0 + px(24)), "rigidflex pull rig", font=font(px(32), True), fill=INK)
    d.text((x0 + px(28), y0 + px(68)), "Simulated test at real speed · illustrative values", font=font(px(22)), fill=MUTED)
    if a > 0:
        ink = lambda c: (*c, int(255 * a))  # noqa: E731
        gx0, gy0, gx1, gy1 = x0 + px(72), y0 + px(232), x1 - px(30), y1 - px(66)
        XM, FM = 20.0, 300.0
        X = lambda v: gx0 + (gx1 - gx0) * v / XM  # noqa: E731
        Y = lambda v: gy1 - (gy1 - gy0) * v / FM  # noqa: E731
        d.line([x0 + px(28), y0 + px(112), x1 - px(28), y0 + px(112)], fill=ink((225, 221, 212)), width=max(1, px(1.5)))
        for f in range(0, 301, 100):
            d.line([gx0, Y(f), gx1, Y(f)], fill=ink((225, 221, 212)), width=max(1, px(1.5)))
            d.text((gx0 - px(12), Y(f)), f"{f}", font=font(px(18)), fill=ink(MUTED), anchor="rm")
        for x in range(0, 21, 5):
            d.text((X(x), gy1 + px(14)), f"{x}", font=font(px(18)), fill=ink(MUTED), anchor="mt")
        d.text(((gx0 + gx1) / 2, gy1 + px(38)), "extension, mm", font=font(px(18)), fill=ink(MUTED), anchor="mt")
        d.text((gx0, gy0 - px(26)), "force, N", font=font(px(18)), fill=ink(MUTED), anchor="lm")
        pts = [(X(x), Y(max(f, 0))) for (ts, x, f) in data if ts <= t]
        if len(pts) > 1:
            d.line(pts, fill=ink(TPU), width=px(4), joint="curve")
        if pts:
            cx, cy = pts[-1]
            d.ellipse([cx - px(7), cy - px(7), cx + px(7), cy + px(7)], fill=ink(TPU), outline=ink((255, 255, 255)), width=px(2))
        cur_f = data[len(pts) - 1][2] if pts else 0.0
        cur_x = data[len(pts) - 1][1] if pts else 0.0
        d.text((x0 + px(28), y0 + px(132)), f"{max(cur_f, 0):.0f} N", font=font(px(46), True), fill=ink(INK))
        d.text((x0 + px(250), y0 + px(132)), f"{cur_x:.1f} mm", font=font(px(46), True), fill=ink(INK))
        peak = max((p for p in data if p[0] <= t), key=lambda p: p[2], default=None)
        if broken and peak:
            d.line([X(peak[1]), Y(peak[2]), X(peak[1]), gy1], fill=RED, width=px(2))
            d.text((X(peak[1]) - px(10), Y(peak[2]) - px(12)), f"break at {peak[2]:.0f} N", font=font(px(20), True), fill=RED, anchor="rb")

    # caption, bottom left
    if t < sim.T_IDLE + 0.3:
        cap = "50 kg load cell · ESP32 · NEMA17 and a self-locking T8 lead screw"
    elif not broken:
        cap = "Pulling at a constant 2 mm/s · 80 force readings per second"
    else:
        cap = "Bond failure detected: the motor stops and the whole curve is saved"
    tw = d.textlength(cap, font=font(px(30), True))
    d.rounded_rectangle([px(48), H - px(124), px(48) + tw + px(56), H - px(48)], px(18), fill=(27, 33, 41, 225))
    d.text((px(76), H - px(86)), cap, font=font(px(30), True), fill=(255, 255, 255), anchor="lm")
    return Image.alpha_composite(img, layer).convert("RGB")


def main() -> None:
    fast = "--fast" in sys.argv
    passthrough = [a for a in sys.argv[1:] if a.startswith("--frames=")] + (["--fast"] if fast else [])
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    tmp = Path(keep) if keep else Path(tempfile.mkdtemp())
    tmp.mkdir(parents=True, exist_ok=True)
    openscad = find_openscad()
    for name in COMPONENTS:
        out = tmp / f"{name}.stl"
        if not out.exists():
            subprocess.run([openscad, "-o", str(out), "-D", f'component="{name}"', str(ROOT / "scad/pull_rig.scad")],
                           check=True, capture_output=True)
    subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(ROOT / "scripts/blender_anim.py"),
                    "--", str(tmp), str(tmp), *passthrough], check=True)
    data = sim.samples()
    comp = tmp / "comp"
    comp.mkdir(exist_ok=True)
    frames = sorted((tmp / "frames").glob("f_*.png"))
    for p in frames:
        n = int(p.stem.split("_")[1])
        overlay(Image.open(p), n / sim.FPS, data).save(comp / f"c_{n:04d}.png")
    if not frames or any(a.startswith("--frames=") for a in passthrough):
        print("frames in", comp)
        return
    ff = shutil.which("ffmpeg") or "ffmpeg"
    first = min(int(p.stem.split("_")[1]) for p in frames)
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(sim.FPS), "-start_number", str(first),
                    "-i", str(comp / "c_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21",
                    "-preset", "slow", "-movflags", "+faststart", str(ROOT / "img/pull_test.mp4")], check=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(ROOT / "img/pull_test.mp4"), "-vf",
                    "fps=10,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                    str(ROOT / "img/pull_test.gif")], check=True)
    print("wrote img/pull_test.mp4 and img/pull_test.gif")


if __name__ == "__main__":
    main()
