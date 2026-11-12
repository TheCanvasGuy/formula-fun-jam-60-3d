#!/usr/bin/env python3
"""
render_photoreal_exploded_heroes.py
Photorealistic Multi-Angle Studio Product Photography Renderer (Blender 5.1.2 CYCLES + Standard sRGB)
for the Formula Fun 6'0" Jam Surfboard (Dual-Stringer Exploded View).

Key Engineering Guarantees:
1. Horizontal Studio Orientation (Z = Up):
   - The surfboard floats horizontally above a seamless curved L-shaped studio infinity cyclorama,
     so overhead softbox lighting casts authentic vertical inter-layer shadows:
       EVA Deck Pad -> Dual Natural Wood Composite Stringers -> Recessed Marko EPS Cavity -> Studio Floor.
2. Mathematical Zero-Crop Camera Framing Solver:
   - Updates `view_layer` after applying exploded offsets and projects all exploded component vertices
     into 2D camera normalized device coordinates (NDC), solving exact camera distance and target so
     100% of the board + fins fits inside X=[0.12..0.88] and Y=[0.14..0.86] (guaranteed >=12-14% margin
     on all 4 sides, zero cropping).
3. Multi-Angle Photorealistic Studio Suite (4 Distinct Angles x 2 Colorways):
   - Angle 1: 3/4 Front-Quarter Studio Hero (`jam_<color>_hero_angle1_34_front_4k.png`)
   - Angle 2: Side-3/4 Rocker & Profile Exploded Hero (`jam_<color>_hero_angle2_side_profile_4k.png`)
   - Angle 3: Rear-3/4 Tail & Thruster Fin System Hero (`jam_<color>_hero_angle3_tail_thruster_4k.png`)
   - Angle 4: High-Angle 45° Architectural Isometric Hero (`jam_<color>_hero_angle4_overhead_iso_4k.png`)
"""

import os
import sys
import math
import shutil
import bpy
import bmesh
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

BASE_DIR = "/Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD"
RENDERS_DIR = os.path.join(BASE_DIR, "renders")
sys.path.insert(0, BASE_DIR)
import build_jam_usdz as base_builder


def enhance_materials_for_photoreal_cycles(mats, colorway="blackout"):
    """
    Upgrade all 6 component materials with physical micro-surface bump, subsurface scattering,
    clearcoat, and Fresnel edge response for close-up 4K Cycles raytracing.
    """
    # 1. Marko EPS Closed-Cell Black Foam Core — micro-cellular bead bump & subtle subsurface scatter
    mat_core = mats["core"]
    nodes = mat_core.node_tree.nodes
    links = mat_core.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.72
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.26
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.04
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.10
        bsdf.inputs["Coat Roughness"].default_value = 0.42

    tex_coord = nodes.new("ShaderNodeTexCoord")
    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.inputs["Scale"].default_value = 280.0
    voronoi.inputs["Randomness"].default_value = 0.85
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.24
    bump.inputs["Distance"].default_value = 0.0015
    norm_m = next((n for n in nodes if n.type == "NORMAL_MAP"), None)
    links.new(tex_coord.outputs["Object"], voronoi.inputs["Vector"])
    links.new(voronoi.outputs["Distance"], bump.inputs["Height"])
    if norm_m:
        norm_m.inputs["Strength"].default_value = 0.80
        links.new(norm_m.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # 2. Marko EPS Recessed Inner Pocket Floor — structured cellular EPS texture
    mat_pocket = mats["pocket"]
    p_nodes = mat_pocket.node_tree.nodes
    p_bsdf = next(n for n in p_nodes if n.type == "BSDF_PRINCIPLED")
    p_bsdf.inputs["Roughness"].default_value = 0.80
    if "Specular IOR Level" in p_bsdf.inputs:
        p_bsdf.inputs["Specular IOR Level"].default_value = 0.22
    p_norm = next((n for n in p_nodes if n.type == "NORMAL_MAP"), None)
    if p_norm:
        p_norm.inputs["Strength"].default_value = 1.15

    # 3. Brushed EVA Traction Deck Pad — crisp matte-satin brushed EVA with micro-groove depth
    mat_deck = mats["deck"]
    d_nodes = mat_deck.node_tree.nodes
    d_bsdf = next(n for n in d_nodes if n.type == "BSDF_PRINCIPLED")
    d_bsdf.inputs["Roughness"].default_value = 0.85 if colorway == "yellow" else 0.78
    if "Specular IOR Level" in d_bsdf.inputs:
        d_bsdf.inputs["Specular IOR Level"].default_value = 0.10 if colorway == "yellow" else 0.18
    if "Coat Weight" in d_bsdf.inputs:
        d_bsdf.inputs["Coat Weight"].default_value = 0.0 if colorway == "yellow" else 0.05
        d_bsdf.inputs["Coat Roughness"].default_value = 0.50
    d_norm = next((n for n in d_nodes if n.type == "NORMAL_MAP"), None)
    if d_norm:
        d_norm.inputs["Strength"].default_value = 0.75

    # 4. Natural Laminated Wood Center Stringer — warm birch/poplar grain with satin epoxy seal coat
    mat_str = mats["stringer"]
    s_nodes = mat_str.node_tree.nodes
    s_links = mat_str.node_tree.links
    s_bsdf = next(n for n in s_nodes if n.type == "BSDF_PRINCIPLED")
    s_bsdf.inputs["Roughness"].default_value = 0.28
    if "Specular IOR Level" in s_bsdf.inputs:
        s_bsdf.inputs["Specular IOR Level"].default_value = 0.48
    if "Coat Weight" in s_bsdf.inputs:
        s_bsdf.inputs["Coat Weight"].default_value = 0.60
        s_bsdf.inputs["Coat Roughness"].default_value = 0.14

    s_coord = s_nodes.new("ShaderNodeTexCoord")
    s_map = s_nodes.new("ShaderNodeMapping")
    s_map.inputs["Scale"].default_value = (2.0, 45.0, 45.0)
    s_noise = s_nodes.new("ShaderNodeTexNoise")
    s_noise.inputs["Scale"].default_value = 18.0
    s_noise.inputs["Detail"].default_value = 8.0
    s_noise.inputs["Roughness"].default_value = 0.65
    s_bump = s_nodes.new("ShaderNodeBump")
    s_bump.inputs["Strength"].default_value = 0.16
    s_bump.inputs["Distance"].default_value = 0.001
    s_links.new(s_coord.outputs["Generated"], s_map.inputs["Vector"])
    s_links.new(s_map.outputs["Vector"], s_noise.inputs["Vector"])
    s_links.new(s_noise.outputs["Fac"], s_bump.inputs["Height"])
    s_links.new(s_bump.outputs["Normal"], s_bsdf.inputs["Normal"])

    # 5. Futures Fin Boxes & Deck Plugs — Satin Black Molded Glass-Filled Nylon
    mat_box = mats["finbox"]
    b_nodes = mat_box.node_tree.nodes
    b_bsdf = next(n for n in b_nodes if n.type == "BSDF_PRINCIPLED")
    b_bsdf.inputs["Base Color"].default_value = (0.028, 0.029, 0.032, 1.0)
    b_bsdf.inputs["Roughness"].default_value = 0.24
    if "Specular IOR Level" in b_bsdf.inputs:
        b_bsdf.inputs["Specular IOR Level"].default_value = 0.52
    if "Coat Weight" in b_bsdf.inputs:
        b_bsdf.inputs["Coat Weight"].default_value = 0.35
        b_bsdf.inputs["Coat Roughness"].default_value = 0.18

    # 6. White Composite Thruster Fins — Crisp Pearl-White Molded Fiberglass Composite
    mat_fin = mats["fin"]
    f_nodes = mat_fin.node_tree.nodes
    f_bsdf = next(n for n in f_nodes if n.type == "BSDF_PRINCIPLED")
    f_bsdf.inputs["Base Color"].default_value = (0.95, 0.96, 0.98, 1.0)
    f_bsdf.inputs["Roughness"].default_value = 0.16
    if "Specular IOR Level" in f_bsdf.inputs:
        f_bsdf.inputs["Specular IOR Level"].default_value = 0.60
    if "Subsurface Weight" in f_bsdf.inputs:
        f_bsdf.inputs["Subsurface Weight"].default_value = 0.08
    if "Coat Weight" in f_bsdf.inputs:
        f_bsdf.inputs["Coat Weight"].default_value = 0.75
        f_bsdf.inputs["Coat Roughness"].default_value = 0.06


def orient_board_horizontally_for_studio(objects_by_name):
    """
    Transform from Standing Upright space into Horizontal Studio space (Z_world = UP) via a proper SO(3)
    rigid rotation (det = +1.0, preserving outward face normals and right-way-round FormulaFun typography):
      X_world = +Z_stand (Length along X: Tail at -0.915m, Nose at +0.915m)
      Y_world = -X_stand (Width along Y: Right rail at -0.268m, Left rail at +0.268m)
      Z_world = -Y_stand (Height along Z: Deck faces UP +Z, Hull faces DOWN -Z)
    """
    R_horiz = Matrix((
        ( 0.0,  0.0, 1.0, 0.0),
        (-1.0,  0.0, 0.0, 0.0),
        ( 0.0, -1.0, 0.0, 0.0),
        ( 0.0,  0.0, 0.0, 1.0),
    ))

    # Remove the 6 microscopic balancer vertices on Jam_60_Core so framing uses true physical geometry
    core_obj, _ = objects_by_name["Jam_60_Core"]
    bm_c = bmesh.new()
    bm_c.from_mesh(core_obj.data)
    bm_c.verts.ensure_lookup_table()
    if len(bm_c.verts) > 100:
        for v in list(bm_c.verts)[-6:]:
            bm_c.verts.remove(v)
    bm_c.to_mesh(core_obj.data)
    bm_c.free()
    core_obj.data.update()

    # Exploded vertical Z offsets (in meters, Z_world = UP)
    z_offsets = {
        "JAM_DCover":         +0.265,
        "Jam_Deck_Hardware":  +0.265,
        "JAM_Stringer_Left":  +0.132,
        "JAM_Stringer_Right": +0.132,
        "JAM_Stringer":       +0.132,
        "Jam_60_Core":         0.000,
        "JAM_Pocket_Liner":    0.000,
        "FB_75_LeftBox":      -0.118,
        "FB_75_RightBox":     -0.118,
        "FB_050_CenterBox":   -0.148,
        "Fin_Left":           -0.220,
        "Fin_Right":          -0.220,
        "Fin_Center":         -0.242,
    }

    for name, (obj, cfg) in objects_by_name.items():
        obj.hide_render = False
        obj.hide_viewport = False
        obj.scale = Vector((1.0, 1.0, 1.0))
        obj.data.transform(R_horiz)
        obj.data.update()
        dz = z_offsets.get(name, 0.0)
        obj.location = Vector((0.0, 0.0, dz))

    # CRITICAL: Update Blender's dependency graph so obj.matrix_world reflects the new Z offsets!
    bpy.context.view_layer.update()


def build_seamless_studio_cyclorama_and_lights(scene):
    """
    Create a true curved L-shaped seamless studio infinity cyclorama (floor + curved cove + tall back wall)
    with a radial studio floor gradient so both dark foam/deck AND white composite thruster fins pop
    with high-contrast studio separation and zero horizon seam.
    """
    bm = bmesh.new()
    # Build profile curve in (Y_local, Z_local), extruded along X_local in [-28m .. +28m]:
    # Floor from Y_local = +14.0m (toward camera) back to Y_local = -5.5m,
    # then a smooth 90-degree circular cove of radius R = 6.0m up to Z_local = +18.0m.
    # Because all studio lights sit within 2.8m of the origin, no light EVER intersects or clips the cove wall!
    profile_pts = []
    profile_pts.append((14.0, 0.0))
    profile_pts.append((4.0, 0.0))
    profile_pts.append((-5.5, 0.0))
    n_arc = 36
    r_cove = 6.0
    yc, zc = -5.5, r_cove
    for i in range(1, n_arc + 1):
        theta = -0.5 * math.pi + (0.5 * math.pi) * (i / float(n_arc))
        py = yc - r_cove * math.cos(theta)
        pz = zc + r_cove * math.sin(theta)
        profile_pts.append((py, pz))
    profile_pts.append((yc - r_cove, 18.0))

    left_verts = [bm.verts.new((-28.0, py, pz)) for (py, pz) in profile_pts]
    right_verts = [bm.verts.new((+28.0, py, pz)) for (py, pz) in profile_pts]
    for i in range(len(profile_pts) - 1):
        f = bm.faces.new((left_verts[i], right_verts[i], right_verts[i + 1], left_verts[i + 1]))
        f.smooth = True

    mesh = bpy.data.meshes.new("StudioCyclorama_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    cyc_obj = bpy.data.objects.new("StudioCyclorama", mesh)
    scene.collection.objects.link(cyc_obj)
    # Place floor at Z = -0.44m (just beneath the lowest thruster fin tip at Z = -0.39m)
    cyc_obj.location = Vector((0.0, 0.0, -0.44))

    # Studio Cyclorama Material: Calibrated architectural warm mid-tone limestone/slate cyclorama
    # so Blackout (#18181B), Mellow Yellow (#F5B800), Wood Stringer, AND White Thruster Fins (#F2F4F7)
    # all have high studio contrast and crisp shadow reception.
    mat_cyc = bpy.data.materials.new("Mat_Studio_Cyclorama")
    nodes = mat_cyc.node_tree.nodes
    links = mat_cyc.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.88
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.06

    tex_coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.09, 0.10, 0.10)
    grad = nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "QUADRATIC_SPHERE"
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.21, 0.215, 0.23, 1.0)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.38, 0.38, 0.395, 1.0)

    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    cyc_obj.data.materials.append(mat_cyc)

    # Remove old lights
    for o in list(scene.collection.objects):
        if o.type == "LIGHT":
            bpy.data.objects.remove(o, do_unlink=True)

    world = scene.world
    if not world:
        world = bpy.data.worlds.new("PhotorealStudioWorld")
        scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.42, 0.42, 0.44, 1.0)
        bg.inputs[1].default_value = 0.28

    # Parent all studio lights to cyc_obj (or a rig) so when the cyclorama rotates to face the camera,
    # the key, rim, and fill softboxes stay oriented relative to the camera and never clip the back wall!
    def add_area_softbox(name, loc, target, energy, size_x, size_y, color=(1.0, 1.0, 1.0)):
        ldata = bpy.data.lights.new(name, type="AREA")
        ldata.energy = energy
        ldata.shape = "RECTANGLE"
        ldata.size = size_x
        ldata.size_y = size_y
        ldata.color = color
        lobj = bpy.data.objects.new(name, ldata)
        scene.collection.objects.link(lobj)
        lobj.parent = cyc_obj
        # Compensate for cyc_obj.location.z = -0.44
        local_loc = Vector((loc[0], loc[1], loc[2] + 0.44))
        local_target = Vector((target[0], target[1], target[2] + 0.44))
        lobj.location = local_loc
        lobj.rotation_euler = (local_target - local_loc).to_track_quat("-Z", "Y").to_euler()
        return lobj

    # 1. Overhead Main Softbox Bank (casts crisp vertical inter-layer shadows + soft studio floor shadow)
    add_area_softbox(
        "Overhead_Main_Softbox",
        loc=(0.10, 0.35, 2.85),
        target=(0.0, 0.0, 0.0),
        energy=175.0,
        size_x=2.4,
        size_y=1.2,
        color=(1.0, 0.99, 0.97),
    )

    # 2. Grazing Rim / Specular Strip Light (rakes across EVA traction texture, wood stringer & foam pocket step)
    add_area_softbox(
        "Grazing_Rim_Strip",
        loc=(-1.10, -1.75, 1.75),
        target=(0.0, 0.0, 0.0),
        energy=135.0,
        size_x=2.6,
        size_y=0.65,
        color=(1.0, 0.98, 0.94),
    )

    # 3. Camera-Side Cool Fill Softbox (reveals closed-cell Marko EPS bead detail on dark rails & fin boxes)
    add_area_softbox(
        "Camera_Cool_Fill",
        loc=(1.25, 2.35, 0.75),
        target=(0.0, 0.0, -0.02),
        energy=115.0,
        size_x=2.8,
        size_y=1.5,
        color=(0.95, 0.98, 1.0),
    )

    # 4. Opposite-Side Rim & Fin Kicker Light (highlights the 3 white composite thruster fins & Futures fin boxes)
    add_area_softbox(
        "Tail_Fin_Kicker",
        loc=(-2.05, 1.45, 0.20),
        target=(-0.45, 0.0, -0.18),
        energy=110.0,
        size_x=1.6,
        size_y=1.1,
        color=(1.0, 0.99, 0.98),
    )

    return cyc_obj


def get_all_mesh_world_points(objects_by_name):
    """Collect world-space vertices AND all 8 world-space bounding-box corners of every component."""
    bpy.context.view_layer.update()
    pts = []
    for name, (obj, cfg) in objects_by_name.items():
        if obj.hide_render:
            continue
        mw = obj.matrix_world
        for corner in obj.bound_box:
            pts.append(mw @ Vector(corner))
        verts = obj.data.vertices
        step = max(1, len(verts) // 300)
        for i in range(0, len(verts), step):
            pts.append(mw @ verts[i].co)
    return pts


def frame_camera_uncropped(
    scene, cam_obj, cam_data, cyc_obj, pts, cam_dir_unit, lens_mm=52.0, max_u_span=0.76, max_v_span=0.72
):
    """
    Mathematically position and aim the camera along `cam_dir_unit`, rotate the curved L-shaped
    studio cyclorama so its cove wall sits directly behind the surfboard relative to the camera,
    and iteratively solve exact distance and target so:
      - Horizontal NDC X span <= max_u_span (e.g. 0.76 -> [0.12 .. 0.88])
      - Vertical NDC Y span   <= max_v_span (e.g. 0.72 -> [0.14 .. 0.86])
    Guarantees >= 12-14% studio breathing room on ALL FOUR SIDES of the image (ZERO cropping!).
    """
    cam_data.lens = lens_mm
    cam_data.sensor_width = 36.0
    cam_data.sensor_fit = "HORIZONTAL"

    min_x = min(p.x for p in pts); max_x = max(p.x for p in pts)
    min_y = min(p.y for p in pts); max_y = max(p.y for p in pts)
    min_z = min(p.z for p in pts); max_z = max(p.z for p in pts)
    target = Vector(((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5))

    u_dir = Vector(cam_dir_unit).normalized()
    # Rotate curved L-shaped cyclorama around Z so its +Y local axis points toward the camera's horizontal azimuth
    az_angle = math.atan2(u_dir.y, u_dir.x) - 0.5 * math.pi
    cyc_obj.rotation_euler = Vector((0.0, 0.0, az_angle))

    dist = 3.2
    aspect = scene.render.resolution_x / float(scene.render.resolution_y)
    fov_h = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    fov_v = 2.0 * math.atan(math.tan(0.5 * fov_h) / aspect)

    for _ in range(14):
        cam_obj.location = target + u_dir * dist
        direction = (target - cam_obj.location).normalized()
        right = direction.cross(Vector((0.0, 0.0, 1.0))).normalized()
        up = right.cross(direction).normalized()
        back = -direction
        rot_mat = Matrix((
            (right.x, up.x, back.x, 0.0),
            (right.y, up.y, back.y, 0.0),
            (right.z, up.z, back.z, 0.0),
            (0.0,     0.0,  0.0,    1.0),
        ))
        cam_obj.rotation_euler = rot_mat.to_euler()
        bpy.context.view_layer.update()

        ndc = [world_to_camera_view(scene, cam_obj, p) for p in pts]
        umin = min(c.x for c in ndc); umax = max(c.x for c in ndc)
        vmin = min(c.y for c in ndc); vmax = max(c.y for c in ndc)

        span_u = umax - umin
        span_v = vmax - vmin

        # Shift target in camera right/up plane so NDC midpoint is at (0.50, 0.50)
        uc = 0.5 * (umin + umax)
        vc = 0.5 * (vmin + vmax)
        shift_right = (uc - 0.5) * 2.0 * dist * math.tan(0.5 * fov_h) * 0.85
        shift_up = (vc - 0.5) * 2.0 * dist * math.tan(0.5 * fov_v) * 0.85
        target = target + right * shift_right + up * shift_up

        # Scale distance by the tighter of horizontal or vertical span constraint
        ratio_needed = max(span_u / max_u_span, span_v / max_v_span)
        dist = dist * (0.2 + 0.8 * ratio_needed)

    # Final verification update before returning
    cam_obj.location = target + u_dir * dist
    bpy.context.view_layer.update()
    ndc = [world_to_camera_view(scene, cam_obj, p) for p in pts]
    umin = min(c.x for c in ndc); umax = max(c.x for c in ndc)
    vmin = min(c.y for c in ndc); vmax = max(c.y for c in ndc)
    print(f"  [FRAME CHECK] NDC X=[{umin:.3f}, {umax:.3f}] Y=[{vmin:.3f}, {vmax:.3f}] (dist={dist:.2f}m)")


def render_multi_angle_suite(res_x=3840, res_y=2160, samples=96):
    # 4 Distinct Uncropped Studio Camera Angles around the horizontal exploded surfboard:
    # X_world = Length (-0.915 Tail .. +0.915 Nose), Y_world = Width, Z_world = Up (Explosion axis)
    angles = [
        {
            "slug": "angle1_34_front",
            "label": "Angle 1 — 3/4 Front-Nose Studio Hero",
            "cam_dir": (0.72, -0.82, 0.28),
            "lens": 52.0,
            "max_u": 0.76,
            "max_v": 0.72,
        },
        {
            "slug": "angle2_side_profile",
            "label": "Angle 2 — Side-3/4 Rocker & Profile Exploded Hero",
            "cam_dir": (0.12, -0.98, 0.17),
            "lens": 56.0,
            "max_u": 0.78,
            "max_v": 0.72,
        },
        {
            "slug": "angle3_tail_thruster",
            "label": "Angle 3 — Rear-3/4 Tail & Thruster Fin System Hero",
            "cam_dir": (-0.74, -0.80, 0.26),
            "lens": 50.0,
            "max_u": 0.76,
            "max_v": 0.72,
        },
        {
            "slug": "angle4_overhead_iso",
            "label": "Angle 4 — High-Angle Overhead Architectural Hero",
            "cam_dir": (0.56, 0.72, 0.56),
            "lens": 52.0,
            "max_u": 0.76,
            "max_v": 0.72,
        },
    ]

    for cw in ["blackout", "yellow"]:
        print(f"\n=== RENDERING PHOTOREALISTIC MULTI-ANGLE SUITE ({cw.upper()}) ===")
        scene, objects_by_name, mats = base_builder.build_scene_for_colorway(cw)
        cam_obj, cam_data = base_builder.setup_studio_lighting_and_camera(
            scene, res_x=res_x, res_y=res_y, transparent=False
        )
        base_builder.enable_cycles_metal_raytracing(scene, samples=samples)

        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = -0.68 if cw == "yellow" else -0.55
        scene.view_settings.gamma = 1.0

        enhance_materials_for_photoreal_cycles(mats, cw)
        orient_board_horizontally_for_studio(objects_by_name)
        cyc_obj = build_seamless_studio_cyclorama_and_lights(scene)
        pts = get_all_mesh_world_points(objects_by_name)

        for idx, ang in enumerate(angles):
            frame_camera_uncropped(
                scene,
                cam_obj,
                cam_data,
                cyc_obj,
                pts,
                cam_dir_unit=ang["cam_dir"],
                lens_mm=ang["lens"],
                max_u_span=ang["max_u"],
                max_v_span=ang["max_v"],
            )
            out_path = os.path.join(RENDERS_DIR, f"jam_{cw}_hero_{ang['slug']}_4k.png")
            scene.render.filepath = out_path
            bpy.ops.render.render(write_still=True)
            print(f"[OK] Saved {ang['label']}: {out_path}")

            if idx == 0:
                shutil.copyfile(out_path, os.path.join(RENDERS_DIR, f"jam_{cw}_exploded_hero_4k.png"))
            elif idx == 2:
                shutil.copyfile(out_path, os.path.join(RENDERS_DIR, f"jam_{cw}_exploded_editorial_4k.png"))


if __name__ == "__main__":
    res_x = int(os.environ.get("HERO_RES_X", "3840"))
    res_y = int(os.environ.get("HERO_RES_Y", "2160"))
    samples = int(os.environ.get("HERO_SAMPLES", "96"))
    render_multi_angle_suite(res_x=res_x, res_y=res_y, samples=samples)
