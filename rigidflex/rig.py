"""The pull-test rig from the computer side: serial link, force-extension curves, metrics, guided session, plots.

pyserial is only needed to talk to real hardware (`pip install 'rigidflex[rig]'`); everything else,
including `rigidflex test --simulate`, runs on the standard library.
"""
from __future__ import annotations

import csv
import math
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

FAILURE_KEYS = {"b": "bond", "t": "tpu", "r": "rigid", "g": "grip"}
CURVE_COLS = ["extension_mm", "energy_j", "stiffness_n_mm", "curve"]


class RigError(RuntimeError):
    pass


@dataclass
class Curve:
    t_ms: list[float] = field(default_factory=list)
    x_mm: list[float] = field(default_factory=list)
    f_n: list[float] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)

    def add(self, t: float, x: float, f: float) -> None:
        self.t_ms.append(t)
        self.x_mm.append(x)
        self.f_n.append(f)


# ---------------------------------------------------------------- metrics

def metrics(c: Curve, rig_stiffness: float | None = None) -> dict[str, float]:
    """Peak force, extension at peak, energy to peak and initial stiffness of one pull.

    The carriage position includes the rig's own deflection; give `rig_stiffness` (N/mm, measured
    once with a steel dummy coupon) to subtract it. Pin slack at the start is removed with the usual
    toe compensation: the line fitted between 10 % and 40 % of the peak defines zero extension.
    """
    if len(c.f_n) < 3:
        raise ValueError("curve has fewer than 3 samples")
    x = list(c.x_mm)
    if rig_stiffness:
        x = [xi - fi / rig_stiffness for xi, fi in zip(x, c.f_n)]
    i_pk = max(range(len(c.f_n)), key=c.f_n.__getitem__)
    peak = c.f_n[i_pk]
    lo, hi = 0.10 * peak, 0.40 * peak
    pts = [(x[i], c.f_n[i]) for i in range(i_pk + 1) if lo <= c.f_n[i] <= hi]
    k = x0 = float("nan")
    if len(pts) >= 3:
        mx = sum(p[0] for p in pts) / len(pts)
        mf = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        if sxx > 0:
            k = sum((p[0] - mx) * (p[1] - mf) for p in pts) / sxx
            x0 = mx - mf / k if k > 0 else float("nan")
    if math.isnan(x0):
        x0 = x[0]
    energy = 0.0  # N·mm, trapezoids from the toe to the peak
    for i in range(1, i_pk + 1):
        if x[i] <= x0:
            continue
        xa = max(x[i - 1], x0)
        energy += 0.5 * (max(c.f_n[i - 1], 0) + max(c.f_n[i], 0)) * (x[i] - xa)
    return {"peak_force_n": peak, "extension_mm": x[i_pk] - x0, "energy_j": energy / 1000, "stiffness_n_mm": k}


# ---------------------------------------------------------------- files

def write_curve(path: Path, c: Curve) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        for k, v in c.meta.items():
            f.write(f"# {k}: {v}\n")
        w = csv.writer(f)
        w.writerow(["t_ms", "x_mm", "force_n"])
        for row in zip(c.t_ms, c.x_mm, c.f_n):
            w.writerow([f"{row[0]:.0f}", f"{row[1]:.3f}", f"{row[2]:.2f}"])
    return path


def read_curve(path: Path) -> Curve:
    c = Curve()
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    data = []
    for line in lines:
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            c.meta[k.strip()] = v.strip()
        elif line.strip():
            data.append(line)
    for r in csv.DictReader(data):
        c.add(float(r["t_ms"]), float(r["x_mm"]), float(r["force_n"]))
    return c


# ---------------------------------------------------------------- devices

class SerialRig:
    """The real rig, over USB serial (firmware/rigidflex_rig)."""

    def __init__(self, port: str, baud: int = 115200):
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise SystemExit("Talking to the rig needs pyserial:  pip install pyserial") from e
        self.s = serial.Serial(port, baud, timeout=1)
        time.sleep(2.0)                     # the ESP32 resets when the port opens
        self.s.reset_input_buffer()

    def _line(self, deadline: float) -> str:
        while time.monotonic() < deadline:
            raw = self.s.readline()
            if raw:
                line = raw.decode(errors="replace").strip()
                if line and not line.startswith("#"):
                    return line
        raise RigError("no answer from the rig (wrong port, or firmware not running?)")

    def command(self, cmd: str, timeout: float = 30) -> str:
        """Send one command; return every line up to and including the OK (e.g. the D lines of `watch`)."""
        self.s.write((cmd + "\n").encode())
        deadline = time.monotonic() + timeout
        out = []
        while True:
            line = self._line(deadline)
            if line.startswith("ERR"):
                raise RigError(line[4:])
            out.append(line)
            if line.startswith("OK"):
                return "\n".join(out)

    def run(self, max_mm: float, speed: float) -> tuple[Curve, dict[str, str]]:
        self.s.write(f"run {max_mm:g} {speed:g}\n".encode())
        deadline = time.monotonic() + max_mm / speed + 30
        c = Curve()
        while True:
            line = self._line(deadline)
            if line.startswith("ERR"):
                raise RigError(line[4:])
            if line.startswith("D,"):
                _, t, x, f = line.split(",")
                c.add(float(t), float(x), float(f))
            elif line.startswith("END,"):
                _, reason, peak, x_pk, x_end = line.split(",")
                return c, {"reason": reason, "peak_n": peak, "peak_x_mm": x_pk, "end_x_mm": x_end}

    def close(self) -> None:
        self.s.close()


class SimulatedRig:
    """Stand-in for the rig so the workflow can be tried without hardware. Numbers are made up."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def command(self, cmd: str, timeout: float = 0) -> str:
        return f"OK,{cmd.split()[0]},simulated"

    def run(self, max_mm: float, speed: float) -> tuple[Curve, dict[str, str]]:
        r = self.rng
        slack, k, fsat = r.uniform(0.2, 0.6), r.uniform(30, 45), r.uniform(150, 320)
        x_break = r.uniform(4, 25) if r.random() < 0.7 else float("inf")
        c, dt, i = Curve(), 1000 / 80, 0
        reason = "max"
        while True:
            x = i * dt / 1000 * speed
            if x >= max_mm:
                break
            f = 0.0 if x < slack else fsat * math.tanh(k * (x - slack) / fsat) + 2.0 * (x - slack)
            if x > x_break:
                f = r.uniform(0, 3)
            c.add(i * dt, x, f + r.gauss(0, 0.3))
            if x > x_break + 0.05:
                reason = "break"
                break
            i += 1
        pk = max(range(len(c.f_n)), key=c.f_n.__getitem__)
        return c, {"reason": reason, "peak_n": f"{c.f_n[pk]:.2f}", "peak_x_mm": f"{c.x_mm[pk]:.3f}", "end_x_mm": f"{c.x_mm[-1]:.3f}"}

    def close(self) -> None:
        pass


def rig_stiffness(c: Curve, lo: float = 50, hi: float = 300) -> float:
    """Slope (N/mm) of a pull on a steel dummy coupon between `lo` and `hi` newtons: the rig's own stiffness."""
    hi = min(hi, 0.9 * max(c.f_n))
    pts = [(x, f) for x, f in zip(c.x_mm, c.f_n) if lo <= f <= hi]
    if len(pts) < 5:
        raise ValueError(f"not enough points between {lo:g} and {hi:g} N")
    mx = sum(p[0] for p in pts) / len(pts)
    mf = sum(p[1] for p in pts) / len(pts)
    return sum((p[0] - mx) * (p[1] - mf) for p in pts) / sum((p[0] - mx) ** 2 for p in pts)


# ---------------------------------------------------------------- guided session

def _label(r: dict[str, str]) -> str:
    bits = [r["series"], r["rigid"], r.get("tpu", ""), r["joint"]]
    if r.get("overlap_mm"):
        bits.append(f"{r['overlap_mm']}mm")
    if r.get("toolchange_order"):
        bits.append(r["toolchange_order"])
    bits += [f"{r['tpu_temp_c']}C", r["conditioning"]]
    return " ".join(b for b in bits if b)


def _curve_name(r: dict[str, str]) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", _label(r).replace(" ", "_")) + f"_{r['specimen']}.csv"


def _save_sheet(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)   # never leaves a half-written sheet


def session(sheet: Path, rig, curves_dir: Path | None = None, max_mm: float = 40, speed: float = 2,
            rig_stiffness: float | None = None, series: str | None = None,
            ask: Callable[[str], str] = input, say: Callable[[str], None] = print) -> int:
    """Walk through every untested coupon in the sheet: measure, pull, classify, save. Returns coupons tested."""
    sheet = Path(sheet)
    curves_dir = Path(curves_dir or sheet.parent / "curves")
    with open(sheet, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for col in CURVE_COLS:
        if col not in fields:
            fields.append(col)
    todo = [r for r in rows if not r.get("peak_force_n", "").strip() and (not series or r["series"] == series)]
    say(f"{len(todo)} coupon(s) left to test in {sheet}. Press q at any prompt to stop; progress is saved after each coupon.")
    done = 0
    for r in todo:
        say("")
        say(f"Next: {_label(r)}  #{r['specimen']}   (plate {r.get('plate', '?')})")
        w = ask("  width at the joint, mm [Enter = 10.0, s = skip]: ").strip().lower()
        if w == "q":
            break
        if w == "s":
            continue
        try:
            width = float(w) if w else 10.0
        except ValueError:
            say("  not a number, skipping this coupon")
            continue
        if ask("  pin the coupon in, then Enter to pull: ").strip().lower() == "q":
            break
        curve, end = rig.run(max_mm, speed)
        m = metrics(curve, rig_stiffness)
        say(f"  {end['reason']}: peak {m['peak_force_n']:.1f} N at {m['extension_mm']:.1f} mm, "
            f"{m['energy_j']:.2f} J, stiffness {m['stiffness_n_mm']:.1f} N/mm")
        suggestion = "t" if end["reason"] == "max" else "b"
        while True:
            k = ask(f"  failure mode: [b]ond / [t]pu / [r]igid / [g]rip [Enter = {suggestion}]: ").strip().lower() or suggestion
            if k in FAILURE_KEYS or k == "q":
                break
        if k == "q":
            break
        curve.meta.update(condition=_label(r), specimen=r["specimen"], width_mm=f"{width:g}",
                          failure_mode=FAILURE_KEYS[k], end=end["reason"], speed_mm_s=f"{speed:g}")
        path = write_curve(curves_dir / _curve_name(r), curve)
        r.update(width_mm=f"{width:g}", peak_force_n=f"{m['peak_force_n']:.1f}", failure_mode=FAILURE_KEYS[k],
                 extension_mm=f"{m['extension_mm']:.2f}", energy_j=f"{m['energy_j']:.3f}",
                 stiffness_n_mm="" if math.isnan(m["stiffness_n_mm"]) else f"{m['stiffness_n_mm']:.1f}",
                 curve=os.path.relpath(path, sheet.parent))
        _save_sheet(sheet, fields, rows)
        done += 1
    say(f"\nTested {done} coupon(s). Run `rigidflex analyze {sheet}` for the summary.")
    return done


# ---------------------------------------------------------------- plot

PALETTE = ["#2563eb", "#ea580c", "#16a34a", "#9333ea", "#dc2626", "#0891b2", "#ca8a04", "#db2777", "#4b5563", "#65a30d"]


def _nice(v: float) -> float:
    e = 10 ** math.floor(math.log10(v))
    return next(m * e for m in (1, 2, 2.5, 5, 10) if m * e >= v)


def plot(paths: list[Path], out: Path, title: str = "Force vs extension") -> Path:
    """Overlay force-extension curves in one dependency-free SVG, one colour per condition."""
    curves = [read_curve(p) for p in paths]
    if not curves:
        raise ValueError("no curves to plot")
    groups: dict[str, str] = {}
    for c in curves:
        groups.setdefault(c.meta.get("condition", "curve"), PALETTE[len(groups) % len(PALETTE)])
    xmax = _nice(max(max(c.x_mm) for c in curves))
    fmax = _nice(max(max(c.f_n) for c in curves) * 1.05)
    W, Hh, L, R, T, B = 900, 560, 70, 250, 50, 60
    pw, ph = W - L - R, Hh - T - B

    def sx(v: float) -> float:
        return L + v / xmax * pw

    def sy(v: float) -> float:
        return T + ph - max(v, 0) / fmax * ph

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" font-family="Helvetica, Arial, sans-serif" font-size="13">',
         f'<rect width="{W}" height="{Hh}" fill="white"/>',
         f'<text x="{L}" y="30" font-size="17" font-weight="bold">{title}</text>']
    for i in range(6):
        xv, fv = xmax * i / 5, fmax * i / 5
        s.append(f'<line x1="{sx(xv):.1f}" y1="{T}" x2="{sx(xv):.1f}" y2="{T + ph}" stroke="#e5e7eb"/>')
        s.append(f'<text x="{sx(xv):.1f}" y="{T + ph + 20}" text-anchor="middle" fill="#374151">{xv:g}</text>')
        s.append(f'<line x1="{L}" y1="{sy(fv):.1f}" x2="{L + pw}" y2="{sy(fv):.1f}" stroke="#e5e7eb"/>')
        s.append(f'<text x="{L - 8}" y="{sy(fv) + 4:.1f}" text-anchor="end" fill="#374151">{fv:g}</text>')
    s.append(f'<rect x="{L}" y="{T}" width="{pw}" height="{ph}" fill="none" stroke="#9ca3af"/>')
    s.append(f'<text x="{L + pw / 2}" y="{Hh - 15}" text-anchor="middle">extension (mm)</text>')
    s.append(f'<text transform="translate(20,{T + ph / 2}) rotate(-90)" text-anchor="middle">force (N)</text>')
    for c in curves:
        step = max(1, len(c.x_mm) // 600)
        pts = " ".join(f"{sx(x):.1f},{sy(f):.1f}" for x, f in list(zip(c.x_mm, c.f_n))[::step])
        s.append(f'<polyline points="{pts}" fill="none" stroke="{groups[c.meta.get("condition", "curve")]}" '
                 f'stroke-width="1.6" stroke-opacity="0.85"/>')
    for i, (name, col) in enumerate(groups.items()):
        y = T + 10 + i * 22
        s.append(f'<line x1="{L + pw + 15}" y1="{y}" x2="{L + pw + 40}" y2="{y}" stroke="{col}" stroke-width="3"/>')
        s.append(f'<text x="{L + pw + 47}" y="{y + 4}" font-size="11">{name[:32]}</text>')
    s.append("</svg>")
    out = Path(out)
    out.write_text("\n".join(s), encoding="utf-8")
    return out
