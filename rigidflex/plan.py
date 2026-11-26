"""Generate a complete test campaign: plates, a pre-filled results sheet, a print log and a checklist.

Each coupon geometry is printed once per rigid material, so the plates are generated once
per geometry and listed for each material. The results CSV has one row per coupon with every
condition column already filled in; `rigidflex test` (or the tester by hand) fills in the rest.

Spool layout on the U1 for the whole campaign:
  extruder 1  rigid (PLA / PETG / ASA, changed per plate)
  extruder 2  TPU 95A
  extruder 3  soft TPU 85A (series G and the three-material grommet only)
  extruder 4  free
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .analyze import REQUIRED_COLS

TPU = "TPU95A"
TPU_SOFT = "TPU85A"
COPIES = 5
SHEET_COLS = REQUIRED_COLS[:8] + ["specimen", "width_mm", "peak_force_n", "failure_mode",
                                  "extension_mm", "energy_j", "stiffness_n_mm", "curve", "notes", "plate"]
PRINT_LOG_COLS = ["series", "rigid", "plate", "tpu_temp_c", "print_time_min", "parts_g", "u1_waste_g",
                  "single_nozzle_flush_g", "toolchanges", "notes"]


@dataclass(frozen=True)
class Plate:
    file: str          # 3MF file name
    kind: str          # "A", "B" or "G"
    joint: str = ""    # A: flat / sawtooth / dovetail / orca-beam;  G: direct / graded
    overlap: float = 0
    order: str = ""

    @property
    def tools(self) -> int:
        return 3 if self.joint == "graded" else 2


@dataclass(frozen=True)
class Condition:
    series: str
    rigid: str
    plate: Plate
    tpu_temp: str
    conditioning: str

    @property
    def tpu(self) -> str:
        if self.plate.kind != "G":
            return TPU
        return f"{TPU}+{TPU_SOFT}" if self.plate.joint == "graded" else TPU_SOFT


def build(rigids=("PLA", "PETG", "ASA"), hot_rigids=("PETG", "ASA"),
          t_joint="dovetail", tpu_low=220, tpu_high=240, tpu_default=230,
          h_joint="dovetail", h_overlap=20.0, h_order="tpu-on-rigid") -> tuple[list[Plate], list[Condition]]:
    a_plates = {j: Plate(f"A_{j}.3mf", "A", joint=j) for j in ("flat", "sawtooth", "dovetail", "orca-beam")}
    b_plates = {(o, r): Plate(f"B_overlap{o:g}_{r}.3mf", "B", overlap=o, order=r)
                for o in (10.0, 20.0) for r in ("tpu-on-rigid", "rigid-on-tpu")}
    g_plates = {j: Plate(f"G_{j}.3mf", "G", joint=j) for j in ("direct", "graded")}
    conds: list[Condition] = []
    for rigid in rigids:
        for p in a_plates.values():
            conds.append(Condition("A", rigid, p, str(tpu_default), "48h-RT"))
        for p in b_plates.values():
            conds.append(Condition("B", rigid, p, str(tpu_default), "48h-RT"))
    for rigid in hot_rigids:
        for temp in (tpu_low, tpu_high):
            conds.append(Condition("T", rigid, a_plates[t_joint], str(temp), "48h-RT"))
        conds.append(Condition("H", rigid, a_plates[h_joint], str(tpu_default), "heat-80C-24h"))
        conds.append(Condition("H", rigid, b_plates[(h_overlap, h_order)], str(tpu_default), "heat-80C-24h"))
        for p in g_plates.values():
            conds.append(Condition("G", rigid, p, str(tpu_default), "48h-RT"))
    plates = list(a_plates.values()) + list(b_plates.values()) + list(g_plates.values())
    return plates, conds


def write_sheet(conds: list[Condition], path: Path, copies: int = COPIES) -> int:
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLS)
        w.writeheader()
        for c in conds:
            for i in range(1, copies + 1):
                row = {k: "" for k in SHEET_COLS}
                row.update({
                    "series": c.series, "rigid": c.rigid, "tpu": c.tpu,
                    "joint": "lap" if c.plate.kind == "B" else c.plate.joint,
                    "overlap_mm": f"{c.plate.overlap:g}" if c.plate.kind == "B" else "",
                    "tpu_temp_c": c.tpu_temp,
                    "toolchange_order": c.plate.order,
                    "conditioning": c.conditioning,
                    "specimen": i,
                    "plate": c.plate.file,
                })
                w.writerow(row)
                rows += 1
    return rows


def write_print_log(conds: list[Condition], path: Path) -> None:
    """One row per plate printed: time and waste, to compare the U1 with a single-nozzle printer."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRINT_LOG_COLS)
        w.writeheader()
        for c in conds:
            w.writerow({k: "" for k in PRINT_LOG_COLS} | {"series": c.series, "rigid": c.rigid,
                                                          "plate": c.plate.file, "tpu_temp_c": c.tpu_temp})


def write_checklist(conds: list[Condition], path: Path, copies: int = COPIES) -> None:
    lines = ["# Test campaign checklist", "",
             f"{len(conds)} plates to print × {copies} coupons = {len(conds) * copies} coupons.", "",
             "Spools: extruder 1 rigid, extruder 2 TPU 95A, extruder 3 TPU 85A (series G), extruder 4 free.",
             "Plates are in `plates/`. `rigidflex test results.csv --port ...` fills in `results.csv`;",
             "fill in `print_log.csv` (time, weighed waste) as each plate comes off the printer.", "",
             "| Series | Rigid | Plate | Tools | TPU °C | Conditioning | Printed | Conditioned | Tested |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in conds:
        lines.append(f"| {c.series} | {c.rigid} | `{c.plate.file}` | {c.plate.tools} | {c.tpu_temp} | {c.conditioning} | ☐ | ☐ | ☐ |")
    lines += ["", "Series T uses the A plate printed at a different TPU nozzle temperature: set it per plate in the slicer.",
              "Series H uses the same plates, re-tested after 24 h at 80 °C (see docs/protocol.md).",
              "Series G: `G_direct` is rigid + TPU 85A; `G_graded` puts a 6 mm band of TPU 95A in between (three extruders)."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
