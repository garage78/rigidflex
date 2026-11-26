"""Summarise bond-test results: one row per coupon in, one row per condition out."""
from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

# Columns that define a test condition (everything that was varied on purpose).
CONDITION_COLS = [
    "series", "rigid", "tpu", "joint", "overlap_mm",
    "tpu_temp_c", "toolchange_order", "conditioning",
]
REQUIRED_COLS = CONDITION_COLS + ["specimen", "peak_force_n", "failure_mode", "width_mm"]
FAILURE_MODES = {"bond", "tpu", "rigid", "grip"}

# Two-sided 95 % t critical values, df 1..30 (beyond 30 use 1.96).
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t95(df: int) -> float:
    return _T95[df - 1] if 1 <= df <= 30 else 1.96


EXTRA_COLS = ["extension_mm", "energy_j", "stiffness_n_mm"]   # filled in by `rigidflex test` (load-cell rig)


@dataclass
class Condition:
    key: tuple[str, ...]
    forces: list[float]
    per_width: list[float]
    modes: Counter
    extras: dict[str, list[float]] | None = None

    def extra_mean(self, col: str) -> float | None:
        v = (self.extras or {}).get(col) or []
        return statistics.fmean(v) if len(v) == self.n else None

    @property
    def n(self) -> int:
        return len(self.forces)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.forces)

    @property
    def sd(self) -> float:
        return statistics.stdev(self.forces) if self.n > 1 else float("nan")

    @property
    def ci95(self) -> float:
        return t95(self.n - 1) * self.sd / math.sqrt(self.n) if self.n > 1 else float("nan")

    @property
    def mean_per_width(self) -> float:
        return statistics.fmean(self.per_width)

    @property
    def bond_failure_share(self) -> float:
        return self.modes.get("bond", 0) / self.n

    def as_dict(self) -> dict[str, object]:
        d: dict[str, object] = dict(zip(CONDITION_COLS, self.key))
        d.update(
            n=self.n,
            mean_n=round(self.mean, 1),
            sd_n=round(self.sd, 1) if self.n > 1 else "",
            ci95_n=round(self.ci95, 1) if self.n > 1 else "",
            cv_pct=round(100 * self.sd / self.mean, 1) if self.n > 1 and self.mean else "",
            mean_n_per_mm=round(self.mean_per_width, 2),
            bond_failures=self.modes.get("bond", 0),
            tpu_failures=self.modes.get("tpu", 0),
            rigid_failures=self.modes.get("rigid", 0),
            grip_failures=self.modes.get("grip", 0),
        )
        for col, nd in (("extension_mm", 2), ("energy_j", 3), ("stiffness_n_mm", 1)):
            m = self.extra_mean(col)
            d[f"mean_{col}"] = round(m, nd) if m is not None else ""
        return d


def load(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path} has no data rows")
    missing = [c for c in REQUIRED_COLS if c not in rows[0]]
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")
    # rows without a force are coupons not tested yet (e.g. a campaign sheet in progress)
    rows = [r for r in rows if r["peak_force_n"].strip()]
    if not rows:
        raise ValueError(f"{path} has no tested coupons yet (peak_force_n is empty everywhere)")
    for i, r in enumerate(rows, start=2):
        mode = r["failure_mode"].strip().lower()
        if mode not in FAILURE_MODES:
            raise ValueError(f"line {i}: failure_mode must be one of {sorted(FAILURE_MODES)}, got {r['failure_mode']!r}")
        float(r["peak_force_n"]), float(r["width_mm"])  # raises on bad numbers
    return rows


def summarise(rows: list[dict[str, str]]) -> list[Condition]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        groups[tuple(r[c].strip() for c in CONDITION_COLS)].append(r)
    out = []
    for key, rs in groups.items():
        forces = [float(r["peak_force_n"]) for r in rs]
        per_width = [float(r["peak_force_n"]) / float(r["width_mm"]) for r in rs]
        modes = Counter(r["failure_mode"].strip().lower() for r in rs)
        extras = {c: [float(r[c]) for r in rs if (r.get(c) or "").strip()] for c in EXTRA_COLS}
        out.append(Condition(key, forces, per_width, modes, extras))
    out.sort(key=lambda c: (c.key[0], c.key[1], -c.mean))
    return out


def write_summary_csv(conditions: list[Condition], path: str | Path) -> None:
    rows = [c.as_dict() for c in conditions]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def markdown_report(conditions: list[Condition], source: str) -> str:
    lines = [
        "# Rigid + TPU bond test: summary",
        "",
        f"Source: `{source}`. Mean peak force ± SD, 95 % CI of the mean, and how each coupon failed.",
        "A high share of `bond` failures means the interface is the weak point; `tpu` failures mean the bond",
        "is stronger than the TPU itself, which is the best possible result.",
        "",
        "| Series | Rigid | TPU | Joint | Overlap | TPU °C | Order | Cond. | n | Mean N | SD | ±CI95 | N/mm | Ext. mm | Energy J | Failures (bond/tpu/rigid/grip) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in conditions:
        d = c.as_dict()
        lines.append(
            f"| {d['series']} | {d['rigid']} | {d['tpu']} | {d['joint']} | {d['overlap_mm']} | {d['tpu_temp_c']} | "
            f"{d['toolchange_order']} | {d['conditioning']} | {d['n']} | {d['mean_n']} | {d['sd_n']} | "
            f"{d['ci95_n']} | {d['mean_n_per_mm']} | {d['mean_extension_mm']} | {d['mean_energy_j']} | "
            f"{d['bond_failures']}/{d['tpu_failures']}/{d['rigid_failures']}/{d['grip_failures']} |"
        )
    small = [c for c in conditions if c.n < 3]
    if small:
        lines += ["", f"Warning: {len(small)} condition(s) have fewer than 3 coupons; treat them as indicative only."]
    return "\n".join(lines) + "\n"


def waste_report(path: str | Path) -> str:
    """Summarise print_log.csv: material in parts vs. waste on the U1, vs. a single-nozzle printer's flush estimate."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("parts_g") or "").strip() and (r.get("u1_waste_g") or "").strip()]
    if not rows:
        return "## Print log\n\nNo plates logged yet.\n"
    parts = sum(float(r["parts_g"]) for r in rows)
    waste = sum(float(r["u1_waste_g"]) for r in rows)
    minutes = sum(float(r["print_time_min"]) for r in rows if (r.get("print_time_min") or "").strip())
    lines = ["## Print log: material and time", "",
             f"{len(rows)} plate(s) logged: {parts:.0f} g in coupons, {waste:.0f} g of waste on the U1 "
             f"({100 * waste / (parts + waste):.1f} % of the filament used), {minutes / 60:.1f} h of printing."]
    single = [r for r in rows if (r.get("single_nozzle_flush_g") or "").strip()]
    if single:
        s_flush = sum(float(r["single_nozzle_flush_g"]) for r in single)
        s_waste = sum(float(r["u1_waste_g"]) for r in single)
        lines.append(f"Same {len(single)} plate(s) sliced for a single-nozzle printer with a filament changer: "
                     f"{s_flush:.0f} g of flush (slicer estimate) vs {s_waste:.0f} g weighed on the U1.")
    return "\n".join(lines) + "\n"
