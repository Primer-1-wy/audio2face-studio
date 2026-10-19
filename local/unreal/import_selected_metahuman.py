"""UE 5.7 import preparation. Run in Editor after selecting an assembled MetaHuman.

Uses Epic's installed 5.7 APIs and MetaHuman FBX mapping preset. This script has
been syntax-checked, but was not executed in UE: the local commandlet did not
initialize. A successful script run verifies controller curves, not final skin
deformation; inspect the face while playing the generated Level Sequence.
"""
import csv
import json
from pathlib import Path
import traceback

import unreal

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "demo-data" / "emotions-56s"
REPORT = HERE / "last_import_report.json"
DEST = "/Game/A2FDemo"


def choose_face(actor):
    components = list(actor.get_components_by_class(unreal.SkeletalMeshComponent))
    exact = [c for c in components if c.get_name().lower() == "face"]
    matching = exact or [c for c in components if "face" in c.get_name().lower()]
    if len(matching) != 1:
        raise RuntimeError("Select one assembled MetaHuman actor with one Face skeletal mesh component.")
    component = matching[0]
    mesh = component.get_editor_property("skeletal_mesh")
    if not mesh:
        raise RuntimeError("The selected Face component has no skeletal mesh.")
    if mesh.get_path_name().startswith("/MetaHumanCharacter/Face/SKM_Face"):
        raise RuntimeError("SKM_Face is an unassembled template; select an assembled MetaHuman with facial DNA.")
    return component, mesh


def choose_rig():
    paths = ["/Game/MetaHumans/Common/Face/Face_ControlBoard_CtrlRig"]
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.search_all_assets(synchronous_search=True)
    for item in registry.get_assets_by_path("/Game", recursive=True):
        if str(item.asset_name) == "Face_ControlBoard_CtrlRig":
            paths.append(str(item.package_name))
    paths.append("/MetaHumanCharacter/Face/Face_ControlBoard_CtrlRig")
    for path in dict.fromkeys(paths):
        rig_asset = unreal.load_asset(path)
        if rig_asset and hasattr(rig_asset, "get_control_rig_class"):
            return rig_asset
    raise RuntimeError("Face_ControlBoard_CtrlRig was not found. Enable MetaHuman Creator / Control Rig and import the character's Common assets.")


def verify_controls(sequence, rig, rows):
    """Compare all CSV values using the Control Rig's own value getters."""
    hierarchy = rig.get_hierarchy()
    available = {str(k.name) for k in hierarchy.get_controls()}
    columns = list(rows[0])[2:]
    by_control = {}
    for column in columns:
        name, axis = column.rsplit(".", 1)
        by_control.setdefault(name, {})[axis] = column
    missing = sorted(set(by_control) - available)
    errors = []
    compared = 0
    largest = 0.0
    library = unreal.ControlRigSequencerLibrary
    for name, axes in by_control.items():
        if name not in available:
            continue
        try:
            for row in rows:
                frame = unreal.FrameNumber(int(row["frame"]))
                if "translateX" in axes:
                    value = library.get_local_control_rig_vector2d(sequence, rig, name, frame)
                    actual = {"translateX": value.x, "translateY": value.y}
                else:
                    actual = {"translateY": library.get_local_control_rig_float(sequence, rig, name, frame)}
                for axis, column in axes.items():
                    difference = abs(float(actual[axis]) - float(row[column]))
                    largest = max(largest, difference)
                    compared += 1
                    if difference > 0.001 and len(errors) < 30:
                        errors.append({"channel": column, "frame": int(row["frame"]), "expected": float(row[column]), "actual": float(actual[axis])})
        except Exception as exc:
            errors.append({"control": name, "error": str(exc)})
    return {"compared_values": compared, "expected_values": len(rows) * len(columns), "max_abs_error": largest, "missing_controls": missing, "first_errors": errors, "passed": not missing and not errors and compared == len(rows) * len(columns)}


def main():
    report = {"status": "started", "engine": unreal.SystemLibrary.get_engine_version(), "visual_deformation_verified": False}
    try:
        for name in ("face.fbx", "audio.wav", "metahuman_controls.csv", "manifest.json"):
            if not (DATA / name).is_file():
                raise RuntimeError("Missing input: " + str(DATA / name))
        manifest = json.loads((DATA / "manifest.json").read_text())
        fps = int(manifest["animation"]["fps"])
        frames = int(manifest["animation"]["frames"])
        with (DATA / "metahuman_controls.csv").open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        actors = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_selected_level_actors())
        if len(actors) != 1:
            raise RuntimeError("Select exactly one assembled MetaHuman actor in the level, then run this script again.")
        actor = actors[0]
        face, mesh = choose_face(actor)
        rig_asset = choose_rig()
        report.update({"actor": actor.get_path_name(), "mesh": mesh.get_path_name(), "rig_asset": rig_asset.get_path_name(), "fps": fps, "frames": frames})
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        package, name = tools.create_unique_asset_name(DEST + "/A2F_Playback", "")
        sequence = tools.create_asset(name, str(Path(package).parent), unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        if not sequence:
            raise RuntimeError("Could not create Level Sequence.")
        sequence.set_display_rate(unreal.FrameRate(fps, 1))
        sequence.set_playback_start(0)
        sequence.set_playback_end(frames)
        sequence.set_view_range(0.0, frames / fps)
        sequence.set_work_range(0.0, frames / fps)
        actor_binding = sequence.add_possessable(actor)
        face_binding = sequence.add_possessable(face)
        face_binding.set_parent(actor_binding)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        library = unreal.ControlRigSequencerLibrary
        track = library.find_or_create_control_rig_track(world, sequence, rig_asset.get_control_rig_class(), face_binding)
        if not track:
            raise RuntimeError("Could not create face Control Rig track.")
        sections = list(track.get_sections())
        section = sections[0] if sections else track.add_section()
        section.set_range(0, frames)
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
        settings = unreal.MovieSceneUserImportFBXControlRigSettings()
        settings.load_control_mappings_from_preset(True)
        settings.set_editor_property("import_onto_selected_controls", False)
        settings.set_editor_property("insert_animation", False)
        settings.set_editor_property("time_to_insert_or_replace_animation", unreal.FrameNumber(0))
        settings.set_editor_property("specify_time_range", True)
        settings.set_editor_property("start_time_range", unreal.FrameNumber(0))
        settings.set_editor_property("end_time_range", unreal.FrameNumber(frames - 1))
        settings.set_editor_property("import_uniform_scale", 1.0)
        imported = library.import_fbx_to_control_rig_track(world, sequence, track, section, [], settings, str(DATA / "face.fbx"))
        if not imported:
            raise RuntimeError("UE rejected the Control Rig FBX import. See Output Log.")
        section.set_range(0, frames)
        audio_task = unreal.AssetImportTask()
        audio_task.set_editor_property("filename", str(DATA / "audio.wav"))
        audio_task.set_editor_property("destination_path", DEST + "/Audio")
        audio_task.set_editor_property("destination_name", name + "_Audio")
        audio_task.set_editor_property("automated", True)
        audio_task.set_editor_property("save", True)
        audio_task.set_editor_property("replace_existing", False)
        tools.import_asset_tasks([audio_task])
        imported_audio = list(audio_task.get_editor_property("imported_object_paths"))
        if not imported_audio:
            raise RuntimeError("Audio import did not create a SoundWave.")
        sound = unreal.load_asset(imported_audio[0])
        audio_track = sequence.add_track(unreal.MovieSceneAudioTrack)
        audio_section = audio_track.add_section()
        audio_section.set_sound(sound)
        audio_section.set_looping(False)
        audio_section.set_start_offset(unreal.FrameNumber(0))
        audio_section.set_range(0, frames)
        unreal.EditorAssetLibrary.save_loaded_asset(sequence)
        report["sequence"] = sequence.get_path_name()
        report["audio"] = sound.get_path_name()
        proxies = list(library.get_control_rigs(sequence))
        rig = next(p.control_rig for p in proxies if p.track == track)
        report["curve_verification"] = verify_controls(sequence, rig, rows)
        report["status"] = "imported_curves_verified" if report["curve_verification"]["passed"] else "imported_needs_curve_review"
        unreal.LevelSequenceEditorBlueprintLibrary.set_current_time(0)
        unreal.log("A2F sequence created: " + report["sequence"])
        unreal.log("Save the level containing the selected actor, then play the sequence and inspect facial deformation.")
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
        unreal.log_error(report["error"])
        raise
    finally:
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        unreal.log("A2F report: " + str(REPORT))


if __name__ == "__main__":
    main()
