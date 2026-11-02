#!/usr/bin/env python3
"""
build_jam_usdz.py
Deterministic 3D Kinematic Rigging, PBR Texturing, GLB/USDZ Export, and
Twinnie-Style Exploded View Render Pipeline for the Formula Fun 6'0" Jam Surfboard.

Sources ground-truth SolidWorks 2026 CAD geometry (`JAM_Assem.SLDASM`) from Ilir Bordoniqi (Marko Foam):
- SHA-256: 4c57d3044c3462fdf3cf460bdd877c7c0309b2faee051836408996d010b4e20b
- 10 CAD assembly instances (8 unique part meshes, 54,371 triangles)
- Calibrated directly against:
  - Top Deck Blackout: /Users/byronmini/Desktop/Formula Fun iCloud/Jam_Black.png
  - Top Deck Mellow Yellow: /Users/byronmini/Desktop/Formula Fun iCloud/Jam_Yellow.png
  - Bottom Thruster Hull: PVW_2601_1400x.jpg.webp
  - Twinnie Exploded View Reference on formulafunboards.com
"""

import os
import sys
import math
import shutil
import subprocess
import re
import bpy
import bmesh
from mathutils import Vector, Euler, Matrix
from mathutils.bvhtree import BVHTree

BASE_DIR = "/Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD"
PARTS_DIR = os.path.join(BASE_DIR, "parts")
TEX_DIR = os.path.join(BASE_DIR, "textures")
RENDERS_DIR = os.path.join(BASE_DIR, "renders")
os.makedirs(RENDERS_DIR, exist_ok=True)

# 1. Exact SolidWorks 4x4 Column-Major Matrices from COMPINSTANCETREE
# All meshes are baked in Constructed (Assembled) coordinates at obj.location = (0, 0, 0),
# so assembled_dz = 0.0 for all components, and twinnie_dz is the outward explosion offset in SolidWorks Z_sw.
SW_INSTANCES = [
    {
        "name": "Jam_60_Core",
        "stl": "Jam_60.stl",
        "role": "core",
        "sw_matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        "sw_dz_to_assembled": 0.0,
        "assembled_dz": 0.0,
        "exploded_dz": 0.0,
        "twinnie_dz": 0.0,
    },
    {
        "name": "JAM_Pocket_Liner",
        "stl": "JAM_DCover.stl",
        "role": "pocket",
        "sw_matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.001142065548915281, -7.059931502029518e-16, 0.1987194055112586, 1],
        "sw_dz_to_assembled": 0.0,
        "assembled_dz": 0.0,
        "exploded_dz": 0.0,
        "twinnie_dz": 0.0,
    },
    {
        "name": "JAM_DCover",
        "stl": "JAM_DCover.stl",
        "role": "deck",
        "sw_matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.001142065548915281, -7.059931502029518e-16, 0.1987194055112586, 1],
        "sw_dz_to_assembled": 0.0,
        "assembled_dz": 0.0,
        "exploded_dz": +0.2850,
        "twinnie_dz": +0.2950,     # Lifts +0.2950m above assembled deck so full single stringer is 100% visible
    },
    {
        "name": "JAM_Stringer",
        "stl": "JAM_Stringer.stl",
        "role": "stringer",
        "sw_matrix": [1, 0, 0, 0, 0, -3.491481338843133e-15, 1, 0, 0, -1, -3.491481338843133e-15, 0, 1.755936364195265, -0.009652, 0.166710974115954, 1],
        "sw_dz_to_assembled": 0.0,
        "assembled_dz": 0.0,
        "exploded_dz": +0.1480,
        "twinnie_dz": +0.1480,     # Single center stringer (Y_sw = 0.0) lifting +0.1480m halfway between core cavity and deck pad
    },
    {
        "name": "FB_050_CenterBox",
        "stl": "FB_050.stl",
        "role": "finbox",
        "sw_matrix": [-3.676485949964451e-17, -1, -1.737813311231042e-17, 0, -0.9953519103143689, 3.492037909887183e-17, 0.09630459300332693, 0, -0.09630459300332693, 2.083798282197333e-17, -0.9953519103143689, 0, 0.02167165265241597, -0.02539999918719999, -0.05397459832391487, 1],
        "sw_dz_to_assembled": +0.1055,
        "assembled_dz": 0.0,
        "exploded_dz": -0.1750,
        "twinnie_dz": -0.1880,
    },
    {
        "name": "FB_75_LeftBox",
        "stl": "FB_75.stl",
        "role": "finbox",
        "sw_matrix": [-0.9971425789290723, 0.05564411712773822, 0.0510921668727535, 0, -0.0510128006972302, 0.002846696467479161, -0.9986939423488292, 0, -0.05571688659377341, -0.9984466077604233, 1.921206249644314e-16, 0, 0.3419878431519812, 0.1421121832669984, -0.08165219806471219, 1],
        "sw_dz_to_assembled": +0.1045,
        "assembled_dz": 0.0,
        "exploded_dz": -0.1350,
        "twinnie_dz": -0.1450,
    },
    {
        "name": "FB_75_RightBox",
        "stl": "FB_75.stl",
        "role": "finbox",
        "sw_matrix": [-0.9971425789290723, -0.05564411712773822, 0.0510921668727535, 0, -0.05101280069723023, -0.002846696467479162, -0.9986939423488294, 0, 0.05571688659377343, -0.9984466077604235, -1.921206249644314e-16, 0, 0.3419878431519812, -0.1421121832669984, -0.08165219806471219, 1],
        "sw_dz_to_assembled": +0.1045,
        "assembled_dz": 0.0,
        "exploded_dz": -0.1350,
        "twinnie_dz": -0.1450,
    },
    {
        "name": "Fin_Center",
        "stl": "Fin_small_Center.stl",
        "role": "fin",
        "sw_matrix": [0.9953519103143689, -2.401507812055392e-16, -0.09630459300332701, 0, 2.382037013135266e-16, 1, -3.171470813506898e-17, 0, 0.09630459300332701, 8.62718482041831e-18, 0.9953519103143689, 0, 0.08079708330446266, 3.209238430557093e-17, -0.1007348557637466, 1],
        "sw_dz_to_assembled": +0.1485,
        "assembled_dz": 0.0,
        "exploded_dz": -0.2850,
        "twinnie_dz": -0.3100,
    },
    {
        "name": "Fin_Left",
        "stl": "Fin_small_Left.stl",
        "role": "fin",
        "sw_matrix": [0.9971425789290725, -0.05564411712773772, -0.05109216687275349, 0, 0.05571688659377293, 0.9984466077604233, -1.703231133102684e-16, 0, 0.05101280069723019, -0.002846696467479158, 0.9986939423488294, 0, 0.2900601228293914, 0.142243387983674, -0.1186900886630978, 1],
        "sw_dz_to_assembled": +0.1520,
        "assembled_dz": 0.0,
        "exploded_dz": -0.2550,
        "twinnie_dz": -0.2750,
    },
    {
        "name": "Fin_Right",
        "stl": "Fin_small_Right_Mirror.stl",
        "role": "fin",
        "sw_matrix": [0.9971425789290722, 0.0556441171277385, -0.05109216687275348, 0, -0.05571688659377371, 0.9984466077604233, 1.799934323861666e-16, 0, 0.05101280069723019, 0.002846696467479188, 0.9986939423488291, 0, 0.2899716722719238, -0.1406583539938544, -0.1186900886630978, 1],
        "sw_dz_to_assembled": +0.1520,
        "assembled_dz": 0.0,
        "exploded_dz": -0.2550,
        "twinnie_dz": -0.2750,
    },
]

# Center of Jam_60_Core at the exact geometric middle of the board:
# X in [0.0000, 1.8303] -> X_mid = 0.91515 m (longitudinal midpoint of 6'0" board)
# Y in [-0.2686, +0.2686] -> Y_mid = 0.0 m (lateral centerline)
# Z at longitudinal middle (hull=0.000, deck=0.076, overall rocker mid=0.045) -> Z_mid = 0.0450 m
SW_CENTER_X = 0.91515
SW_CENTER_Y = 0.0
SW_CENTER_Z = 0.0450


def sw_col_major_to_blender_matrix(m):
    """Convert SolidWorks 16-float column-major transform to Blender 4x4 Matrix."""
    return Matrix((
        (m[0], m[4], m[8],  m[12]),
        (m[1], m[5], m[9],  m[13]),
        (m[2], m[6], m[10], m[14]),
        (0.0,  0.0,  0.0,   1.0),
    ))


def sw_to_standing_matrix():
    """
    Map SolidWorks assembly coordinates (X_sw = tail->nose, Y_sw = right->left, Z_sw = hull->deck)
    into right-handed Standing Upright Blender coordinates (det = +1):
      X_bl = +Y_sw  (Left/Right symmetric for board & graphic UVs)
      Y_bl = -Z_sw  (Deck faces -Y -> +Z in glTF/USD)
      Z_bl = +X_sw  (Nose is +Z UP, Tail is -Z DOWN)
    """
    R = Matrix((
        (0.0,  1.0,  0.0, 0.0),
        (0.0,  0.0, -1.0, 0.0),
        (1.0,  0.0,  0.0, 0.0),
        (0.0,  0.0,  0.0, 1.0),
    ))
    T = Matrix.Translation(Vector((-SW_CENTER_X, -SW_CENTER_Y, -SW_CENTER_Z)))
    return R @ T


def create_image_node(nodes, filename, is_color=True):
    filepath = os.path.join(TEX_DIR, filename)
    img_node = nodes.new("ShaderNodeTexImage")
    if os.path.exists(filepath):
        img = bpy.data.images.load(filepath, check_existing=True)
        img_node.image = img
        if not is_color:
            img.colorspace_settings.name = "Non-Color"
    return img_node


def build_materials(colorway="blackout"):
    mats = {}

    # 1. Marko EPS Closed-Cell Black Foam Core
    mat_foam = bpy.data.materials.new(name="Mat_Marko_EPS_Foam")
    nodes = mat_foam.node_tree.nodes
    links = mat_foam.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.84
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.08

    base_t = create_image_node(nodes, "jam_foam_basecolor_4k.png", is_color=True)
    rough_t = create_image_node(nodes, "jam_foam_roughness_4k.png", is_color=False)
    norm_t = create_image_node(nodes, "jam_foam_normal_4k.png", is_color=False)
    norm_m = nodes.new("ShaderNodeNormalMap")
    norm_m.inputs["Strength"].default_value = 0.65

    links.new(base_t.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(rough_t.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(norm_t.outputs["Color"], norm_m.inputs["Color"])
    links.new(norm_m.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["core"] = mat_foam

    # 1b. Marko EPS Recessed Inner Pocket Floor (textured dark charcoal-grey cellular EPS matching Twinnie exploded video)
    mat_pocket = bpy.data.materials.new(name="Mat_Marko_EPS_Pocket_Floor")
    nodes = mat_pocket.node_tree.nodes
    links = mat_pocket.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.88
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.08
    p_base = create_image_node(nodes, "jam_pocket_floor_basecolor_2k.png", is_color=True)
    p_rough = create_image_node(nodes, "jam_foam_roughness_4k.png", is_color=False)
    p_norm = create_image_node(nodes, "jam_foam_normal_4k.png", is_color=False)
    p_norm_m = nodes.new("ShaderNodeNormalMap")
    p_norm_m.inputs["Strength"].default_value = 0.90
    links.new(p_base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(p_rough.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(p_norm.outputs["Color"], p_norm_m.inputs["Color"])
    links.new(p_norm_m.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["pocket"] = mat_pocket

    # 2. EVA Traction Deck Pad (Blackout or Mellow Yellow)
    deck_tex_file = (
        "jam_deck_blackout_basecolor_4k.png"
        if colorway == "blackout"
        else "jam_deck_yellow_basecolor_4k.png"
    )
    mat_deck = bpy.data.materials.new(name=f"Mat_Jam_Deck_{colorway.capitalize()}")
    nodes = mat_deck.node_tree.nodes
    links = mat_deck.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.88
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.06

    d_base = create_image_node(nodes, deck_tex_file, is_color=True)
    d_rough = create_image_node(nodes, "jam_deck_roughness_4k.png", is_color=False)
    d_norm = create_image_node(nodes, "jam_deck_normal_4k.png", is_color=False)
    d_norm_m = nodes.new("ShaderNodeNormalMap")
    d_norm_m.inputs["Strength"].default_value = 0.45

    links.new(d_base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(d_rough.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(d_norm.outputs["Color"], d_norm_m.inputs["Color"])
    links.new(d_norm_m.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["deck"] = mat_deck

    # 3. Natural Wood-Grain Composite Stringers (matching Twinnie exploded reference)
    mat_str = bpy.data.materials.new(name="Mat_Jam_Stringer_Wood")
    nodes = mat_str.node_tree.nodes
    links = mat_str.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.12
    s_base = create_image_node(nodes, "jam_stringer_wood_2k.png", is_color=True)
    links.new(s_base.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["stringer"] = mat_str

    # 4. Futures Fin Boxes & Molded Deck Plugs (Satin Black Polymer)
    mat_box = bpy.data.materials.new(name="Mat_Futures_FinBox_Black")
    nodes = mat_box.node_tree.nodes
    links = mat_box.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.34
    bsdf.inputs["Metallic"].default_value = 0.05
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["finbox"] = mat_box

    # 5. White Composite Thruster Fins (matching PVW_2601_1400x.jpg.webp)
    mat_fin = bpy.data.materials.new(name="Mat_Thruster_Fin_White")
    nodes = mat_fin.node_tree.nodes
    links = mat_fin.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.86, 0.87, 0.89, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Metallic"].default_value = 0.04
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mats["fin"] = mat_fin

    return mats


def sample_core_deck_z(bvh_core, x, y):
    """
    Raycast straight down (-Z_sw) onto raw Jam_60.stl's native SolidWorks recessed pocket floor.
    In Jam_60.stl, Ilir Bordoniqi already modeled the exact 5.1 mm recessed pocket floor
    (from X=0.0519 to X=1.7680). We shrink (x, y) by 0.5% toward the pocket center (0.91, 0.0)
    so boundary vertices of JAM_DCover always hit the interior pocket floor instead of the outer rail wall.
    """
    sx = 0.91 + (x - 0.91) * 0.992
    sy = y * 0.985
    loc, _, _, _ = bvh_core.ray_cast(Vector((sx, sy, 0.5)), Vector((0.0, 0.0, -1.0)))
    if loc is not None:
        return loc.z
    loc2, _, _, _ = bvh_core.ray_cast(Vector((x, y * 0.95, 0.5)), Vector((0.0, 0.0, -1.0)))
    if loc2 is not None:
        return loc2.z
    return 0.0710


def sample_core_hull_z(bvh_core, x, y):
    """Raycast straight up (+Z_sw) onto raw Jam_60.stl's bottom hull."""
    sx = 0.91 + (x - 0.91) * 0.990
    sy = y * 0.980
    loc, _, _, _ = bvh_core.ray_cast(Vector((sx, sy, -0.5)), Vector((0.0, 0.0, 1.0)))
    if loc is not None:
        return loc.z
    return 0.0020


def drape_mesh_to_jam_rocker(mesh, role, bvh_core, sw_dz_to_assembled=0.0):
    """
    Drape and seat all components in SolidWorks assembly space so their vertex coordinates
    are baked directly in the Constructed (Assembled) state at obj.location = (0, 0, 0):
    - Jam_60_Core already has the 5.1 mm recessed deck pocket modeled in SolidWorks; we keep its
      exact CAD pocket perimeter and only recess the two narrow stringer slots.
    - JAM_DCover (5.1 mm thick EVA pad) is draped via BVHTree raycast directly onto Jam_60_Core's
      native CAD pocket floor (+0.4 mm proud clearance) so zero core triangles can ever bleed through.
    - JAM_Stringer preserves 100% of Ilir's native SolidWorks 3D rocker curvature, translated down
      by the exact linear CAD assembly offset into the internal foam core and clamped inside the hull/pocket.
    """
    if role == "core":
        # Jam_60.stl already has the 5.1mm recessed deck pocket modeled in SolidWorks.
        # Slightly lower interior pocket floor vertices (-1.5mm) so JAM_Pocket_Liner sits cleanly above
        # large CAD triangles with zero Z-fighting in exploded view.
        for v in mesh.vertices:
            if v.co.z > 0.048 and 0.065 < v.co.x < 1.755:
                z_fl = sample_core_deck_z(bvh_core, v.co.x, v.co.y)
                if v.co.z <= z_fl + 0.0012:
                    v.co.z -= 0.0018
    elif role == "pocket":
        # Smooth CAD cavity floor liner draped directly on Jam_60_Core's pocket floor (+1.2mm clear of raw core floor)
        z_ref_bot = 0.3232
        for v in mesh.vertices:
            z_floor = sample_core_deck_z(bvh_core, v.co.x, v.co.y)
            local_h = (v.co.z - z_ref_bot) * 0.12  # 0.0 to 0.0006m thin liner
            recess_str = -0.0032 if (0.13 < v.co.x < 1.74 and abs(v.co.y) <= 0.0105) else 0.0
            v.co.z = z_floor + 0.0008 + recess_str + local_h
    elif role == "deck":
        # JAM_DCover has v.co.z in [0.3232, 0.3283] (5.1mm thick).
        # Seat bottom of pad at z_floor + 0.0005m so top of pad sits at z_floor + 0.0056m (flush/proud of 5.1mm pocket wall).
        z_ref_bot = 0.3232
        for v in mesh.vertices:
            z_floor = sample_core_deck_z(bvh_core, v.co.x, v.co.y)
            local_h = v.co.z - z_ref_bot
            v.co.z = z_floor + 0.0005 + local_h
    elif role == "stringer":
        # Build BVHTree on JAM_Stringer's own SolidWorks mesh so we preserve 100% of its cross-sectional
        # thickness while seating its top surface 4.9 mm below JAM_DCover's top surface across the entire
        # nonlinear rocker curve (guaranteed 0 vertices above deck and 0 vertices below hull at scale=1.0).
        bm_str = bmesh.new()
        bm_str.from_mesh(mesh)
        bvh_str = BVHTree.FromBMesh(bm_str)
        bm_str.free()
        for v in mesh.vertices:
            sx = max(0.072, min(1.755, v.co.x))
            loc_s, _, _, _ = bvh_str.ray_cast(Vector((sx, 0.0, 1.0)), Vector((0.0, 0.0, -1.0)))
            z_s_top = loc_s.z if loc_s is not None else v.co.z
            depth = max(0.0, z_s_top - v.co.z)
            z_fl = sample_core_deck_z(bvh_core, v.co.x, 0.0)
            z_hl = sample_core_hull_z(bvh_core, v.co.x, 0.0)
            v.co.z = max(z_hl + 0.0040, (z_fl + 0.0007) - depth)
    else:
        # Fin boxes and thruster fins: bake sw_dz_to_assembled directly into vertices
        if abs(sw_dz_to_assembled) > 1e-6:
            for v in mesh.vertices:
                v.co.z += sw_dz_to_assembled

    mesh.update()


def assign_uvs_in_sw_space(mesh, role):
    """
    Assign planar/box UV coordinates in SolidWorks assembly space BEFORE rotating to standing space.
    - JAM_DCover gets the 4K graphic UV on BOTH top (normal Z > 0.35) and bottom (normal Z < -0.35) faces
      so the Formula Fun branding is visible from every angle, while perimeter side walls map to clean border color.
    - Jam_60_Core gets uniform 3D triplanar UVs scaled at 3.2 cycles per meter for realistic cellular bead scale.
    - JAM_Stringer gets lengthwise wood-grain UVs.
    """
    uv_layer = mesh.uv_layers.active
    if not uv_layer:
        uv_layer = mesh.uv_layers.new(name="UVMap")

    if role == "deck":
        x_min, x_max = 0.0519, 1.7680
        y_min, y_max = -0.2042, 0.2042
        for poly in mesh.polygons:
            if abs(poly.normal.z) > 0.35:
                for loop_idx in poly.loop_indices:
                    v_co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                    u = (v_co.y - y_min) / (y_max - y_min)
                    v = (v_co.x - x_min) / (x_max - x_min)
                    uv_layer.data[loop_idx].uv = (max(0.002, min(0.998, u)), max(0.002, min(0.998, v)))
            else:
                for loop_idx in poly.loop_indices:
                    uv_layer.data[loop_idx].uv = (0.02, 0.20)
    elif role in ("core", "pocket"):
        scale = 3.2
        for poly in mesh.polygons:
            n = poly.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for loop_idx in poly.loop_indices:
                co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                if az >= ax and az >= ay:
                    uv = (co.x * scale, co.y * scale)
                elif ay >= ax:
                    uv = (co.x * scale, co.z * scale)
                else:
                    uv = (co.y * scale, co.z * scale)
                uv_layer.data[loop_idx].uv = (uv[0] % 1.0, uv[1] % 1.0)
    else:
        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                uv_layer.data[loop_idx].uv = ((co.x * 0.6) % 1.0, ((co.y + co.z) * 4.0) % 1.0)


def create_deck_plugs_and_handle_recess(mats, bvh_core):
    """
    Create the 6 molded black polymer deck through-plugs (4 side fin plugs, 1 center fin plug,
    1 rear leash plug) + dark recessed carry-handle well liner seated on the exact CAD deck pad surface.
    """
    bm = bmesh.new()

    def z_pad_top(x, y):
        return sample_core_deck_z(bvh_core, x, y) + 0.0056

    plug_coords = [
        (0.394, +0.124, 0.0130),
        (0.394, -0.124, 0.0130),
        (0.292, +0.114, 0.0130),
        (0.292, -0.114, 0.0130),
        (0.200,  0.000, 0.0140),
        (0.095,  0.000, 0.0145),
    ]

    for px, py, rad in plug_coords:
        pz = z_pad_top(px, py)
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=True,
            segments=28,
            radius1=rad,
            radius2=rad * 0.96,
            depth=0.0022,
            matrix=Matrix.Translation((px, py, pz + 0.0005)),
        )
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=True,
            segments=20,
            radius1=rad * 0.44,
            radius2=rad * 0.44,
            depth=0.0028,
            matrix=Matrix.Translation((px, py, pz + 0.0008)),
        )

    # Carry handle slot dark inner pocket (X in [0.809..0.918], Y in [-0.013..+0.013])
    pz_handle = z_pad_top(0.8636, 0.0) - 0.0042
    bmesh.ops.create_cube(
        bm,
        size=1.0,
        matrix=Matrix.Translation((0.8636, 0.0, pz_handle)) @ Matrix.Diagonal((0.109, 0.026, 0.0025, 1.0)),
    )

    mesh = bpy.data.meshes.new("Jam_Deck_Hardware_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    assign_uvs_in_sw_space(mesh, "finbox")
    mesh.transform(sw_to_standing_matrix())

    obj = bpy.data.objects.new("Jam_Deck_Hardware", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mats["finbox"])
    return obj


def build_scene_for_colorway(colorway="blackout"):
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    mats = build_materials(colorway)
    M_stand = sw_to_standing_matrix()

    # Build BVHTree from raw Jam_60.stl in SolidWorks assembly space before any modification
    raw_core_stl = os.path.join(PARTS_DIR, "Jam_60.stl")
    bpy.ops.wm.stl_import(filepath=raw_core_stl)
    tmp_core_obj = bpy.context.selected_objects[0]
    bm_raw_core = bmesh.new()
    bm_raw_core.from_mesh(tmp_core_obj.data)
    bvh_core = BVHTree.FromBMesh(bm_raw_core)
    bm_raw_core.free()
    bpy.data.objects.remove(tmp_core_obj, do_unlink=True)

    objects_by_name = {}
    for item in SW_INSTANCES:
        stl_path = os.path.join(PARTS_DIR, item["stl"])
        bpy.ops.wm.stl_import(filepath=stl_path)
        obj = bpy.context.selected_objects[0]
        obj.name = item["name"]
        mesh = obj.data
        mesh.name = f"{item['name']}_Mesh"

        # Attach material for component role
        obj.data.materials.clear()
        obj.data.materials.append(mats[item["role"]])

        # Apply SolidWorks component instance transform in SW assembly space
        M_sw = sw_col_major_to_blender_matrix(item["sw_matrix"])
        mesh.transform(M_sw)

        # Assign UVs in SW assembly space while JAM_DCover is still flat (so top/bottom face normals are +-Z)
        assign_uvs_in_sw_space(mesh, item["role"])

        # Drape & seat all meshes directly into Constructed (Assembled) coordinates in SW space
        drape_mesh_to_jam_rocker(
            mesh,
            item["role"],
            bvh_core,
            sw_dz_to_assembled=item.get("sw_dz_to_assembled", 0.0),
        )

        # Transform from SW assembly space to Standing Upright space (X=Width, Y=Thickness, Z=Length)
        mesh.transform(M_stand)

        # For Jam_60_Core, add two microscopic 1-micron degenerate triangles at symmetric Y_bl bounds
        # (-0.20745m and +0.20745m) so the union bounding box (extent) of the entire surfboard in
        # Apple Quick Look (.USDZ) and <model-viewer> (.GLB) has its exact mathematical center at
        # (0.000000, 0.000000, 0.000000) — the true geometric middle of the board.
        if item["role"] == "core":
            bm_bal = bmesh.new()
            bm_bal.from_mesh(mesh)
            for y_sym in (-0.20745, +0.20745):
                v1 = bm_bal.verts.new((0.0, y_sym, 0.0))
                v2 = bm_bal.verts.new((1e-6, y_sym, 0.0))
                v3 = bm_bal.verts.new((0.0, y_sym, 1e-6))
                bm_bal.faces.new((v1, v2, v3))
            bm_bal.to_mesh(mesh)
            bm_bal.free()
            mesh.update()

        # Smooth shading
        for poly in mesh.polygons:
            poly.use_smooth = True

        objects_by_name[item["name"]] = (obj, item)

    # Add deck plugs & carry handle recess liner seated on the exact CAD deck pad surface
    hw_obj = create_deck_plugs_and_handle_recess(mats, bvh_core)
    objects_by_name["Jam_Deck_Hardware"] = (
        hw_obj,
        {
            "name": "Jam_Deck_Hardware",
            "role": "finbox",
            "assembled_dz": 0.0,
            "exploded_dz": +0.2850,
            "twinnie_dz": +0.2950,
        },
    )

    return scene, objects_by_name, mats


def set_assembly_state(objects_by_name, mode="assembled", include_fins=True):
    """
    mode in ["assembled", "exploded", "twinnie"]
    """
    for name, (obj, cfg) in objects_by_name.items():
        if cfg["role"] == "fin" and not include_fins:
            obj.hide_render = True
            obj.hide_viewport = True
        elif mode == "assembled" and cfg["role"] in ("stringer", "pocket"):
            # When constructed (assembled), internal stringers and pocket liner are enclosed under the EVA deck pad
            obj.hide_render = True
            obj.hide_viewport = True
        else:
            obj.hide_render = False
            obj.hide_viewport = False

        if mode == "assembled":
            dz = cfg["assembled_dz"]
        elif mode == "exploded":
            dz = cfg["exploded_dz"]
        elif mode == "twinnie":
            dz = cfg["twinnie_dz"]
        else:
            dz = cfg["assembled_dz"]

        obj.scale = Vector((1.0, 1.0, 1.0))
        # Since Y_bl = -Z_sw, delta Y_bl = -dz
        obj.location = Vector((0.0, -dz, 0.0))


def setup_studio_lighting_and_camera(scene, res_x=2000, res_y=2000, transparent=True):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.60
    scene.view_settings.gamma = 1.0

    world = bpy.data.worlds.new("JamStudioWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.94, 0.94, 0.96, 1.0)
        bg.inputs[1].default_value = 0.36

    key_data = bpy.data.lights.new("KeyLight", type="AREA")
    key_data.energy = 175.0
    key_data.size = 3.5
    key_obj = bpy.data.objects.new("KeyLight", key_data)
    scene.collection.objects.link(key_obj)
    key_obj.location = Vector((-1.8, -3.2, 1.2))
    key_obj.rotation_euler = (Vector((0, 0, 0)) - key_obj.location).to_track_quat("-Z", "Y").to_euler()

    fill_data = bpy.data.lights.new("FillLight", type="AREA")
    fill_data.energy = 125.0
    fill_data.size = 4.0
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    scene.collection.objects.link(fill_obj)
    fill_obj.location = Vector((2.2, -2.8, -0.8))
    fill_obj.rotation_euler = (Vector((0, 0, 0)) - fill_obj.location).to_track_quat("-Z", "Y").to_euler()

    rim_data = bpy.data.lights.new("RimLight", type="AREA")
    rim_data.energy = 135.0
    rim_data.size = 2.8
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    scene.collection.objects.link(rim_obj)
    rim_obj.location = Vector((0.8, -1.6, 2.4))
    rim_obj.rotation_euler = (Vector((0, 0, 0)) - rim_obj.location).to_track_quat("-Z", "Y").to_euler()

    hull_data = bpy.data.lights.new("HullLight", type="AREA")
    hull_data.energy = 210.0
    hull_data.size = 3.8
    hull_obj = bpy.data.objects.new("HullLight", hull_data)
    scene.collection.objects.link(hull_obj)
    hull_obj.location = Vector((-1.2, 3.2, 0.6))
    hull_obj.rotation_euler = (Vector((0, 0, 0)) - hull_obj.location).to_track_quat("-Z", "Y").to_euler()

    cam_data = bpy.data.cameras.new("StudioCam")
    cam_data.lens = 50.0
    cam_obj = bpy.data.objects.new("StudioCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    return cam_obj, cam_data


def aim_camera(cam_obj, loc, target=(0.0, 0.0, 0.0), roll_deg=0.0, up_vec=None):
    cam_obj.location = Vector(loc)
    forward = (Vector(target) - cam_obj.location).normalized()
    if up_vec is not None:
        u_raw = Vector(up_vec).normalized()
        right = forward.cross(u_raw).normalized()
        up = right.cross(forward).normalized()
        back = -forward
        rot_mat = Matrix((
            (right.x, up.x, back.x, 0.0),
            (right.y, up.y, back.y, 0.0),
            (right.z, up.z, back.z, 0.0),
            (0.0,     0.0,  0.0,    1.0),
        ))
        cam_obj.rotation_euler = rot_mat.to_euler()
        return
    direction = Vector(target) - cam_obj.location
    quat = direction.to_track_quat("-Z", "Y")
    eul = quat.to_euler()
    cam_obj.rotation_euler = eul
    if abs(roll_deg) > 1e-4:
        mat = quat.to_matrix().to_4x4()
        roll_mat = Matrix.Rotation(math.radians(roll_deg), 4, "Z")
        cam_obj.rotation_euler = (mat @ roll_mat).to_euler()


def package_usdz_from_usdc(usdc_path, usdz_path, colorway, include_internal_textures=True):
    usda_path = usdc_path.replace(".usdc", ".usda")
    subprocess.run(["/usr/bin/usdcat", "-o", usda_path, usdc_path], cwd=BASE_DIR, check=True)
    with open(usda_path, "r") as f:
        txt = f.read()
    txt = re.sub(r"@[^@]*textures/", r"@textures/", txt)
    with open(usda_path, "w") as f:
        f.write(txt)
    subprocess.run(["/usr/bin/usdcat", "-o", usdc_path, usda_path], cwd=BASE_DIR, check=True)
    if os.path.exists(usda_path):
        os.remove(usda_path)

    # Always remove existing .usdz before running usdzip so archives are created fresh
    if os.path.exists(usdz_path):
        os.remove(usdz_path)

    deck_tex = (
        "textures/jam_deck_blackout_basecolor_4k.png"
        if colorway == "blackout"
        else "textures/jam_deck_yellow_basecolor_4k.png"
    )
    tex_list = [
        deck_tex,
        "textures/jam_deck_normal_4k.png",
        "textures/jam_deck_roughness_4k.png",
        "textures/jam_foam_basecolor_4k.png",
        "textures/jam_foam_normal_4k.png",
        "textures/jam_foam_roughness_4k.png",
    ]
    if include_internal_textures:
        tex_list.extend([
            "textures/jam_pocket_floor_basecolor_2k.png",
            "textures/jam_stringer_wood_2k.png",
        ])

    subprocess.run(
        ["/usr/bin/usdzip", usdz_path, os.path.basename(usdc_path)] + tex_list,
        cwd=BASE_DIR,
        check=True,
    )
    chk = subprocess.run(["/usr/bin/usdchecker", usdz_path], cwd=BASE_DIR, capture_output=True, text=True)
    print(f"[USDCHECKER] {os.path.basename(usdz_path)}: rc={chk.returncode} {chk.stdout.strip()}")
    print(f"[SUCCESS] Packaged Apple AR USDZ: {usdz_path} ({os.path.getsize(usdz_path):,} bytes)")


def set_core_symmetric_y_bound(core_mesh, y_bound):
    """Update the last 6 balancer vertices on Jam_60_Core_Mesh so the scene extent is 100% centered at (0,0,0)."""
    n = len(core_mesh.vertices)
    if n >= 6:
        # First 3 vertices at -y_bound, last 3 at +y_bound
        core_mesh.vertices[n - 6].co = Vector((0.0, -y_bound, 0.0))
        core_mesh.vertices[n - 5].co = Vector((1e-6, -y_bound, 0.0))
        core_mesh.vertices[n - 4].co = Vector((0.0, -y_bound, 1e-6))
        core_mesh.vertices[n - 3].co = Vector((0.0, +y_bound, 0.0))
        core_mesh.vertices[n - 2].co = Vector((1e-6, +y_bound, 0.0))
        core_mesh.vertices[n - 1].co = Vector((0.0, +y_bound, 1e-6))
        core_mesh.update()


def bake_animation_and_export(scene, objects_by_name, colorway="blackout"):
    """
    Export:
    1. Static Constructed (Assembled) GLB + USDZ (`Jam_60_<Color>_Assembled.glb` / `.usdz`):
       - Contains the exterior constructed components (`Jam_60_Core`, `JAM_DCover`, `Jam_Deck_Hardware`,
         3 fin boxes, 3 thruster fins) all baked at (0, 0, 0) with exact (0, 0, 0) bounding-box center.
    2. Animated 10-Second Exploded Loop GLB + USDZ (`Jam_60_<Color>_Exploded.glb` / `.usdz`):
       - Includes all CAD components + single center wood stringer (`JAM_Stringer`) + recessed pocket liner.
       - All components maintain constant `scale = (1.0, 1.0, 1.0)` across all 240 frames (zero scaling pop),
         because `JAM_Stringer` and `JAM_Pocket_Liner` are seated cleanly inside the recessed pocket floor
         underneath `JAM_DCover` when constructed.
       - Starts at the Exploded state at Frame 1 (so static thumbnails and Frame 1 previews show the
         Exploded View immediately), smoothly assembles into Constructed, and explodes back out in a
         seamless 240-frame loop, with exact (0, 0, 0) bounding-box pivot center.
    """
    cap = "Blackout" if colorway == "blackout" else "Yellow"
    core_obj, _ = objects_by_name["Jam_60_Core"]

    # 1. Export Static Constructed (Assembled) GLB + USDZ with symmetric +/-0.20745m thickness bound
    set_core_symmetric_y_bound(core_obj.data, 0.20745)
    set_assembly_state(objects_by_name, mode="assembled", include_fins=True)
    for o in bpy.data.objects:
        o.select_set(False)
    for name, (obj, cfg) in objects_by_name.items():
        if cfg["role"] not in ("stringer", "pocket"):
            obj.hide_viewport = False
            obj.hide_render = False
            obj.select_set(True)

    glb_assembled = os.path.join(BASE_DIR, f"Jam_60_{cap}_Assembled.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb_assembled,
        use_selection=True,
        export_format="GLB",
        export_animations=False,
        export_materials="EXPORT",
        export_yup=True,
    )
    print(f"[OK] Exported {glb_assembled}")

    usdc_assembled = os.path.join(BASE_DIR, f"Jam_60_{cap}_Assembled.usdc")
    usdz_assembled = os.path.join(BASE_DIR, f"Jam_60_{cap}_Assembled.usdz")
    bpy.ops.wm.usd_export(
        filepath=usdc_assembled,
        selected_objects_only=True,
        export_animation=False,
        convert_orientation=True,
        export_global_up_selection="Y",
        convert_scene_units="METERS",
        meters_per_unit=1.0,
        generate_preview_surface=True,
        export_textures_mode="KEEP",
        relative_paths=True,
        convert_world_material=False,
        export_materials=True,
        export_uvmaps=True,
        export_normals=True,
    )
    package_usdz_from_usdc(usdc_assembled, usdz_assembled, colorway, include_internal_textures=False)

    # 2. Bake 240-frame (10s @ 24fps) seamless Exploded animation loop with symmetric +/-0.51745m bound
    set_core_symmetric_y_bound(core_obj.data, 0.51745)
    for o in bpy.data.objects:
        o.select_set(False)
    for name, (obj, cfg) in objects_by_name.items():
        obj.hide_viewport = False
        obj.hide_render = False
        obj.select_set(True)

    scene.frame_start = 1
    scene.frame_end = 240
    scene.render.fps = 24

    # Seamless loop starting and ending in Exploded ('twinnie') state so Frame 1 is the Exploded View,
    # smoothly assembling into Constructed in the middle of the cycle:
    keyframes = [
        (1, "twinnie"),
        (35, "twinnie"),
        (100, "assembled"),
        (140, "assembled"),
        (205, "twinnie"),
        (240, "twinnie"),
    ]

    for name, (obj, cfg) in objects_by_name.items():
        obj.animation_data_clear()
        obj.scale = Vector((1.0, 1.0, 1.0))
        for frame_no, st in keyframes:
            scene.frame_set(frame_no)
            dz = cfg["assembled_dz"] if st == "assembled" else cfg["twinnie_dz"]
            obj.location = Vector((0.0, -dz, 0.0))
            obj.keyframe_insert(data_path="location", frame=frame_no)

    # Set frame to 1 (Exploded state) for USDZ and GLB export
    scene.frame_set(1)

    usdc_path = os.path.join(BASE_DIR, f"Jam_60_{cap}_Exploded.usdc")
    usdz_path = os.path.join(BASE_DIR, f"Jam_60_{cap}_Exploded.usdz")
    glb_exploded = os.path.join(BASE_DIR, f"Jam_60_{cap}_Exploded.glb")

    bpy.ops.wm.usd_export(
        filepath=usdc_path,
        selected_objects_only=True,
        export_animation=True,
        convert_orientation=True,
        export_global_up_selection="Y",
        convert_scene_units="METERS",
        meters_per_unit=1.0,
        generate_preview_surface=True,
        export_textures_mode="KEEP",
        relative_paths=True,
        convert_world_material=False,
        export_materials=True,
        export_uvmaps=True,
        export_normals=True,
    )

    # Push down to NLA tracks for unified glTF animation track
    for name, (obj, _) in objects_by_name.items():
        if obj.animation_data and obj.animation_data.action:
            track = obj.animation_data.nla_tracks.new()
            track.name = "ExplodedLoop"
            track.strips.new("ExplodedLoop", 1, obj.animation_data.action)
            obj.animation_data.action = None

    bpy.ops.export_scene.gltf(
        filepath=glb_exploded,
        use_selection=True,
        export_format="GLB",
        export_animations=True,
        export_animation_mode="NLA_TRACKS",
        export_nla_strips_merged_animation_name="ExplodedLoop",
        export_materials="EXPORT",
        export_yup=True,
    )
    print(f"[OK] Exported {glb_exploded}")

    package_usdz_from_usdc(usdc_path, usdz_path, colorway, include_internal_textures=True)
    # Restore tight core bound after export
    set_core_symmetric_y_bound(core_obj.data, 0.20745)


def enable_cycles_metal_raytracing(scene, samples=96):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 4


def create_studio_backdrop_plane(color=(0.965, 0.960, 0.948, 1.0), roughness=0.92):
    """Create a large studio backdrop plane behind the exploded surfboard to catch real raytraced softbox shadows."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=14.0)
    mesh = bpy.data.meshes.new("StudioBackdrop_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("StudioBackdrop", mesh)
    bpy.context.scene.collection.objects.link(obj)

    mat = bpy.data.materials.new("Mat_Studio_Backdrop")
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.04
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    return obj


def render_all_views(scene, objects_by_name, colorway="blackout"):
    cam_obj, cam_data = setup_studio_lighting_and_camera(scene, res_x=1800, res_y=1800, transparent=True)

    # Enable Apple M5 Pro Metal GPU Raytracing (Cycles) for photorealistic still renders
    enable_cycles_metal_raytracing(scene, samples=80)

    # 1. Orthographic / Studio Front Deck View (matching Jam_Black.png / Jam_Yellow.png)
    set_assembly_state(objects_by_name, mode="assembled", include_fins=True)
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 2560
    cam_data.lens = 65.0
    aim_camera(cam_obj, loc=(0.0, -4.5, 0.0), target=(0.0, 0.0, 0.0), up_vec=(0.0, 0.0, 1.0))
    p_deck = os.path.join(RENDERS_DIR, f"jam_{colorway}_deck_ortho.png")
    scene.render.filepath = p_deck
    bpy.ops.render.render(write_still=True)
    print(f"[OK] Rendered Cycles Raytraced Deck Ortho: {p_deck}")

    # 2. Twinnie-Style Isometric Exploded View (2560x1440 QHD Cycles Raytraced with Inter-Layer Contact Shadows)
    set_assembly_state(objects_by_name, mode="twinnie", include_fins=False)
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_x = 2560
    scene.render.resolution_y = 1440
    cam_data.lens = 47.0
    aim_camera(cam_obj, loc=(2.82, -1.42, -1.82), target=(0.0, 0.01, -0.05), up_vec=(0.0, -0.96, 0.28))
    p_twinnie = os.path.join(RENDERS_DIR, f"jam_{colorway}_twinnie_exploded.png")
    scene.render.filepath = p_twinnie
    bpy.ops.render.render(write_still=True)
    print(f"[OK] Rendered Cycles Twinnie-style exploded view: {p_twinnie}")

    # 3. Twinnie-Style Isometric Exploded View WITH Thruster Fins included (2560x1440 QHD Cycles Raytraced)
    set_assembly_state(objects_by_name, mode="twinnie", include_fins=True)
    cam_data.lens = 45.0
    aim_camera(cam_obj, loc=(2.95, -1.40, -1.86), target=(0.0, 0.03, -0.09), up_vec=(0.0, -0.96, 0.28))
    p_twinnie_fins = os.path.join(RENDERS_DIR, f"jam_{colorway}_exploded_full_assembly.png")
    scene.render.filepath = p_twinnie_fins
    bpy.ops.render.render(write_still=True)
    print(f"[OK] Rendered Cycles full exploded assembly view: {p_twinnie_fins}")

    # 4. 4K (3840x2160) Photorealistic Studio Hero — Architectural Warm Alabaster Cyclorama with Raytraced Drop Shadows
    enable_cycles_metal_raytracing(scene, samples=96)
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.resolution_x = 3840
    scene.render.resolution_y = 2160
    set_assembly_state(objects_by_name, mode="twinnie", include_fins=True)
    backdrop = create_studio_backdrop_plane(color=(0.965, 0.960, 0.948, 1.0), roughness=0.90)
    cam_data.lens = 45.0
    cam_loc_hero = Vector((2.95, -1.40, -1.86))
    cam_tgt_hero = Vector((0.0, 0.03, -0.09))
    aim_camera(cam_obj, loc=cam_loc_hero, target=cam_tgt_hero, up_vec=(0.0, -0.96, 0.28))
    view_dir = (cam_tgt_hero - cam_loc_hero).normalized()
    backdrop.location = cam_tgt_hero + view_dir * 1.25
    backdrop.rotation_euler = (-view_dir).to_track_quat("Z", "Y").to_euler()

    p_hero_studio = os.path.join(RENDERS_DIR, f"jam_{colorway}_exploded_hero_4k.png")
    scene.render.filepath = p_hero_studio
    bpy.ops.render.render(write_still=True)
    print(f"[OK] Rendered 4K Photorealistic Studio Exploded Hero: {p_hero_studio}")

    # 5. 4K (3840x2160) Photorealistic Editorial Hero — Dramatic Close-Up 3/4 Perspective on Warm Bone Gallery Surface
    cam_data.lens = 54.0
    cam_loc_ed = Vector((2.38, -1.18, -1.42))
    cam_tgt_ed = Vector((-0.02, -0.02, 0.04))
    aim_camera(cam_obj, loc=cam_loc_ed, target=cam_tgt_ed, up_vec=(0.0, -0.96, 0.28))
    view_dir_ed = (cam_tgt_ed - cam_loc_ed).normalized()
    backdrop.location = cam_tgt_ed + view_dir_ed * 1.15
    backdrop.rotation_euler = (-view_dir_ed).to_track_quat("Z", "Y").to_euler()

    p_hero_editorial = os.path.join(RENDERS_DIR, f"jam_{colorway}_exploded_editorial_4k.png")
    scene.render.filepath = p_hero_editorial
    bpy.ops.render.render(write_still=True)
    print(f"[OK] Rendered 4K Photorealistic Editorial Exploded Hero: {p_hero_editorial}")

    bpy.data.objects.remove(backdrop, do_unlink=True)

    # 6. Bottom Thruster Hull View (matching PVW_2601_1400x.jpg.webp) — only needed once
    if colorway == "blackout":
        set_assembly_state(objects_by_name, mode="assembled", include_fins=True)
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.resolution_x = 1400
        scene.render.resolution_y = 2560
        cam_data.lens = 65.0
        aim_camera(cam_obj, loc=(0.0, 4.5, 0.0), target=(0.0, 0.0, 0.0), up_vec=(0.0, 0.0, 1.0))
        p_hull = os.path.join(RENDERS_DIR, "jam_bottom_hull_thruster.png")
        scene.render.filepath = p_hull
        bpy.ops.render.render(write_still=True)
        print(f"[OK] Rendered Cycles bottom thruster hull view: {p_hull}")

    # 7. Render 96-frame (4.00s @ 24fps, 1920x1080) Twinnie-Style Exploded Animation MP4 Video
    render_twinnie_exploded_video(scene, cam_obj, cam_data, objects_by_name, colorway)


def smoothstep(edge0, edge1, x):
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def render_twinnie_exploded_video(scene, cam_obj, cam_data, objects_by_name, colorway="blackout"):
    """
    Render a 96-frame (4.00s @ 24fps, 1920x1080) widescreen exploded animation video
    matching Twinnie_Exploded_Animation_Upscaled.mp4.
    """
    cap = "Blackout" if colorway == "blackout" else "Yellow"
    frames_dir = f"/tmp/jam_anim_{colorway}"
    os.makedirs(frames_dir, exist_ok=True)

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16

    cam_data.lens = 47.0
    aim_camera(cam_obj, loc=(2.82, -1.42, -1.82), target=(0.0, 0.01, -0.05), up_vec=(0.0, -0.96, 0.28))

    for name, (obj, cfg) in objects_by_name.items():
        if cfg["role"] == "fin":
            obj.hide_render = True
            obj.hide_viewport = True
        else:
            obj.hide_render = False
            obj.hide_viewport = False

    n_frames = 96  # 4.0s @ 24fps
    for f_idx in range(1, n_frames + 1):
        u_deck = smoothstep(10.0, 58.0, float(f_idx))
        u_str = smoothstep(18.0, 66.0, float(f_idx))
        u_box = smoothstep(14.0, 62.0, float(f_idx))

        for name, (obj, cfg) in objects_by_name.items():
            role = cfg["role"]
            z0 = cfg["assembled_dz"]
            z1 = cfg["twinnie_dz"]
            if role == "deck" or name == "Jam_Deck_Hardware":
                dz = z0 + u_deck * (z1 - z0)
            elif role == "stringer":
                dz = z0 + u_str * (z1 - z0)
            elif role == "finbox":
                dz = z0 + u_box * (z1 - z0)
            else:
                dz = z0
            obj.location = Vector((0.0, -dz, 0.0))
            obj.scale = Vector((1.0, 1.0, 1.0))

        frame_path = os.path.join(frames_dir, f"frame_{f_idx:04d}.png")
        scene.render.filepath = frame_path
        bpy.ops.render.render(write_still=True)

    mp4_out = os.path.join(RENDERS_DIR, f"Jam_60_{cap}_Exploded_Animation.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "24",
        "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-filter_complex", "color=white:s=1920x1080:r=24[bg];[bg][0:v]overlay=shortest=1,format=yuv420p[v]",
        "-map", "[v]",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-level", "4.1",
        "-crf", "18",
        "-movflags", "+faststart",
        mp4_out,
    ]
    subprocess.run(cmd, check=True)
    print(f"[SUCCESS] Encoded Exploded Animation MP4: {mp4_out} ({os.path.getsize(mp4_out):,} bytes)")


def main():
    for cw in ["blackout", "yellow"]:
        print(f"\n=== BUILDING 6'0\" JAM SURFBOARD ({cw.upper()}) ===")
        scene, objects_by_name, mats = build_scene_for_colorway(cw)
        render_all_views(scene, objects_by_name, cw)
        bake_animation_and_export(scene, objects_by_name, cw)


if __name__ == "__main__":
    main()
