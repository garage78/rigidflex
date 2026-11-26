"""Animated pull test on the rig (EEVEE). Run through scripts/render_video.py.

Reuses the still-render scene (blender_scene.py), then animates the carriage, the coupon's TPU half
(stretch, then spring-back after the break), the pulleys and the lead-screw thread, and the camera.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pull_sim as sim  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
sys.argv.append("--no-stills")
scene_file = HERE / "blender_scene.py"
exec(compile(scene_file.read_text(), str(scene_file), "exec"))  # defines objs, sc, ...

stl_dir, out_dir = Path(args[0]), Path(args[1])
FAST = "--fast" in args


def world_center(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return sum(pts, Vector()) / 8


def select_only(o):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def split_loose(o):
    select_only(o)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return list(bpy.context.selected_objects)


# ---------- what moves with the carriage ----------
moving = [objs["carriage"], objs["brass_nut"]]
for name in ("pins", "pin_nuts"):
    moving += [p for p in split_loose(objs[name]) if world_center(p).x > sim.JOINT_X]
base_x = {o.name: o.location.x for o in moving}

# ---------- the TPU half: a shape key stretches its gauge section ----------
tpu = objs["coupon_tpu"]
D_MAX = sim.X_BREAK * 0.001
tpu.shape_key_add(name="Basis")
key = tpu.shape_key_add(name="stretch")
x0, x1 = sim.JOINT_X + 0.00005, sim.GAUGE_END_X
for v, kv in zip(tpu.data.vertices, key.data):
    x = (tpu.matrix_world @ v.co).x
    shift = 0.0 if x <= x0 else D_MAX if x >= x1 else D_MAX * (x - x0) / (x1 - x0)
    kv.co = v.co + Vector((shift, 0, 0))
key.slider_max = 1.0
tpu_x0 = tpu.location.x

# ---------- spinning parts (origins on their axes) ----------
spin = {}
for name, ratio in (("pulley60", 1.0), ("pulley20", 3.0), ("motor_shaft", 3.0)):
    o = objs.get(name)
    if not o:
        continue
    c = world_center(o)
    sc.cursor.location = c
    select_only(o)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    spin[o] = ratio
thread_map = next(n for n in LEAD.node_tree.nodes if n.type == "MAPPING")
thread_scale = thread_map.inputs["Scale"].default_value[0]

# ---------- keyframes, one per frame ----------
F = sim.frames()
sc.frame_start, sc.frame_end = 0, F - 1
sc.render.fps = sim.FPS
for f in range(F):
    t = f / sim.FPS
    d = sim.displacement(t) * 0.001
    s = sim.stretch(t) * 0.001
    for o in moving:
        o.location.x = base_x[o.name] + d
        o.keyframe_insert("location", index=0, frame=f)
    key.value = s / D_MAX
    key.keyframe_insert("value", frame=f)
    tpu.location.x = tpu_x0 + d - s
    tpu.keyframe_insert("location", index=0, frame=f)
    turns = sim.displacement(t) / 2.0          # T8 x 2 mm: one turn of the screw per 2 mm
    for o, ratio in spin.items():
        o.rotation_euler.x = 2 * math.pi * turns * ratio
        o.keyframe_insert("rotation_euler", index=0, frame=f)
    thread_map.inputs["Location"].default_value[0] = -thread_scale * d
    thread_map.inputs["Location"].keyframe_insert("default_value", index=0, frame=f)

for o in bpy.data.objects:
    if o.animation_data and o.animation_data.action:
        for fc in getattr(o.animation_data.action, "fcurves", []):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

# ---------- camera: wide establishing shot, then into the coupon ----------
bpy.ops.object.empty_add(location=(0.34, 0.0, 0.02))
tgt = bpy.context.object
bpy.ops.object.camera_add(location=(0.02, -0.62, 0.42))
cam = bpy.context.object
cam.data.lens = 32
tc = cam.constraints.new("TRACK_TO")
tc.target = tgt
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
cam.data.dof.use_dof = True
cam.data.dof.focus_object = tgt
cam.data.dof.aperture_fstop = 9.0
sc.camera = cam
shots = [  # (seconds, camera, target)
    (0.0, (0.02, -0.62, 0.42), (0.34, 0.0, 0.02)),
    (1.2, (0.03, -0.60, 0.40), (0.34, 0.0, 0.02)),
    (3.6, (0.215, -0.42, 0.26), (0.330, 0.0, 0.075)),
    (sim.T_BREAK - 0.6, (0.262, -0.30, 0.185), (0.322, 0.0, 0.072)),
    (sim.T_END, (0.268, -0.292, 0.18), (0.324, 0.0, 0.072)),
]
for t, c, g in shots:
    f = round(t * sim.FPS)
    cam.location = c
    tgt.location = g
    cam.keyframe_insert("location", frame=f)
    tgt.keyframe_insert("location", frame=f)

# ---------- EEVEE ----------
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE_NEXT"
ee = sc.eevee
ee.taa_render_samples = 8 if FAST else 48
for attr, val in (("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    if hasattr(ee, attr):
        setattr(ee, attr, val)
sc.render.resolution_x, sc.render.resolution_y = (960, 540) if FAST else (1920, 1080)
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"
frames_dir = out_dir / "frames"
frames_dir.mkdir(parents=True, exist_ok=True)
sc.render.filepath = str(frames_dir / "f_")
only = [a for a in args if a.startswith("--frames=")]
if only:
    a, b = map(int, only[0].split("=")[1].split(":"))
    sc.frame_start, sc.frame_end = a, b
bpy.ops.render.render(animation=True)
