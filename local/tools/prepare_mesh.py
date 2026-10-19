#!/usr/bin/env python3
"""Export the official Claire v2 neutral mesh and relative morphs for Three.js.

Reads only numeric NPZ arrays (allow_pickle=False) and a strictly limited subset
of Maya ASCII geometry statements. It never evaluates Maya/MEL or Python scene
code. Downloaded archives and licenses remain in assets/claire.

Run from any directory: .venv/bin/python tools/prepare_mesh.py
The mesh.json paths are relative to its containing viewer directory. Float
buffers are little-endian float32, indices are little-endian uint32, and the
morph buffer contains one complete vertex delta array per morphNames entry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL_REV = "e49df240e416777475cfb5e1b61772206785485a"
MAYA_REV = "f0dc13670952c495450dab1655c94e9056c9d7d9"
MODEL_URL = "https://huggingface.co/nvidia/Audio2Face-3D-v2.3.1-Claire"
MAYA_URL = f"https://github.com/NVIDIA/Maya-ACE/blob/{MAYA_REV}/sample_project/maya_geom/claire_geom_v2_topo1.ma"
SELECTED = {
    "c_headWatertight_hiShape": ("skin", "skin", "bs_skin.npz"),
    "c_tongue_hiShape": ("tongue", "tongue", "bs_tongue.npz"),
    "r_choroid_hiShape": ("eye_right", "eye", None),
    "l_choroid_hiShape": ("eye_left", "eye", None),
    "r_cornea_hiShape": ("cornea_right", "cornea", None),
    "l_cornea_hi1Shape": ("cornea_left", "cornea", None),
    "c_topDenture_hiShape": ("teeth_upper", "teeth", None),
    "c_bottomDenture_hiShape": ("teeth_lower", "teeth", None),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def numeric_attribute(block: str, attribute: str, dtype) -> np.ndarray:
    """Parse indexed vt/ed records and require every index once in order."""
    pattern = rf'setAttr(?: -s \d+)? "\.{attribute}\[(\d+)(?::(\d+))?\]"\s*([^;]+);'
    chunks, cursor = [], 0
    for match in re.finditer(pattern, block):
        start, stop = int(match[1]), int(match[2] or match[1])
        require(start == cursor, f"{attribute}: non-contiguous indices {start} != {cursor}")
        values = np.fromstring(match[3], sep=" ", dtype=dtype)
        require(values.size == (stop - start + 1) * 3, f"{attribute}: incorrect record size")
        chunks.append(values.reshape(-1, 3))
        cursor = stop + 1
    require(bool(chunks), f"Missing attribute {attribute}")
    return np.concatenate(chunks)


def parse_mesh(block: str) -> tuple[np.ndarray, np.ndarray, dict]:
    vertices = numeric_attribute(block, "vt", np.float64)
    edges = numeric_attribute(block, "ed", np.int64)[:, :2]
    require(np.isfinite(vertices).all(), "Non-finite vertex")
    require(edges.min() >= 0 and edges.max() < len(vertices), "Edge index out of range")
    triangles, face_count, counts = [], 0, {}
    face_records = re.finditer(r'^\s*f (\d+) ([\d\- ]+)\s*$', block, re.M)
    for record in face_records:
        n = int(record[1])
        refs = np.fromstring(record[2], sep=" ", dtype=np.int64)
        require(n in (3, 4) and refs.size == n, "Unsupported or invalid polygon record")
        # Maya encodes reverse edge e as -e-1 (not -e).
        ids = np.where(refs >= 0, refs, -refs - 1)
        require(ids.max() < len(edges), "Polygon edge index out of range")
        directed = edges[ids].copy()
        directed[refs < 0] = directed[refs < 0, ::-1]
        require(np.array_equal(directed[:, 1], np.roll(directed[:, 0], -1)), "Polygon boundary is not closed")
        face = directed[:, 0]
        require(len(set(face.tolist())) == n, "Repeated polygon vertex")
        for i in range(1, n - 1):
            triangles.append((face[0], face[i], face[i + 1]))
        face_count += 1
        counts[str(n)] = counts.get(str(n), 0) + 1
    expected_faces = re.search(r'setAttr -s (\d+)(?: -ch \d+)? "\.fc";', block)
    require(expected_faces is not None and face_count == int(expected_faces[1]), "Missing polygon records")
    indices = np.asarray(triangles, dtype="<u4")
    require(indices.size > 0, "Missing triangle topology")
    # Keeping Maya's explicit order preserves original winding.
    a, b, c = (vertices[indices[:, i]] for i in range(3))
    signed_volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)
    return vertices, indices, {"polygonCount": face_count, "polygonDegrees": counts, "signedVolumeCm3": signed_volume}


def write_buffer(directory: Path, name: str, values: np.ndarray, dtype: str) -> str:
    destination = directory / name
    np.asarray(values, dtype=dtype, order="C").tofile(destination)
    require(destination.stat().st_size == values.size * np.dtype(dtype).itemsize, "Buffer size mismatch")
    return f"geometry/{name}"


def bbox(vertices: np.ndarray) -> dict:
    return {"min": vertices.min(axis=0).tolist(), "max": vertices.max(axis=0).tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "assets/claire")
    parser.add_argument("--csv", type=Path, default=ROOT / "demo-data/blendshapes.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "viewer")
    args = parser.parse_args()
    out = args.out / "geometry"
    out.mkdir(parents=True, exist_ok=True)

    with args.csv.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        channel_names = [n for n in reader.fieldnames if n not in {"frame", "time_seconds"}]
        rows = list(reader)
    require(bool(rows), "Animation CSV is empty")
    weights = np.array([[float(row[name]) for name in channel_names] for row in rows])
    require(np.isfinite(weights).all(), "Non-finite animation weights")

    scene = (args.assets / "claire_geom_v2_topo1.ma").read_text(encoding="utf-8")
    parts, matched, all_base = [], [], []
    for block in re.split(r'(?=^createNode )', scene, flags=re.M):
        node = re.match(r'createNode mesh -n "([^"]+)"', block)
        if not node or node[1] not in SELECTED:
            continue
        source_name = node[1]
        name, material, archive = SELECTED[source_name]
        scene_base, triangles, validation = parse_mesh(block)
        base, deltas, morph_names = scene_base, [], []
        if archive:
            with np.load(args.assets / archive, allow_pickle=False) as data:
                base = np.asarray(data["neutral"], dtype=np.float32)
                require(base.shape == scene_base.shape, f"{name}: NPZ/topology vertex count mismatch")
                pose_names = [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in data["poseNames"]]
                require(pose_names[0] == "neutral", "Unexpected pose name ordering")
                morph_names = pose_names[1:]
                require(len(set(morph_names)) == len(morph_names), "Duplicate morph names")
                require(set(morph_names).issubset(channel_names), f"CSV missing {set(morph_names) - set(channel_names)}")
                for pose in morph_names:
                    delta = np.asarray(data[pose], dtype=np.float32)
                    require(delta.shape == base.shape and np.isfinite(delta).all(), f"Invalid delta {pose}")
                    deltas.append(delta)
                deltas = np.stack(deltas)
                separation = np.linalg.norm(scene_base - base, axis=1)
                # The Maya geometry scene contains a slightly posed surface.
                # Officially matching topology plus point-wise positional
                # correspondence bounds protect against ordering/topology errors.
                require(float(separation.max()) < 0.3, f"{name}: geometry correspondence exceeds 3 mm")
                validation["mayaToNpzMedianDistanceCm"] = float(np.median(separation))
                validation["mayaToNpzMaxDistanceCm"] = float(separation.max())
                animation_weights = weights[:, [channel_names.index(x) for x in morph_names]]
                # Validate finite deformation on the entire supplied performance.
                deformation = np.tensordot(animation_weights, deltas, axes=(1, 0))
                require(np.isfinite(deformation).all(), "Invalid reconstructed animation")
                validation["maxAnimationDisplacementCm"] = float(np.linalg.norm(deformation, axis=-1).max())
            matched.extend(morph_names)
        require(np.isfinite(base).all(), "Non-finite neutral geometry")
        part = {"name": name, "material": material, "sourceMesh": source_name,
                "vertexCount": len(base), "indexCount": int(triangles.size),
                "base": write_buffer(out, name + ".base.bin", base, "<f4"),
                "indices": write_buffer(out, name + ".indices.bin", triangles, "<u4"),
                "morphs": write_buffer(out, name + ".morphs.bin", deltas, "<f4") if morph_names else None,
                "morphNames": morph_names, "morphTargetsRelative": True,
                "bbox": bbox(base), "static": not bool(morph_names), "validation": validation}
        parts.append(part)
        all_base.append(base)
    require(len(parts) == len(SELECTED), "Missing requested geometry parts")
    require(set(matched) == set(channel_names), "Not all input animation channels map to official morphs")
    result = {
        "schemaVersion": 1,
        "label": "NVIDIA Claire v2.3.1 · official reference mesh; not MetaHuman",
        "units": "centimeters", "upAxis": "+Y", "frontAxis": "+Z",
        "bbox": bbox(np.concatenate(all_base)),
        "morphTargetsRelative": True, "bufferEndianness": "little",
        "positionType": "float32", "indexType": "uint32", "morphLayout": "shape-major",
        "source": {"model": MODEL_URL, "modelRevision": MODEL_REV, "geometry": MAYA_URL, "geometryRevision": MAYA_REV},
        "animation": {"file": "../demo-data/blendshapes.csv", "frames": len(rows), "matchedChannels": len(matched), "csvSha256": sha256(args.csv)},
        "limitations": [
            "This is the NVIDIA Claire reference mesh, not an Epic MetaHuman character.",
            "Appearance uses preview materials; original skin/eye textures and hair are absent.",
            "Eyes and upper/lower teeth remain static in their original bind coordinates. No jaw or eye transforms were inferred.",
            "Tongue morphs use their neutral jaw coordinates; separate jaw transform animation was not included in the supplied CSV.",
            "Maya scene scripts, deformers, and transform animation are not evaluated. Only matching vertex/edge/face records are read.",
        ],
        "parts": parts,
    }
    (args.out / "mesh.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    provenance = {"model": {"url": MODEL_URL, "revision": MODEL_REV},
                  "topology": {"url": MAYA_URL, "revision": MAYA_REV},
                  "license": {"model": "NVIDIA Open Model License", "modelFile": "NVIDIA_OPEN_MODEL_LICENSE.pdf", "mayaAce": "MAYA_ACE_LICENSE.txt"},
                  "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in args.assets.iterdir() if p.is_file() and p.name != "SOURCES.json"},
                  "method": "Read NPZ with allow_pickle=False. Parse Maya ASCII numeric geometry only. No downloaded code is executed. Model ONNX not downloaded."}
    (args.assets / "SOURCES.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"mesh": str(args.out / "mesh.json"), "parts": [{"name": p["name"], "vertices": p["vertexCount"], "triangles": p["indexCount"] // 3, "morphs": len(p["morphNames"])} for p in parts], "matchedChannels": len(matched)}, indent=2))


if __name__ == "__main__":
    main()
