#!/usr/bin/env python3
"""Convert all offline CSV frames and WAV peaks to the browser's local JSON."""
import argparse
import json
import math
import os
import struct
import wave
from pathlib import Path
from validate_package import ROOT, read_csv


def prepare(package, output):
    manifest = json.loads((package / "manifest.json").read_text())
    blendshapes = read_csv(package / "blendshapes.csv")
    controls = read_csv(package / "metahuman_controls.csv")
    if blendshapes["frames"] != controls["frames"] or blendshapes["times"] != controls["times"]:
        raise ValueError("CSV timelines differ")
    fps = float(manifest["animation"]["fps"])
    with wave.open(str(package / "audio.wav"), "rb") as audio:
        rate, channels, samples = audio.getframerate(), audio.getnchannels(), audio.getnframes()
        if audio.getsampwidth() != 2 or audio.getcomptype() != "NONE":
            raise ValueError("Preview waveform requires uncompressed PCM16")
        raw = audio.readframes(samples)
    pcm = struct.unpack("<" + str(len(raw) // 2) + "h", raw)
    mono = [max(abs(x) for x in pcm[i:i + channels]) / 32768 for i in range(0, len(pcm), channels)]
    count = min(256, len(mono))
    peaks = [max(mono[math.floor(i * len(mono) / count):math.floor((i + 1) * len(mono) / count)]) for i in range(count)]
    model = manifest["model"]
    package_url = Path(os.path.relpath(package.resolve(), output.parent.resolve())).as_posix()
    data = {"schemaVersion": 1, "fps": fps, "frameCount": len(blendshapes["frames"]),
            "duration": len(blendshapes["frames"]) / fps,
            "lastFrameTime": blendshapes["times"][-1],
            "times": blendshapes["times"], "frames": [int(x) for x in blendshapes["frames"]],
            "blendshapes": {"names": blendshapes["names"], "values": blendshapes["values"]},
            "controls": {"names": controls["names"], "values": controls["values"]},
            "package": {"name": package.name, "url": package_url, "fbxUrl": package_url + "/face.fbx"},
            "audio": {"url": package_url + "/audio.wav", "duration": samples / rate,
                      "sampleRate": rate, "channels": channels, "peaks": peaks},
            "source": {"model": model["name"], "revision": model["revision"],
                       "emotion": model["emotion"], "provider": model["provider"], "serverClaims": True,
                       "proceduralBlinks": manifest.get("procedural_blinks", {}).get("enabled", False)},
            "caveats": ["NVIDIA Claire 参考网格与控制器预览；不是 MetaHuman 角色渲染。",
                        "包内没有 MetaHuman 网格、材质、DNA 或 Unreal 工程。",
                        "68 个形变权重、173 个控制器与音频来自原始包；未重新执行 NVIDIA 推理。",
                        "完整 CSV 数据均已加载；皮肤和舌头使用官方同名形变，眼球和牙齿为静态参考网格。"]}
    track = package / "emotion_track.json"
    if track.is_file():
        data["emotionTrack"] = json.loads(track.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    print(json.dumps({"output": str(output), "frames": len(data["frames"]), "blendshapeChannels": len(data["blendshapes"]["names"]),
                      "controlChannels": len(data["controls"]["names"]), "bytes": output.stat().st_size}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, nargs="?", default=ROOT / "demo-data")
    parser.add_argument("--output", type=Path, default=ROOT / "viewer" / "data.json")
    arguments = parser.parse_args()
    prepare(arguments.package, arguments.output)
