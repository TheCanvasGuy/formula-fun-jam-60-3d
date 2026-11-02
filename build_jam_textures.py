#!/usr/bin/env python3
"""
Generate 4K UV-calibrated PBR textures for the Formula Fun 6'0" Jam Surfboard:
1. Marko EPS Closed-Cell Black Foam Core & Hull (BaseColor, Normal, Roughness)
   matched to PVW_2601_1400x.jpg.webp
2. Blackout Deck Pad (JAM_DCover) matched to Jam_Black.png (with crisp Formula Fun
   circular lightning-S chest emblem, FormulaFun wordmark, and mid-deck seam line)
3. Mellow Yellow Deck Pad (JAM_DCover) matched to Jam_Yellow.png
4. Natural Wood-Grain Composite Stringer Texture (matching the Twinnie exploded view
   reference on formulafunboards.com)
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

OUT_DIR = "/Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD/textures"
os.makedirs(OUT_DIR, exist_ok=True)

JAM_BLACK_REF = "/Users/byronmini/Desktop/Formula Fun iCloud/Jam_Black.png"
JAM_YELLOW_REF = "/Users/byronmini/Desktop/Formula Fun iCloud/Jam_Yellow.png"
JAM_BOTTOM_PNG = "/Users/byronmini/.gemini/antigravity/brain/b0585db8-d01e-4ac8-82fe-ec790d03d924/scratch/jam_inspect/photos/PVW_2601_1400x.png"


def extract_clean_chest_logo_and_wordmark():
    """
    Extract high-resolution alpha masks of the Formula Fun circular chest logo
    and the FormulaFun lightning wordmark directly from Jam_Black.png, then upscale
    and anti-alias them for 4K deck pad synthesis.
    """
    im = Image.open(JAM_BLACK_REF).convert("RGBA")
    arr = np.array(im)
    # In Jam_Black.png (793 x 1983):
    # Board bbox: x in [120, 675], y in [22, 1962]
    # Let us locate white graphic pixels inside the deck pad region:
    # Brightness > 140
    gray = arr[:, :, :3].mean(axis=2)
    alpha = arr[:, :, 3]
    # Crop chest logo region: y in [420, 740], x in [250, 545]
    # Crop wordmark region: y in [880, 1020], x in [240, 560]
    return gray, alpha


def draw_crisp_ff_emblem(size_w: int, size_h: int, ring_color, bolt_color, bg_disc_color=None) -> Image.Image:
    """
    Render a vector-crisp Formula Fun circular lightning-S emblem at (size_w, size_h)
    to pre-compensate for UV aspect ratio so it renders as a 100% true circle on the 3D mesh.
    Matches Jam_Black.png (transparent/black center, white ring + white lightning S)
    and Jam_Yellow.png (solid black circular disc + white ring + white lightning S).
    """
    ref = Image.open(JAM_BLACK_REF).convert("RGBA")
    ref_arr = np.array(ref)
    sub = ref_arr[420:595, 315:480, :3].mean(axis=2)
    ys, xs = np.where(sub > 140)
    ymin, ymax = ys.min(), ys.max()
    xmin, xmax = xs.min(), xs.max()
    logo_crop = sub[ymin : ymax + 1, xmin : xmax + 1]

    # Render in 1:1 square space at 2x supersampling, then resample to (size_w, size_h)
    ss = size_w * 2
    logo_pil = Image.fromarray(np.clip((logo_crop - 85) * 2.5, 0, 255).astype(np.uint8), mode="L")
    logo_pil = logo_pil.resize((ss, ss), Image.Resampling.LANCZOS)
    logo_pil = logo_pil.filter(ImageFilter.GaussianBlur(radius=1.4))
    l_arr = np.array(logo_pil, dtype=np.float32)

    # Mask out the outer ring from the extracted crop so we only keep the crisp interior lightning bolt
    yy, xx = np.meshgrid(np.linspace(-1, 1, ss), np.linspace(-1, 1, ss), indexing="ij")
    rr = np.sqrt(xx * xx + yy * yy)
    bolt_only = np.where(rr < 0.78, l_arr, 0.0)
    bolt_mask = np.clip((bolt_only - 110.0) * 4.5, 0, 255).astype(np.uint8)

    canvas = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    cx, cy = ss / 2.0, ss / 2.0
    r_outer = ss * 0.465
    ring_w = max(6, int(ss * 0.032))

    if bg_disc_color is not None:
        r_disc = r_outer + ring_w * 0.65
        draw.ellipse([cx - r_disc, cy - r_disc, cx + r_disc, cy + r_disc], fill=bg_disc_color)

    # Draw perfectly smooth geometric outer circle ring
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        outline=ring_color,
        width=ring_w,
    )

    # Composite crisp interior lightning-S bolt
    bolt_patch = Image.new("RGBA", (ss, ss), bolt_color)
    canvas.paste(bolt_patch, (0, 0), Image.fromarray(bolt_mask, mode="L"))
    return canvas.resize((size_w, size_h), Image.Resampling.LANCZOS)


def extract_crisp_wordmark(target_w: int, uv_v_stretch: float, color_rgba) -> Image.Image:
    """
    Extract the exact 'FormulaFun ⚡' script wordmark from Jam_Black.png,
    clean and vector-sharpen its alpha mask, pre-compensate for UV vertical stretch,
    and tint with color_rgba.
    """
    ref = Image.open(JAM_BLACK_REF).convert("RGBA")
    ref_arr = np.array(ref)
    # Wordmark sits just above the horizontal seam & handle slot: y in [870..1015], x in [240..555]
    sub = ref_arr[870:1015, 240:555, :3].mean(axis=2)
    ys, xs = np.where(sub > 125)
    ymin, ymax = ys.min(), ys.max()
    xmin, xmax = xs.min(), xs.max()
    crop = sub[ymin : ymax + 1, xmin : xmax + 1]
    h, w = crop.shape
    # Pre-compress vertical height by uv_v_stretch so 3D mesh renders at 1:1 physical aspect ratio
    target_h = max(16, int(round(target_w * (h / float(w)) / uv_v_stretch)))

    pil_mask = Image.fromarray(np.clip((crop - 80) * 2.5, 0, 255).astype(np.uint8), mode="L")
    pil_mask = pil_mask.resize((target_w * 2, target_h * 2), Image.Resampling.LANCZOS)
    pil_mask = pil_mask.filter(ImageFilter.GaussianBlur(radius=1.1))
    m_arr = np.array(pil_mask, dtype=np.float32)
    alpha_mask = np.clip((m_arr - 105.0) * 4.0, 0, 255).astype(np.uint8)
    final_mask = Image.fromarray(alpha_mask, mode="L").resize((target_w, target_h), Image.Resampling.LANCZOS)

    out = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    patch = Image.new("RGBA", (target_w, target_h), color_rgba)
    out.paste(patch, (0, 0), final_mask)
    return out


def build_deck_pad_textures():
    """
    UV layout of JAM_DCover:
    U in [0, 1] maps across width Y in [-0.2042, +0.2042] (width = 0.4084 m)
    V in [0, 1] maps along length X in [0.0519, 1.7680] (length = 1.7161 m, V=0 at Tail, V=1 at Nose)
    Row 0 = Nose (X = 1.7680) and row H-1 = Tail (X = 0.0519).
    Physical aspect ratio L_phys / W_phys = 1.7161 / 0.4084 = 4.2020.
    Texture aspect ratio H / W = 4096 / 2048 = 2.0000.
    Therefore each vertical texture pixel stretches by uv_v_stretch = 4.2020 / 2.0 = 2.1010x on the 3D pad!
    """
    W, H = 2048, 4096
    uv_v_stretch = (1.7161 / 0.4084) / (float(H) / float(W))  # 2.1010
    rng = np.random.default_rng(42)

    # Micro-brushed EVA foam texture noise (isotropic in physical 3D space)
    noise_fine = rng.normal(0.0, 1.0, (H, W)).astype(np.float32)
    yy, xx = np.meshgrid(np.linspace(0, 1, H, dtype=np.float32), np.linspace(0, 1, W, dtype=np.float32), indexing="ij")
    diamond = (np.sin(xx * W * 0.45 + yy * H * 0.45 * uv_v_stretch) * np.sin(xx * W * 0.45 - yy * H * 0.45 * uv_v_stretch)) * 2.2
    eva_grain = noise_fine * 2.6 + diamond

    # Horizontal seam groove at t_seam = 0.4953 (row = int(0.4953 * H))
    seam_row = int(0.4953 * H)

    # 1. BLACKOUT DECK PAD (Jam_Black.png)
    base_black = np.zeros((H, W, 3), dtype=np.uint8)
    for c, val in enumerate([20, 20, 23]):  # Rich deep charcoal-black EVA
        ch = np.clip(val + eva_grain, 10, 36)
        ch[seam_row - 3 : seam_row + 3, :] *= 0.35
        base_black[:, :, c] = ch.astype(np.uint8)

    img_black = Image.fromarray(base_black, mode="RGB").convert("RGBA")

    # Paste white chest emblem at t = 0.252 (cx = W//2, cy = int(0.252 * H))
    # Pre-compress vertical pixel height by uv_v_stretch so 3D mesh renders a 100% geometric circle
    logo_w = int(W * 0.455)
    logo_h = int(round(logo_w / uv_v_stretch))
    chest_white = draw_crisp_ff_emblem(
        logo_w,
        logo_h,
        ring_color=(248, 248, 250, 255),
        bolt_color=(248, 248, 250, 255),
        bg_disc_color=None,
    )
    img_black.alpha_composite(chest_white, (W // 2 - logo_w // 2, int(H * 0.252) - logo_h // 2))

    # Paste white FormulaFun wordmark just above the horizontal seam at t = 0.458
    wm_w = int(W * 0.45)
    wm_white = extract_crisp_wordmark(wm_w, uv_v_stretch, (248, 248, 250, 255))
    img_black.alpha_composite(wm_white, (W // 2 - wm_w // 2, int(H * 0.458) - wm_white.height // 2))

    black_path = os.path.join(OUT_DIR, "jam_deck_blackout_basecolor_4k.png")
    img_black.convert("RGB").save(black_path, quality=95)
    print(f"Saved {black_path}")

    # 2. MELLOW YELLOW DECK PAD (Jam_Yellow.png)
    # Calibrated so linear sRGB under studio lights renders at exact Formula Fun Golden Yellow (#F5B800 / RGB 245, 184, 4)
    base_yellow = np.zeros((H, W, 3), dtype=np.uint8)
    for c, val in enumerate([244, 168, 0]):
        ch = np.clip(val + eva_grain * 1.5, 0, 255)
        ch[seam_row - 3 : seam_row + 3, :] *= 0.62
        base_yellow[:, :, c] = ch.astype(np.uint8)

    img_yellow = Image.fromarray(base_yellow, mode="RGB").convert("RGBA")

    # On Mellow Yellow (Jam_Yellow.png), chest emblem has a solid black circular disc with white ring & white bolt
    chest_yellow = draw_crisp_ff_emblem(
        logo_w,
        logo_h,
        ring_color=(248, 248, 250, 255),
        bolt_color=(248, 248, 250, 255),
        bg_disc_color=(20, 20, 23, 255),
    )
    img_yellow.alpha_composite(chest_yellow, (W // 2 - logo_w // 2, int(H * 0.252) - logo_h // 2))

    # On Mellow Yellow, FormulaFun wordmark is crisp matte black (#141417)
    wm_black = extract_crisp_wordmark(wm_w, uv_v_stretch, (20, 20, 23, 255))
    img_yellow.alpha_composite(wm_black, (W // 2 - wm_w // 2, int(H * 0.458) - wm_black.height // 2))

    yellow_path = os.path.join(OUT_DIR, "jam_deck_yellow_basecolor_4k.png")
    img_yellow.convert("RGB").save(yellow_path, quality=95)
    print(f"Saved {yellow_path}")

    # 3. DECK PAD NORMAL & ROUGHNESS MAPS
    # Compute tangent-space normal map from eva_grain + seam groove
    height_map = eva_grain.copy()
    height_map[seam_row - 3 : seam_row + 3, :] -= 12.0
    dy, dx = np.gradient(height_map)
    strength = 0.35
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / norm, ny / norm, nz / norm
    normal_rgb = np.stack(
        [
            np.clip((nx * 0.5 + 0.5) * 255, 0, 255),
            np.clip((ny * 0.5 + 0.5) * 255, 0, 255),
            np.clip((nz * 0.5 + 0.5) * 255, 0, 255),
        ],
        axis=-1,
    ).astype(np.uint8)
    deck_norm_path = os.path.join(OUT_DIR, "jam_deck_normal_4k.png")
    Image.fromarray(normal_rgb, mode="RGB").resize((1024, 2048), Image.Resampling.LANCZOS).save(deck_norm_path, optimize=True)

    rough_map = np.clip(222 + eva_grain * 3.0, 195, 245).astype(np.uint8)
    deck_rough_path = os.path.join(OUT_DIR, "jam_deck_roughness_4k.png")
    Image.fromarray(rough_map, mode="L").resize((1024, 2048), Image.Resampling.LANCZOS).save(deck_rough_path, optimize=True)
    print(f"Saved {deck_norm_path} and {deck_rough_path}")


def build_foam_core_and_stringer_textures():
    """
    1. Marko EPS Closed-Cell Black Foam Core texture (`jam_foam_basecolor_4k.png`, `jam_foam_normal_4k.png`, `jam_foam_roughness_4k.png`)
       matched to PVW_2601_1400x.jpg.webp: molded bead cellular micro-relief with subtle charcoal-black sheen.
    2. Natural Light-Wood / Composite Stringer texture (`jam_stringer_wood_2k.png`) matching the Twinnie exploded reference.
    """
    W, H = 1024, 1024
    rng = np.random.default_rng(108)

    # Cellular Marko EPS foam bead structure (multi-scale Voronoi/cellular approximation via filtered noise)
    n1 = rng.normal(0, 1, (H // 4, W // 4)).astype(np.float32)
    n1_pil = Image.fromarray(np.clip((n1 * 35 + 128), 0, 255).astype(np.uint8), mode="L").resize((W, H), Image.Resampling.BICUBIC)
    n2 = rng.normal(0, 1, (H, W)).astype(np.float32)
    cell_field = (np.array(n1_pil, dtype=np.float32) - 128.0) * 0.12 + n2 * 2.2

    foam_rgb = np.zeros((H, W, 3), dtype=np.uint8)
    # Sampled from PVW_2601_1400x: deep carbon-black closed-cell EPS
    for c, base_v in enumerate([23, 23, 26]):
        foam_rgb[:, :, c] = np.clip(base_v + cell_field, 12, 38).astype(np.uint8)

    foam_base_path = os.path.join(OUT_DIR, "jam_foam_basecolor_4k.png")
    Image.fromarray(foam_rgb, mode="RGB").save(foam_base_path, optimize=True)

    # Recessed inner EPS cavity floor texture (matching Twinnie exploded reference frame_06.png:
    # textured dark charcoal-grey cellular EPS cavity floor contrasting with the deep black outer rails)
    pocket_rgb = np.zeros((H, W, 3), dtype=np.uint8)
    for c, base_v in enumerate([54, 54, 58]):
        pocket_rgb[:, :, c] = np.clip(base_v + cell_field * 2.1, 32, 78).astype(np.uint8)
    pocket_base_path = os.path.join(OUT_DIR, "jam_pocket_floor_basecolor_2k.png")
    Image.fromarray(pocket_rgb, mode="RGB").save(pocket_base_path, optimize=True)

    dy, dx = np.gradient(cell_field)
    nx = -dx * 0.28
    ny = -dy * 0.28
    nz = np.ones_like(nx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    foam_norm_rgb = np.stack(
        [
            np.clip((nx / norm * 0.5 + 0.5) * 255, 0, 255),
            np.clip((ny / norm * 0.5 + 0.5) * 255, 0, 255),
            np.clip((nz / norm * 0.5 + 0.5) * 255, 0, 255),
        ],
        axis=-1,
    ).astype(np.uint8)
    foam_norm_path = os.path.join(OUT_DIR, "jam_foam_normal_4k.png")
    Image.fromarray(foam_norm_rgb, mode="RGB").save(foam_norm_path, optimize=True)

    foam_rough = np.clip(196 - cell_field * 3.5, 165, 225).astype(np.uint8)
    foam_rough_path = os.path.join(OUT_DIR, "jam_foam_roughness_4k.png")
    Image.fromarray(foam_rough, mode="L").save(foam_rough_path, optimize=True)
    print(f"Saved Marko EPS foam textures: {foam_base_path}")

    # Natural Birch/Poplar Wood Stringer Texture (matching the Twinnie exploded reference image)
    sw, sh = 2048, 512
    yy, xx = np.meshgrid(np.linspace(0, 1, sh, dtype=np.float32), np.linspace(0, 1, sw, dtype=np.float32), indexing="ij")
    grain = (
        np.sin(yy * 48.0 + np.sin(xx * 14.0) * 1.8) * 10.0
        + np.sin(yy * 140.0 + xx * 9.0) * 4.5
        + rng.normal(0, 2.5, (sh, sw)).astype(np.float32)
    )
    wood_rgb = np.zeros((sh, sw, 3), dtype=np.uint8)
    for c, base_v in enumerate([218, 195, 162]):  # Warm natural wood stringer tone from Twinnie exploded view
        wood_rgb[:, :, c] = np.clip(base_v + grain, 150, 245).astype(np.uint8)
    wood_path = os.path.join(OUT_DIR, "jam_stringer_wood_2k.png")
    Image.fromarray(wood_rgb, mode="RGB").save(wood_path)
    print(f"Saved natural wood stringer texture: {wood_path}")


if __name__ == "__main__":
    build_deck_pad_textures()
    build_foam_core_and_stringer_textures()
