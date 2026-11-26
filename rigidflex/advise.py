"""Recommend joint and settings for a rigid material from measured data.

Works on any results CSV in the kit format: the project's validated dataset
once it is published, or your own measurements.
"""
from __future__ import annotations

from .analyze import Condition


def recommend(conditions: list[Condition], rigid: str, heat: bool = False, min_n: int = 3, top: int = 3) -> list[Condition]:
    """Best conditions for `rigid`, ranked by mean force, preferring joints that do not fail at the bond.

    heat=True keeps only heat-soaked results, for parts that will see high temperatures.
    """
    rigid = rigid.strip().lower()
    pool = [
        c for c in conditions
        if c.key[1].lower() == rigid and c.n >= min_n
        and (("heat" in c.key[7].lower()) if heat else True)
    ]
    # Rank: fewer bond failures first, then higher mean force.
    pool.sort(key=lambda c: (round(c.bond_failure_share, 2), -c.mean))
    return pool[:top]


def explain(c: Condition) -> str:
    series, rigid, tpu, joint, overlap, temp, order, cond = c.key
    parts = [f"{rigid} + {tpu}: joint={joint}"]
    if overlap:
        parts.append(f"overlap={overlap} mm")
    if temp:
        parts.append(f"TPU nozzle={temp} °C")
    if order:
        parts.append(f"toolchange order={order}")
    head = ", ".join(parts)
    sd = f" ± {c.sd:.0f}" if c.n > 1 else ""
    return (f"{head}\n    {c.mean:.0f}{sd} N over {c.n} coupons ({c.mean_per_width:.1f} N/mm), "
            f"{c.modes.get('bond', 0)}/{c.n} failed at the bond  [series {series}, {cond}]")
