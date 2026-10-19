import unreal
import json
from pathlib import Path

report = {}
for path in [
    "/MetaHumanCharacter/Face/SKM_Face",
    "/MetaHumanCharacter/Face/Face_ControlBoard_CtrlRig",
    "/MetaHumanCharacter/Optional/Presets/Ada",
]:
    asset = unreal.load_asset(path)
    item = {"loaded": bool(asset), "class": asset.get_class().get_name() if asset else None}
    if asset:
        item["methods"] = [x for x in dir(asset) if any(t in x.lower() for t in ["dna", "rig", "skeleton", "asset_user", "bounds", "morph", "post_process"])]
        for prop in ["skeleton", "asset_user_data", "post_process_anim_blueprint", "materials"]:
            try:
                item[prop] = str(asset.get_editor_property(prop))
            except Exception:
                pass
    report[path] = item
out = Path(__file__).parent / "asset_probe.json"
out.write_text(json.dumps(report, indent=2))
unreal.log("A2F_PROBE_COMPLETE " + str(out))
