"""The simulated pull test shown in the rig video (illustrative values, not a measurement).

Shared by scripts/blender_anim.py (motion) and scripts/render_video.py (force plot), so both stay in step.
A PETG + TPU 95A coupon: toe region, a stiffening TPU curve, adhesive failure at the joint after 16 mm.
"""
import math
import random

FPS = 24
T_IDLE = 1.5          # s before the motor starts
SPEED = 2.0           # mm/s, as in the protocol
X_BREAK = 16.0        # mm of extension at the bond failure
STOP_AFTER = 0.04     # s the firmware needs to see the drop (3 samples at 80 Hz)
SNAP = 0.18           # s for the free TPU half to spring back
T_END = 12.5          # s, length of the clip
JOINT_X = 0.311       # m, joint plane in the rig model (scad/pull_rig.scad)
GAUGE_END_X = 0.336   # m, end of the TPU gauge section
T_BREAK = T_IDLE + X_BREAK / SPEED


def frames() -> int:
    return int(round(T_END * FPS))


def displacement(t: float) -> float:
    """Carriage travel in mm at time t."""
    if t <= T_IDLE:
        return 0.0
    if t <= T_BREAK:
        return (t - T_IDLE) * SPEED
    return X_BREAK + min(t - T_BREAK, STOP_AFTER) * SPEED


def stretch(t: float) -> float:
    """Extension carried by the TPU half in mm (it springs back after the break)."""
    if t <= T_BREAK:
        return displacement(t)
    u = min((t - T_BREAK) / SNAP, 1.0)
    return X_BREAK * (1 - u) ** 3


def force(x: float, broken: bool) -> float:
    """Force in N at extension x (mm)."""
    if broken:
        return 1.5
    return max(0.0, 250 * math.tanh(max(0.0, x - 0.3) / 6.0))


def samples():
    """(t, x, F) at the 80 Hz the firmware streams, with load-cell noise, up to the stop."""
    rng = random.Random(7)
    out = []
    t = T_IDLE
    while t <= T_BREAK + STOP_AFTER + 1e-9:
        x = displacement(t)
        broken = t > T_BREAK
        out.append((t, x, force(x, broken) + rng.gauss(0, 0.6)))
        t += 1 / 80
    return out
