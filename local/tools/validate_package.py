#!/usr/bin/env python3
"""Independently validate the supplied offline package using only Python stdlib.

This checks serialized data, not NVIDIA inference or an Unreal import. The FBX
reader is intentionally limited to this package's ASCII exporter; it is not a
general FBX SDK and cannot establish Control Rig compatibility in Unreal.
"""
import argparse
import ast
import csv
import hashlib
import json
import math
import re
import struct
import wave
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FBX_TICKS_PER_SECOND = 46186158000


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    if header[:2] != ["frame", "time_seconds"] or len(set(header)) != len(header):
        raise ValueError(f"Invalid or duplicate CSV headers: {path.name}")
    if not rows or any(len(row) != len(header) for row in rows):
        raise ValueError(f"Empty or nonrectangular CSV: {path.name}")
    values = [[float(x) for x in row] for row in rows]
    if not all(math.isfinite(x) for row in values for x in row):
        raise ValueError(f"Nonfinite CSV value: {path.name}")
    return {"names": header[2:], "frames": [row[0] for row in values],
            "times": [row[1] for row in values], "values": [row[2:] for row in values]}


def read_wave(path):
    with wave.open(str(path), "rb") as audio:
        return {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                "samples": audio.getnframes(), "sample_width_bytes": audio.getsampwidth(),
                "compression": audio.getcomptype(),
                "duration_seconds": audio.getnframes() / audio.getframerate()}


def read_npy(raw):
    """Read only primitive NPY arrays; never enable pickle or object loading."""
    if raw[:6] != b"\x93NUMPY":
        raise ValueError("Invalid NPY magic")
    major = raw[6]
    if major not in (1, 2, 3):
        raise ValueError(f"Unsupported NPY version {major}")
    start = 10 if major == 1 else 12
    size = struct.unpack("<H" if major == 1 else "<I", raw[8:start])[0]
    meta = ast.literal_eval(raw[start:start + size].decode("utf-8").strip())
    shape = meta["shape"]
    if meta["fortran_order"]:
        raise ValueError("Fortran order not supported")
    count = math.prod(shape)
    descr = meta["descr"]
    body = raw[start + size:]
    if descr in ("<f8", "<f4", "<i8"):
        code = {"<f8": "d", "<f4": "f", "<i8": "q"}[descr]
        values = list(struct.unpack("<" + str(count) + code, body))
    elif re.fullmatch(r"<U\d+", descr):
        width = int(descr[2:]) * 4
        if len(body) != count * width:
            raise ValueError("Invalid Unicode NPY length")
        values = [body[i:i + width].decode("utf-32-le").rstrip("\0")
                  for i in range(0, len(body), width)]
    else:
        raise ValueError(f"Unsupported or unsafe NPY dtype: {descr}")
    return {"dtype": descr, "shape": list(shape), "values": values}


def csv_stats(table, fps):
    values = table["values"]
    stats = []
    for column, name in enumerate(table["names"]):
        channel = [row[column] for row in values]
        stats.append({"name": name, "min": min(channel), "max": max(channel),
                      "nonzero_frames": sum(x != 0 for x in channel)})
    return {"frames": len(values), "channels": len(table["names"]),
            "first_frame": table["frames"][0], "last_frame": table["frames"][-1],
            "start_seconds": table["times"][0], "end_seconds": table["times"][-1],
            "finite_values": True,
            "contiguous_zero_based_frames": table["frames"] == list(range(len(values))),
            "strictly_increasing_times": all(a < b for a, b in zip(table["times"], table["times"][1:])),
            "max_grid_time_error_seconds": max(abs(t - i / fps) for i, t in enumerate(table["times"])),
            "min": min(s["min"] for s in stats), "max": max(s["max"] for s in stats),
            "zero_channels": [s["name"] for s in stats if s["nonzero_frames"] == 0],
            "channel_ranges": stats}


def validate_fbx(path, controls, fps):
    text = path.read_text(encoding="ascii")
    # Braces in strings/comments must not affect the balance check.
    structural = re.sub(r'"(?:[^"\\]|\\.)*"|;[^\n]*', '', text)
    depth = 0
    balanced = True
    for char in structural:
        depth += (char == "{") - (char == "}")
        balanced = balanced and depth >= 0
    balanced = balanced and depth == 0
    objects = re.findall(r'^\t(Model|AnimationStack|AnimationLayer|AnimationCurveNode|AnimationCurve|Geometry|Deformer|Material|Texture):\s*(\d+),\s*"([^"]*)",\s*"([^"]*)"\s*\{', text, re.M)
    ids = [int(obj[1]) for obj in objects]
    by_type = {kind: sum(o[0] == kind for o in objects) for kind in sorted({o[0] for o in objects})}
    models = {int(i): (name.removeprefix("Model::"), subtype) for kind, i, name, subtype in objects if kind == "Model"}
    connections = [(kind, int(src), int(dst), prop) for kind, src, dst, prop in
                   re.findall(r'^\s*C:\s*"(OO|OP)",(\d+),(\d+)(?:,"([^"]*)")?\s*$', text, re.M)]
    valid_ids = set(ids) | {0}
    curves = re.findall(r'^\tAnimationCurve:\s*(\d+),\s*"AnimCurve::([^"]+)",\s*""\s*\{(.*?)^\t\}', text, re.M | re.S)
    errors = []
    max_value_error = 0.0
    max_time_error = 0.0
    sample_count = 0
    csv_index = {name: i for i, name in enumerate(controls["names"])}
    for curve_id, name, body in curves:
        arrays = {}
        for key, declared, data in re.findall(r'(KeyTime|KeyValueFloat|KeyAttrFlags|KeyAttrRefCount):\s*\*(\d+)\s*\{\s*a:\s*([^}]+)\}', body):
            arrays[key] = [float(x.strip()) for x in data.split(",") if x.strip()]
            if len(arrays[key]) != int(declared):
                errors.append(f"{name}: {key} array length mismatch")
        times, values = arrays.get("KeyTime", []), arrays.get("KeyValueFloat", [])
        if len(times) != len(controls["times"]) or len(values) != len(times):
            errors.append(f"{name}: frame count mismatch")
            continue
        if name not in csv_index:
            errors.append(f"{name}: unknown control")
            continue
        if not all(math.isfinite(x) for x in times + values):
            errors.append(f"{name}: nonfinite value")
        max_time_error = max(max_time_error, max(abs(t / FBX_TICKS_PER_SECOND - i / fps) for i, t in enumerate(times)))
        max_value_error = max(max_value_error, max(abs(v - row[csv_index[name]]) for v, row in zip(values, controls["values"])))
        if arrays.get("KeyAttrFlags") != [4.0] or sum(arrays.get("KeyAttrRefCount", [])) != len(times):
            errors.append(f"{name}: unexpected interpolation flags/refcount")
        # Confirm the curve actually reaches the named model and axis.
        curve_links = [c for c in connections if c[1] == int(curve_id) and c[0] == "OP"]
        model_name, axis = name.split(".translate")
        if len(curve_links) != 1 or curve_links[0][3] != "d|" + axis:
            errors.append(f"{name}: invalid curve-to-axis connection")
        else:
            node_id = curve_links[0][2]
            model_links = [c for c in connections if c[1] == node_id and c[0] == "OP"]
            if len(model_links) != 1 or model_links[0][3] != "Lcl Translation" or models.get(model_links[0][2], (None,))[0] != model_name:
                errors.append(f"{name}: invalid node-to-model connection")
        sample_count += len(values)
    version = re.search(r'FBXVersion:\s*(\d+)', text)
    return {"method": "Independent stdlib structural ASCII parser; not a full FBX SDK or Unreal import",
            "version": int(version.group(1)) if version else None,
            "balanced_braces": balanced, "object_counts": by_type,
            "object_ids_unique": len(set(ids)) == len(ids),
            "connection_count": len(connections),
            "connections_reference_existing_objects": all(src in valid_ids and dst in valid_ids for _, src, dst, _ in connections),
            "all_models_are_null_controls": all(kind == "Null" for _, kind in models.values()),
            "contains_mesh": bool(re.search(r'^\s*Geometry:|^\s*Vertices:|^\s*PolygonVertexIndex:|^\s*Model:[^\n]*"Mesh"', text, re.M)),
            "curve_names_equal_csv": sorted(name for _, name, _ in curves) == sorted(controls["names"]),
            "key_samples_compared_to_csv": sample_count,
            "max_key_value_error_vs_csv": max_value_error,
            "max_key_time_error_seconds": max_time_error,
            "curve_errors": errors, "unreal_import_tested_locally": False}


def validate(package):
    manifest = json.loads((package / "manifest.json").read_text())
    fps = float(manifest["animation"]["fps"])
    checks = []
    for name, expected in manifest["files"].items():
        path = (package / name).resolve()
        if not path.is_relative_to(package.resolve()):
            raise ValueError("Manifest path outside package")
        actual = path.read_bytes()
        digest = hashlib.sha256(actual).hexdigest()
        checks.append({"file": name, "bytes": len(actual), "sha256": digest,
                       "bytes_match": len(actual) == expected["bytes"], "sha256_match": digest == expected["sha256"]})
    checks_by_name = {item["file"]: item for item in checks}
    auxiliary_hashes = {
        "input_sha256_matches_source_audio": manifest["input"]["sha256"] == checks_by_name["source_audio.wav"]["sha256"],
        "fbx_mapping_sha256_matches_mapping": manifest["fbx"]["mapping_sha256"] == checks_by_name["MH_Mapping.json"]["sha256"]}
    audio = {name: read_wave(package / name) for name in ("audio.wav", "source_audio.wav")}
    bs, controls = read_csv(package / "blendshapes.csv"), read_csv(package / "metahuman_controls.csv")
    csv_report = {"blendshapes": csv_stats(bs, fps), "controls": csv_stats(controls, fps)}
    mapping = json.loads((package / "MH_Mapping.json").read_text())
    mapping_error = 0.0
    for b, c in zip(bs["values"], controls["values"]):
        predicted = dict.fromkeys(controls["names"], 0.0)
        for shape, weight in zip(bs["names"], b):
            for name, coefficient in mapping.get(shape, {}).items():
                if name in predicted:
                    predicted[name] += weight * coefficient
        mapping_error = max(mapping_error, max(abs(predicted[name] - value) for name, value in zip(controls["names"], c)))
    with zipfile.ZipFile(package / "curves.npz") as archive:
        arrays = {name.removesuffix(".npy"): read_npy(archive.read(name)) for name in archive.namelist()}
    npz_report = {name: {"dtype": value["dtype"], "shape": value["shape"],
                        "finite_values": all(math.isfinite(x) for x in value["values"]) if value["dtype"][1] != "U" else None}
                  for name, value in arrays.items()}
    for key, table in (("blendshape", bs), ("control", controls)):
        npz_report[key + "_names_match_csv"] = arrays[key + "_names"]["values"] == table["names"]
        flat = [x for row in table["values"] for x in row]
        expected = arrays[key + ("_weights" if key == "blendshape" else "_values")]["values"]
        npz_report[key + "_max_value_error_vs_csv"] = max(abs(a - b) for a, b in zip(flat, expected)) if len(flat) == len(expected) else None
    npz_report["times_max_error_vs_csv"] = max(abs(a - b) for a, b in zip(arrays["times_seconds"]["values"], bs["times"]))
    fbx = validate_fbx(package / "face.fbx", controls, fps)
    failures = []
    def check(condition, message):
        if not condition:
            failures.append(message)
    check(all(x["bytes_match"] and x["sha256_match"] for x in checks), "Manifest checksum/size mismatch")
    check(all(auxiliary_hashes.values()), "Manifest auxiliary checksum mismatch")
    for key, channels in (("blendshapes", 68), ("controls", 173)):
        stats = csv_report[key]
        check(stats["frames"] == manifest["animation"]["frames"] and stats["channels"] == channels, key + " dimensions mismatch")
        check(stats["contiguous_zero_based_frames"] and stats["strictly_increasing_times"] and stats["max_grid_time_error_seconds"] < 1e-9, key + " timestamp/frame mismatch")
    check(bs["times"] == controls["times"], "CSV time arrays differ")
    claimed = manifest["animation"]
    check(fps == 30 and claimed["frames"] == len(bs["frames"]) and claimed["blendshape_channels"] == len(bs["names"]) and claimed["control_channels"] == len(controls["names"]), "Animation metadata mismatch")
    check(claimed["start_frame"] == bs["frames"][0] and claimed["end_frame"] == bs["frames"][-1] and abs(claimed["start_seconds"] - bs["times"][0]) < 1e-9 and abs(claimed["end_seconds"] - bs["times"][-1]) < 1e-9, "Animation endpoints mismatch")
    check(sorted(manifest["zero_blendshape_channels"]) == sorted(csv_report["blendshapes"]["zero_channels"]), "Zero-channel metadata mismatch")
    check(csv_report["blendshapes"]["min"] >= -1e-9 and csv_report["blendshapes"]["max"] <= 1 + 1e-9, "Blendshape weights outside [0,1]")
    check(csv_report["controls"]["min"] >= -1 - 1e-9 and csv_report["controls"]["max"] <= 1 + 1e-9, "Controls outside inspected [-1,1] range; rig limits need separate check")
    check(mapping_error < 1e-7, "Controls differ from mapping-weighted blendshapes")
    check(all(audio["audio.wav"][key] == manifest["audio"][key] for key in ("sample_rate", "channels", "samples", "duration_seconds")), "Audio metadata mismatch")
    check(audio["audio.wav"] == audio["source_audio.wav"], "Audio/source audio metadata differ")
    check(arrays["fps"]["values"] == [fps], "NPZ fps mismatch")
    check(npz_report["times_max_error_vs_csv"] < 1e-9, "NPZ/CSV timestamps differ")
    frame_count = len(bs["frames"])
    for key, shape in (("times_seconds", [frame_count]), ("blendshape_names", [68]), ("blendshape_weights", [frame_count, 68]), ("control_names", [173]), ("control_values", [frame_count, 173]), ("network_output", [frame_count, 169])):
        check(arrays[key]["shape"] == shape, key + " NPZ shape mismatch")
    check(all(item.get("finite_values") is not False for item in npz_report.values() if isinstance(item, dict)), "NPZ contains nonfinite values")
    for key in ("blendshape", "control"):
        check(npz_report[key + "_names_match_csv"] and npz_report[key + "_max_value_error_vs_csv"] is not None and npz_report[key + "_max_value_error_vs_csv"] < 1e-7, key + " NPZ/CSV mismatch")
    check(fbx["balanced_braces"] and fbx["object_ids_unique"] and fbx["connections_reference_existing_objects"], "FBX structural inconsistency")
    check(fbx["curve_names_equal_csv"] and not fbx["curve_errors"] and fbx["max_key_value_error_vs_csv"] < 1e-9 and fbx["max_key_time_error_seconds"] < 1e-9, "FBX curves differ from CSV")
    return {"schema_version": 1, "result": "PASS" if not failures else "FAIL", "failures": failures,
            "independently_verified": {"manifest_files": checks, "manifest_auxiliary_hashes": auxiliary_hashes, "audio": audio, "csv": csv_report,
                                       "csv_time_arrays_equal": bs["times"] == controls["times"],
                                       "mapping_max_value_error": mapping_error, "npz": npz_report, "fbx": fbx,
                                       "animation_minus_audio_end_seconds": bs["times"][-1] - audio["audio.wav"]["duration_seconds"]},
            "server_manifest_claims_not_reproduced_locally": {"model": manifest["model"], "solver": manifest["solver"]["implementation"],
                                                             "fbx_validation": manifest["fbx"]["validation"]},
            "limitations": ["No MetaHuman mesh, materials, DNA, assembled character, skeleton or Unreal project is included.",
                            "ASCII FBX contains control animation only; import must target an existing compatible MetaHuman Control Rig.",
                            "This does not reproduce model inference, prove upstream provenance, or validate Unreal/MetaHuman runtime compatibility.",
                            "CSV/FBX controls are serialized translations; observed [-1,1] values do not prove per-rig control limits.",
                            f"Audio duration is {audio['audio.wav']['duration_seconds']} s; last key is at {bs['times'][-1]} s; {frame_count} frames at {fps} fps occupy a {frame_count/fps} s playback interval."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, nargs="?", default=ROOT / "demo-data")
    parser.add_argument("--output", type=Path, default=ROOT / "validation.json")
    args = parser.parse_args()
    report = validate(args.package)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    verified = report["independently_verified"]
    print(json.dumps({"result": report["result"], "manifest_files": len(verified["manifest_files"]),
                      "audio_seconds": verified["audio"]["audio.wav"]["duration_seconds"],
                      "frames": verified["csv"]["blendshapes"]["frames"],
                      "blendshape_channels": verified["csv"]["blendshapes"]["channels"],
                      "control_channels": verified["csv"]["controls"]["channels"],
                      "fbx_mesh": verified["fbx"]["contains_mesh"],
                      "fbx_curve_samples_compared": verified["fbx"]["key_samples_compared_to_csv"],
                      "failures": report["failures"]}, ensure_ascii=False))
    raise SystemExit(0 if report["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
