"""Studio render of one two-material part (rigid.stl + flex.stl). Run through scripts/render_images.py.

blender -b --factory-startup -P blender_part.py -- <stl_dir> <out.png> <view: top|iso|low> [samples]
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
stl_dir, out, view = Path(args[0]), args[1], args[2]
samples = int(args[3]) if len(args) > 3 else 128


def mat(name, color, rough, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    return m


RIGID = mat("petg_blue", (0.015, 0.09, 0.42), 0.3, 0.2)
TPU = mat("tpu_orange", (0.92, 0.22, 0.01), 0.55)
SOFT = mat("tpu85_yellow", (0.98, 0.78, 0.0), 0.5)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
objs = []
for name, m in (("rigid", RIGID), ("flex", TPU), ("third", SOFT)):
    if not (stl_dir / f"{name}.stl").exists():
        continue
    bpy.ops.wm.stl_import(filepath=str(stl_dir / f"{name}.stl"), global_scale=0.001)
    o = bpy.context.selected_objects[0]
    o.data.materials.append(m)
    bpy.context.view_layer.objects.active = o
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    except Exception:
        bpy.ops.object.shade_smooth()
    bev = o.modifiers.new("bevel", "BEVEL")
    bev.width = 0.00025
    bev.segments = 2
    bev.limit_method = "ANGLE"
    objs.append(o)

pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, hi - lo
span = max(size.x, size.y, size.z)

bpy.ops.mesh.primitive_plane_add(size=span * 20, location=(center.x, center.y, lo.z - 0.00005))
floor = bpy.context.object
floor.data.materials.append(mat("floor", (0.80, 0.81, 0.83), 0.6))
floor.is_shadow_catcher = True


def area(loc, power, size):
    bpy.ops.object.light_add(type="AREA", location=loc)
    lt = bpy.context.object
    lt.data.energy = power
    lt.data.size = size
    c = lt.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"


bpy.ops.object.empty_add(location=center)
target = bpy.context.object
k = span / 0.12  # light power scales with part size (reference: a 120 mm coupon)
area(center + Vector((-0.6, -0.8, 1.2)) * span * 4, 5.0 * k * k, span * 3)
area(center + Vector((1.0, 0.6, 0.6)) * span * 4, 1.6 * k * k, span * 2)
world = bpy.data.worlds.new("w")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25

direction = {"top": Vector((0.0, -0.12, 1.0)), "iso": Vector((-0.55, -1.0, 0.75)), "low": Vector((-0.35, -1.0, 0.45))}[view]
bpy.ops.object.camera_add(location=center + direction.normalized() * span * 3)
cam = bpy.context.object
cam.data.type = "ORTHO"
cam.data.ortho_scale = span * (1.15 if view == "top" else 1.05)
cam.data.clip_start = span * 0.01
cam.data.clip_end = span * 100
c = cam.constraints.new("TRACK_TO")
c.target = target
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"

sc = bpy.context.scene
sc.camera = cam
sc.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
except Exception:
    pass
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
aspect = 2.4 if view == "top" else 1.6
sc.render.resolution_x, sc.render.resolution_y = 1600, int(1600 / aspect)
sc.render.film_transparent = True
sc.render.image_settings.color_mode = "RGBA"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
