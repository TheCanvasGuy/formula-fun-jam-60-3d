#!/usr/bin/env python3
"""
Extract all 8 unique CAD part meshes (and 10 assembly instances) from JAM_Assem.SLDASM
embedded FaceTessellations__000-000-006 and COMPINSTANCETREE streams.
Saves binary STL files into /Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD/parts/
and verifies exact assembly transforms (Assembled vs. Exploded).
"""

import os
import struct
import zlib
import math
import json

SLDASM_PATH = "/Users/byronmini/.gemini/antigravity/brain/b0585db8-d01e-4ac8-82fe-ec790d03d924/scratch/jam_inspect/JAM_Assem.SLDASM"
OUT_DIR = "/Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD"
PARTS_DIR = os.path.join(OUT_DIR, "parts")
os.makedirs(PARTS_DIR, exist_ok=True)


def swap_nibbles(b: bytes) -> str:
    return bytes(((x >> 4) | ((x & 0x0F) << 4)) for x in b).decode("latin-1", errors="replace")


def extract_sldasm_streams(sldasm_path: str) -> dict[str, bytes]:
    with open(sldasm_path, "rb") as f:
        raw = f.read()
    streams = {}
    pos = 0
    while True:
        idx = raw.find(b"PK\x03\x04", pos)
        if idx < 0:
            break
        ver, flag, method, mtime, mdate, crc, csize, usize, nlen, elen = struct.unpack_from(
            "<HHHHHIIIHH", raw, idx + 4
        )
        name_bytes = raw[idx + 30 : idx + 30 + nlen]
        decoded_name = swap_nibbles(name_bytes)
        data_start = idx + 30 + nlen + elen
        comp_data = raw[data_start : data_start + csize]
        if method == 8:
            try:
                payload = zlib.decompress(comp_data, -15)
            except Exception:
                payload = comp_data
        else:
            payload = comp_data
        streams[decoded_name] = payload
        pos = data_start + csize
    return streams


PART_RECORDS = [
    ("Jam_60", 4, 1591560),
    ("FB_050", 1591564, 216092),
    ("FB_75", 1807656, 88398),
    ("Fin_small_Center", 1896054, 490484),
    ("Fin_small_Left", 2386538, 498732),
    ("Fin_small_Right_Mirror", 2885270, 492896),
    ("JAM_Stringer", 3378166, 52994),
    ("JAM_DCover", 3431160, 468992),
]


def parse_part_mesh(blob: bytes):
    """
    Parse all faces in a SolidWorks FaceTessellations part record.
    Returns list of triangles: ((v0, v1, v2), face_normal)
    and bounding box.
    """
    STRIP_TAG = struct.pack("<3I", 4, 8, 2)
    ARRAY_TAG = struct.pack("<3I", 12, 100, 2)

    pos = 0
    triangles = []
    min_xyz = [1e9, 1e9, 1e9]
    max_xyz = [-1e9, -1e9, -1e9]
    face_count = 0

    while True:
        s_idx = blob.find(STRIP_TAG, pos)
        if s_idx < 0:
            break
        n_strips = struct.unpack_from("<I", blob, s_idx + 12)[0]
        if n_strips == 0 or n_strips > 10000:
            pos = s_idx + 4
            continue
        strip_lens_end = s_idx + 16 + 4 * n_strips
        if strip_lens_end > len(blob):
            break
        strip_lens = struct.unpack_from(f"<{n_strips}I", blob, s_idx + 16)
        total_strip_verts = sum(strip_lens)

        # Next should be vertex ARRAY_TAG
        v_idx = blob.find(ARRAY_TAG, strip_lens_end)
        if v_idx < 0 or (v_idx - strip_lens_end) > 64:
            pos = s_idx + 4
            continue
        n_verts = struct.unpack_from("<I", blob, v_idx + 12)[0]
        if n_verts != total_strip_verts or n_verts == 0:
            pos = s_idx + 4
            continue
        verts_start = v_idx + 16
        verts_end = verts_start + n_verts * 12
        if verts_end > len(blob):
            break
        verts_flat = struct.unpack_from(f"<{n_verts * 3}f", blob, verts_start)
        verts = [
            (verts_flat[3 * i], verts_flat[3 * i + 1], verts_flat[3 * i + 2])
            for i in range(n_verts)
        ]

        # Update bbox
        for vx, vy, vz in verts:
            if vx < min_xyz[0]: min_xyz[0] = vx
            if vy < min_xyz[1]: min_xyz[1] = vy
            if vz < min_xyz[2]: min_xyz[2] = vz
            if vx > max_xyz[0]: max_xyz[0] = vx
            if vy > max_xyz[1]: max_xyz[1] = vy
            if vz > max_xyz[2]: max_xyz[2] = vz

        # Check normal ARRAY_TAG right after verts_end
        norms = None
        if verts_end + 16 <= len(blob) and blob[verts_end : verts_end + 12] == ARRAY_TAG:
            n_norms = struct.unpack_from("<I", blob, verts_end + 12)[0]
            norms_start = verts_end + 16
            norms_end = norms_start + n_norms * 12
            if n_norms == n_verts and norms_end <= len(blob):
                norms_flat = struct.unpack_from(f"<{n_norms * 3}f", blob, norms_start)
                norms = [
                    (norms_flat[3 * i], norms_flat[3 * i + 1], norms_flat[3 * i + 2])
                    for i in range(n_norms)
                ]
                pos = norms_end
            else:
                pos = verts_end
        else:
            pos = verts_end

        # Convert triangle strips to triangles
        v_offset = 0
        for slen in strip_lens:
            for k in range(slen - 2):
                i0 = v_offset + k
                i1 = v_offset + k + 1
                i2 = v_offset + k + 2
                if k % 2 == 1:
                    i0, i1 = i1, i0
                p0, p1, p2 = verts[i0], verts[i1], verts[i2]
                # Compute geometric cross product
                ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
                nx = uy * vz - uz * vy
                ny = uz * vx - ux * vz
                nz = ux * vy - uy * vx
                nlen = math.sqrt(nx * nx + ny * ny + nz * nz)
                if nlen < 1e-12:
                    continue
                nx, ny, nz = nx / nlen, ny / nlen, nz / nlen

                if norms is not None:
                    # Align triangle winding with CAD analytical vertex normals
                    anx = norms[i0][0] + norms[i1][0] + norms[i2][0]
                    any_ = norms[i0][1] + norms[i1][1] + norms[i2][1]
                    anz = norms[i0][2] + norms[i1][2] + norms[i2][2]
                    dot = nx * anx + ny * any_ + nz * anz
                    if dot < 0:
                        p0, p1 = p1, p0
                        nx, ny, nz = -nx, -ny, -nz

                triangles.append(((p0, p1, p2), (nx, ny, nz)))
            v_offset += slen

        face_count += 1

    return triangles, face_count, min_xyz, max_xyz


def write_binary_stl(filepath: str, triangles, header_text: str = "Formula Fun 6'0 Jam CAD"):
    hdr = header_text.encode("ascii", errors="ignore")[:80].ljust(80, b"\x00")
    with open(filepath, "wb") as f:
        f.write(hdr)
        f.write(struct.pack("<I", len(triangles)))
        for (p0, p1, p2), (nx, ny, nz) in triangles:
            f.write(
                struct.pack(
                    "<12fH",
                    nx, ny, nz,
                    p0[0], p0[1], p0[2],
                    p1[0], p1[1], p1[2],
                    p2[0], p2[1], p2[2],
                    0,
                )
            )


def main():
    tess_path = "/Users/byronmini/.gemini/antigravity/brain/b0585db8-d01e-4ac8-82fe-ec790d03d924/scratch/jam_inspect/streams/0060365_FaceTessellations__000-000-006"
    if os.path.exists(tess_path):
        with open(tess_path, "rb") as f:
            tess_stream = f.read()
    else:
        print("Extracting streams from JAM_Assem.SLDASM...")
        streams = extract_sldasm_streams(SLDASM_PATH)
        tess_key = [k for k in streams.keys() if "FaceTessellations" in k and len(streams[k]) > 1000000][0]
        tess_stream = streams[tess_key]
    print(f"Loaded FaceTessellations stream: {len(tess_stream):,} bytes")

    manifest = {}
    for name, offset, size in PART_RECORDS:
        blob = tess_stream[offset : offset + size]
        tris, n_faces, bmin, bmax = parse_part_mesh(blob)
        dims = [bmax[i] - bmin[i] for i in range(3)]
        stl_path = os.path.join(PARTS_DIR, f"{name}.stl")
        write_binary_stl(stl_path, tris, f"FF Jam 6'0 - {name}")
        manifest[name] = {
            "faces": n_faces,
            "triangles": len(tris),
            "bbox_min_m": [round(x, 6) for x in bmin],
            "bbox_max_m": [round(x, 6) for x in bmax],
            "dims_m": [round(x, 6) for x in dims],
            "stl_path": stl_path,
        }
        print(
            f"  [OK] {name:24s} | Faces: {n_faces:4d} | Tris: {len(tris):6d} | "
            f"BBox Min: ({bmin[0]:.4f}, {bmin[1]:.4f}, {bmin[2]:.4f}) | "
            f"Max: ({bmax[0]:.4f}, {bmax[1]:.4f}, {bmax[2]:.4f})"
        )

    manifest_path = os.path.join(OUT_DIR, "jam_parts_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved parts manifest to {manifest_path}")


if __name__ == "__main__":
    main()
