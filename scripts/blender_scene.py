"""Blender scene for the pull-rig render. Run through scripts/render_rig.py."""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

stl_dir, out_dir = map(Path, sys.argv[sys.argv.index("--") + 1:][:2])
FAST = "--fast" in sys.argv

# ---------- materials ----------
def principled(name, color, rough=0.5, metal=0.0, coat=0.0, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def wood():
    m = bpy.data.materials.new("plywood")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.55
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.3, 1.0, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 2.2
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 1.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.42, 0.25, 0.11, 1)
    ramp.color_ramp.elements[1].color = (0.80, 0.60, 0.37, 1)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


RAILS = principled("plywood_strip", (0.62, 0.45, 0.27), rough=0.6)
PETG = principled("petg_graphite", (0.045, 0.05, 0.058), rough=0.38, coat=0.15)
STEEL = principled("zinc_steel", (0.78, 0.79, 0.80), rough=0.28, metal=1.0)
BRASS = principled("brass", (0.86, 0.62, 0.28), rough=0.25, metal=1.0)
RUBBER = principled("rubber", (0.03, 0.03, 0.03), rough=0.7)
CELL = principled("load_cell_nickel", (0.70, 0.71, 0.73), rough=0.32, metal=1.0)
POTTING = principled("potting", (0.10, 0.11, 0.10), rough=0.45, coat=0.4)
CABLE = principled("cable", (0.02, 0.02, 0.022), rough=0.45, coat=0.2)
ALU = principled("aluminium", (0.80, 0.81, 0.83), rough=0.22, metal=1.0)
MOTOR = principled("motor_black", (0.025, 0.025, 0.028), rough=0.35, metal=0.6)
BELT = principled("gt2_belt", (0.03, 0.03, 0.03), rough=0.8)
RED = principled("button_red", (0.65, 0.03, 0.02), rough=0.25, coat=0.6)
RIGID = principled("petg_blue", (0.015, 0.09, 0.42), rough=0.3, coat=0.2)
TPU = principled("tpu_orange", (0.92, 0.22, 0.01), rough=0.55)


def threaded(name, pitch_m=0.002):
    # steel with a bump-mapped thread along X (the screw axis)
    m = principled(name, (0.74, 0.75, 0.77), rough=0.3, metal=1.0)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (2 * math.pi / (10 * pitch_m), 0.0, 0.0)
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.bands_direction = "X"
    wv.inputs["Scale"].default_value = 1.0
    wv.inputs["Distortion"].default_value = 0.0
    wv.inputs["Detail"].default_value = 0.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.9
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    nt.links.new(wv.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    return m


LEAD = threaded("lead_screw")
ENGRAVE = principled("laser_engrave", (0.08, 0.05, 0.03), rough=0.9)

MATS = {
    "board": wood(), "rails": RAILS, "ticks": ENGRAVE,
    "ebox": PETG, "ebox_lid": PETG, "box_screws": STEEL, "button_bezel": RUBBER, "button_cap": RED,
    "cell_anchor": PETG, "anchor_hw": STEEL, "load_cell": CELL, "cell_potting": POTTING, "cell_gland": RUBBER,
    "cell_label": principled("label", (0.85, 0.86, 0.84), rough=0.5), "cell_label_text": principled("ink", (0.02, 0.02, 0.02), rough=0.6),
    "cables": CABLE, "fork_a": PETG, "coupon_rigid": RIGID, "coupon_tpu": TPU, "pins": STEEL, "pin_nuts": STEEL,
    "carriage": PETG, "brass_nut": BRASS, "screw": LEAD, "collar": STEEL, "bearing": STEEL, "motor_end": PETG,
    "pulley60": ALU, "pulley20": ALU, "belt": BELT, "motor_body": MOTOR, "motor_caps": ALU, "motor_shaft": STEEL,
}

# ---------- scene ----------
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)

objs = {}
for name, mat in MATS.items():
    f = stl_dir / f"{name}.stl"
    if not f.exists():
        continue
    bpy.ops.wm.stl_import(filepath=str(f), global_scale=0.001)
    o = bpy.context.selected_objects[0]
    o.name = name
    o.data.materials.append(mat)
    bpy.context.view_layer.objects.active = o
    if name not in ("ticks", "cables", "belt", "cell_label_text"):
        # STL faces are triangles; merge coplanar ones so flat faces shade flat under the bevel
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(1))
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    except Exception:
        bpy.ops.object.shade_smooth()
    if name not in ("ticks", "cables", "belt", "cell_label", "cell_label_text"):
        bev = o.modifiers.new("bevel", "BEVEL")
        bev.width = 0.0004
        bev.segments = 2
        bev.limit_method = "ANGLE"
        bev.harden_normals = True      # keeps big flat faces flat next to the rounded edges
    objs[name] = o

# studio floor
bpy.ops.mesh.primitive_plane_add(size=6, location=(0.33, 0, -0.0181))
floor = bpy.context.object
floor.data.materials.append(principled("floor", (0.62, 0.63, 0.65), rough=0.6))

# lights
def area(loc, rot, size, power, color=(1, 1, 1)):
    bpy.ops.object.light_add(type="AREA", location=loc, rotation=rot)
    l = bpy.context.object
    l.data.size = size
    l.data.energy = power
    l.data.color = color
    return l

area((0.25, -0.6, 0.9), (math.radians(35), 0, math.radians(-10)), 1.2, 38)
area((0.9, 0.5, 0.5), (math.radians(-60), 0, math.radians(130)), 0.8, 14, (0.9, 0.95, 1.0))
area((-0.4, 0.2, 0.4), (math.radians(-50), 0, math.radians(-110)), 0.6, 6, (1.0, 0.92, 0.85))
world = bpy.context.scene.world or bpy.data.worlds.new("world")
bpy.context.scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.18

# render settings
sc = bpy.context.scene
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
sc.cycles.samples = 48 if FAST else 256
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.film_transparent = False


def shoot(name, cam_loc, target, lens, res, dof=None):
    bpy.ops.object.empty_add(location=target)
    tgt = bpy.context.object
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.object
    cam.data.lens = lens
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    if dof:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_object = tgt
        cam.data.dof.aperture_fstop = dof
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = str(out_dir / name)
    bpy.ops.render.render(write_still=True)


shoot("pull_rig.png", (0.02, -0.62, 0.42), (0.34, 0.0, 0.02), 30, (1920, 1000))
shoot("pull_rig_detail.png", (0.17, -0.20, 0.13), (0.26, 0.0, 0.025), 40, (1600, 1000), dof=11.0)
shoot("pull_rig_drive.png", (0.80, -0.24, 0.20), (0.60, 0.0, 0.055), 40, (1600, 1000), dof=11.0)
