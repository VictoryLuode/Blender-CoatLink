# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.

"""Send / pull orchestration.

Send : export the chosen meshes to <root>/BlenderBridge/bridge.<ext> and drop a
       root-level import.txt next to it, then remember where they came from.
Pull : watch <root>/BlenderBridge/export.txt for the returned model and merge it
       into the object the send came from.

Everything 3D-Coat writes into a BlenderBridge folder is ours; anything else is
left alone, so the official 3D-Coat AppLink can stay enabled.
"""

import json
import os
import time
import traceback
from datetime import datetime

import bpy
from mathutils import Matrix, Vector

from . import applink, transfer, receipts

ROOT = __package__.split(".")[0]

#: a returned model is rescaled when its size differs from the sent one by more
#: than this fraction (3D-Coat scene units are not always metres)
SCALE_TOLERANCE = 0.02

#: the one format we send with: OBJ carries geometry, UVs and materials without
#: unit ambiguity, and 3D-Coat hands its own FBX back regardless
SEND_FORMAT = "obj"

STATE = {
    "target": None,     # {"object": name, "file": path} of the last send
    "seen": {},         # signal file -> mtime already handled
    "last_send": 0.0,
    "last_pull": 0.0,
    "imported_versions": {},  # canonical path -> (mtime_ns, size) successfully imported
    "message": "Ready",
    "log": [],
}


#: Display name only; ownership is tracked separately by instance.
REMESH_MODIFIER = "CoatLink Remesh"
_remesh_owned = []  # exact (object, modifier) instances, never user-owned names


def auto_voxel_size(obj):
    """A voxel size for an object that was not given one.

    About 64 voxels across its largest dimension: fine enough to keep the shape,
    coarse enough that a metre-scale model does not become millions of faces.
    """
    try:
        biggest = max(obj.dimensions)
    except Exception:
        biggest = 0.0
    return biggest / 64.0 if biggest else 0.01


def add_remesh(objects, voxel_size=0.0, adaptivity=0.0):
    """Put a voxel Remesh modifier on every mesh in `objects`; returns the count.

    Non-destructive on purpose: it changes what the export writes, not the mesh in
    the scene, and `remove_remesh` takes it off again after the export.  A failure on
    one object is logged and skipped rather than stopping the send.
    """
    added = 0
    for obj in objects:
        if getattr(obj, "type", "") != "MESH":
            continue
        try:
            modifier = obj.modifiers.new(REMESH_MODIFIER, "REMESH")
            _remesh_owned.append((obj, modifier))
            modifier.mode = "VOXEL"
            modifier.voxel_size = voxel_size if voxel_size > 0 else auto_voxel_size(obj)
            try:
                modifier.adaptivity = min(1.0, max(0.0, adaptivity))
            except Exception:
                pass                  # older builds without the option still remesh
            added += 1
        except Exception as error:                 # never let this stop a send
            remove_remesh([obj])
            _log("remesh: skipped %s (%s)" % (obj.name, error))
    return added


def remove_remesh(objects):
    """Take our modifier off again, and only ours."""
    for obj, modifier in list(_remesh_owned):
        try:
            if obj not in objects:
                continue
            obj.modifiers.remove(modifier)
        except ReferenceError:
            pass  # object/modifier was already removed by the host
        else:
            _remesh_owned.remove((obj, modifier))
            continue
        _remesh_owned.remove((obj, modifier))


def prefs(context=None):
    ctx = context or bpy.context
    addons = getattr(ctx.preferences, "addons", None)
    if addons is None:
        return None
    entry = addons.get(ROOT)
    return entry.preferences if entry else None


def status(context=None):
    target = STATE.get("target") or {}
    path = target.get("file")
    if path and STATE.get("last_send", 0) > STATE.get("last_pull", 0) and STATE.get("message", "").startswith("Sent "):
        receipt = receipts.received(path, "3dcoat")
        if receipt:
            return "3D-Coat received: %s" % ", ".join(receipt["objects"])
    return STATE["message"]


#: the record of what has already been imported, kept in the exchange folder
HISTORY_NAME = "pull-history.json"
_HISTORY_LOADED = [False]


def _history_path(p):
    """Where the between-sessions pull record lives.

    In the exchange folder we own rather than in Blender's config: it describes
    these files, so clearing the folder should clear it too.
    """
    root = applink.exchange_roots(p.exchange_folder)[0]
    return os.path.join(applink.ensure_app_folder(root), HISTORY_NAME)


def load_history(p, force=False):
    """Recall what earlier sessions already handled.

    Without this, restarting Blender forgets everything and the return file still
    sitting in the exchange folder is imported a second time - the duplicate
    import the user reported.  Only files that are already on disk are recalled,
    and a model whose version changed is imported normally again.
    """
    if _HISTORY_LOADED[0] and not force:
        return STATE["seen"], STATE["imported_versions"]
    try:
        with open(_history_path(p), encoding="utf-8") as stream:
            data = json.load(stream)
        for signal, mtime in (data.get("seen") or {}).items():
            STATE["seen"].setdefault(signal, mtime)
        for key, version in (data.get("imported_versions") or {}).items():
            STATE["imported_versions"].setdefault(key, tuple(version))
    except (OSError, ValueError, TypeError):
        pass                    # no record yet, or a damaged one: import normally
    _HISTORY_LOADED[0] = True
    return STATE["seen"], STATE["imported_versions"]


def save_history(p):
    """Write the record atomically.  Unwritable folders must not break a pull."""
    try:
        path = _history_path(p)
        temporary = path + ".tmp"
        payload = {"seen": STATE["seen"],
                   "imported_versions": {key: list(value)
                                         for key, value in STATE["imported_versions"].items()}}
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        os.replace(temporary, path)
        return True
    except (OSError, TypeError, ValueError):
        return False


#: what the after-import helper writes on every run, in the shared log
AFTER_IMPORT_MARK = "after-import ran"


def after_import_seen(roots=None):
    """Did 3D-Coat run the after-import step since our last send?

    True means dated execution evidence after the last send; False means unconfirmed,
    not proof of non-execution. None means no send or an unreadable log.
    This is diagnostic evidence, not a per-job success receipt.

    The helper's own marker is checked first, because it is the one record that
    survives a machine where the shared log cannot be reached from inside 3D-Coat -
    and because "the step never ran" and "it ran but could not write anything" used
    to look exactly the same from out here.
    """
    sent = STATE.get("last_send") or 0.0
    if not sent:
        return None
    for root in roots or []:
        for marker in applink.after_import_markers(root):
            try:
                if os.path.isfile(marker) and os.path.getmtime(marker) >= sent - 1.0:
                    return True
            except OSError:
                continue
    try:
        with open(applink.shared_log_path(), "rb") as handle:
            handle.seek(0, os.SEEK_END)
            start = max(0, handle.tell() - 65536)
            handle.seek(start)
            if start:
                handle.readline()  # discard a partial first line
            tail = handle.read(65536).decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(tail):
        fields = line.split("|", 2)
        if (len(fields) != 3 or fields[1].strip() != "3dcoat"
                or not fields[2].strip().startswith(AFTER_IMPORT_MARK + ":")):
            continue
        stamp = fields[0].strip()
        try:
            when = datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            continue
        if sent <= when <= time.time():
            return True
    return False


def detail_lines(context=None):
    p = prefs(context)
    if p is None:
        return ["Add-on preferences unavailable"]
    roots = applink.exchange_roots(p.exchange_folder)
    lines = ["Job file: %s" % applink.import_txt(roots[0])]
    lines.append("Model folder: %s" % applink.app_folder(roots[0]))
    for extra in roots[1:]:
        lines.append("Also watching: %s" % applink.app_folder(extra))
    target = STATE["target"]
    lines.append("Target object: %s" % (target["object"] if target else "none"))
    seen = after_import_seen(roots)
    if seen is True:
        lines.append("After-import step: 3D-Coat ran it")
    elif STATE.get("last_send"):
        lines.append("After-import step: not confirmed (no readable dated record)")
    lines.append("Last send %s / last pull %s" % (_stamp(STATE["last_send"]), _stamp(STATE["last_pull"])))
    linked = [obj for obj in bpy.data.objects if obj.get("coat_bridge_file")]
    lines.append("Linked objects: %s" % (", ".join(obj.name for obj in linked[:6]) or "none"))
    lines += STATE["log"][-3:]
    return lines


#: how many of 3D-Coat's scene units one metre is, keyed by what
#: Scene.GetSceneUnits() reports
UNITS_PER_METRE = {
    "METERS": 1.0, "METER": 1.0, "M": 1.0,
    "CENTIMETERS": 100.0, "CENTIMETER": 100.0, "CM": 100.0,
    "MILLIMETERS": 1000.0, "MILLIMETER": 1000.0, "MM": 1000.0,
    "INCHES": 39.3700787, "INCH": 39.3700787,
    "FEET": 3.2808399, "FOOT": 3.2808399,
}

#: factors a returned model may be off by and still be corrected - a unit
#: conversion, never a sculpt (stretching someone's sculpt would be worse than
#: leaving the size alone)
CLEAN_FACTORS = (1e-3, 1e-2, 1.0 / 39.3700787, 1.0 / 3.2808399, 25.4, 100.0, 1000.0, 39.3700787, 3.2808399)


def units_factor():
    """(metres -> 3D-Coat scene units, note) using what 3D-Coat reported."""
    state = applink.coat_state()
    units = str(state.get("scene_units") or "").strip().upper()
    factor = UNITS_PER_METRE.get(units)
    if factor is None:
        return None, "3D-Coat has not reported its units yet (%s)" % (units or "nothing")
    try:
        scene_scale = float(state.get("scene_scale"))
    except (TypeError, ValueError):
        scene_scale = 1.0
    if scene_scale <= 0:
        scene_scale = 1.0
    return factor * scene_scale, "3D-Coat units=%s" % units


def transfer_scale(context):
    """(factor, where it came from): Blender units -> 3D-Coat scene units.

    Why a model used to arrive small: Blender writes metres, 3D-Coat's scene is
    in centimetres, so 3D-Coat read the file 100x smaller than intended.  That is
    a **unit conversion** - not the scene scale, which is 1.0 on the machines
    seen so far, which is why reading scene_scale alone fixed nothing.  A value
    in `3D-Coat scale` overrides the calculation.
    """
    p = prefs(context)
    if p is not None and p.coat_scale > 0:
        return float(p.coat_scale), "set here"
    factor, note = units_factor()
    if factor is None:
        return 1.0, note
    metres = 1.0
    settings = getattr(getattr(context, "scene", None), "unit_settings", None)
    try:
        metres = float(getattr(settings, "scale_length", 1.0) or 1.0)
    except (TypeError, ValueError):
        metres = 1.0
    return factor * metres, note


#: formats that declare their own axes AND units (FBX does: unit scale plus
#: up-axis).  For those the file decides and the bridge keeps its hands off -
#: converting a second time is how a model ends up rotated or 100x off twice.
SELF_DESCRIBING_AXES = ("fbx",)


def axis_swap(context, p=None, fmt=None):
    """True/False/None for the axis convention; None = leave it to the file.

    OBJ has no axis metadata, so there the bridge must say which convention the
    file is in - one rule, used for the export and the import alike, which is
    what keeps the two directions from drifting apart.  FBX declares its own
    axes, so overriding them there is how a model ends up rotated twice.
    """
    if fmt in SELF_DESCRIBING_AXES:
        return None
    p = p or prefs(context)
    if p is None:
        return None
    if p.axis_mode == "swap":
        return True
    if p.axis_mode == "normal":
        return False
    reported = applink.coat_state().get("swap_yz")
    return None if reported is None else bool(reported)


def send(context):
    """Export the selection (or every visible mesh) and queue it for 3D-Coat."""
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    roots = applink.exchange_roots(p.exchange_folder)
    primary = roots[0]
    if not os.path.isdir(primary):
        raise RuntimeError("exchange folder not found: %s (press Detect in the panel)" % primary)

    objects, scope = _send_objects(context, getattr(p, "scope", "selected") == "scene")
    active = context.view_layer.objects.active
    if active not in objects:
        active = objects[0]

    fmt = SEND_FORMAT
    if not transfer.ensure_module(fmt):
        raise RuntimeError(transfer.missing_reason(fmt) or "%s unavailable" % fmt)
    for obj in objects:
        if not obj.data.uv_layers:  # 3D-Coat painting needs a UV set
            obj.data.uv_layers.new(name="UVMap", do_init=False)

    scale, scale_from = transfer_scale(context)
    swap = axis_swap(context, p, fmt)
    overrides = {"global_scale": scale}
    overrides.update(transfer.axis_overrides(fmt, "export", swap))

    ext = transfer.spec(fmt)["ext"]
    out_path = applink.model_path(primary, ext)
    back_path = applink.model_path(primary, ext, name="bridge_back")
    for root in roots:  # so 3D-Coat lists the target from every root it searches
        applink.ensure_app_folder(root)

    # Persistent per-object export aliases survive Blender-side renaming/reload.
    for obj in objects:
        obj["coat_bridge_source_name"] = obj.name
    suspended = []
    remeshed = 0
    try:
        if p.remesh and not p.apply_modifiers:
            for obj in objects:
                for modifier in obj.modifiers:
                    suspended.append((modifier, modifier.show_viewport, modifier.show_render))
                    modifier.show_viewport = False
                    modifier.show_render = False
            bpy.context.view_layer.update()
        remeshed = (add_remesh(objects, getattr(p, "remesh_voxel", 0.0),
                               getattr(p, "remesh_adaptivity", 0.0))
                    if p.remesh else 0)
        # the remesh only exists as a modifier, so the export has to apply modifiers
        dropped = transfer.export_model(out_path, fmt, objects,
                                        p.apply_modifiers or bool(remeshed), overrides)
    finally:
        try:
            remove_remesh(objects)
        finally:
            for modifier, viewport, render in suspended:
                modifier.show_viewport = viewport
                modifier.show_render = render
    replaced = applink.foreign_job(primary)
    if replaced:
        # one job file is shared with the official Blender AppLink, so a job of
        # theirs is replaced by ours here - say so, or it looks like a job that
        # vanished for no reason
        _log("replaced another AppLink's queued job: %s" % replaced)
    applink.write_import_txt(primary, out_path, back_path, p.mode, p.skip_dialogs)

    STATE["target"] = {"object": active.name, "file": out_path, "diagonal": _diagonal(objects[0])}
    STATE["last_send"] = time.time()
    for candidate in applink.signal_files(roots):
        STATE["seen"].pop(candidate, None)
    applied = []
    if scale != 1.0:
        applied.append("x%s (%s)" % (_trim(scale), scale_from))
    if swap is not None:
        applied.append("swap Y/Z" if swap else "Y up")
    if remeshed:
        applied.append("remeshed" if len(objects) == 1 else "remeshed %d" % remeshed)
    where = " [%s]" % ", ".join(applied) if applied else ""
    _log("sent %s: %s (%s, %d object(s)) diagonal %.4f m%s"
         % (active.name, os.path.basename(out_path), scope, len(objects),
            STATE["target"]["diagonal"] or 0.0, where))

    if applink.is_coat_running() is False:
        note = " - start 3D-Coat to pick it up"
    else:
        # A focus change may help on builds that pause in the background.
        note = " - bring 3D-Coat to the front to pick it up"
    merged = "" if len(objects) == 1 else " (%d merged)" % len(objects)
    _set_message("Sent %s%s (%s) -> %s%s%s"
                 % (active.name, merged, scope, os.path.basename(out_path), note, where))
    if dropped:
        STATE["log"].append("dropped unsupported options: %s" % ", ".join(dropped))
    return out_path


#: a pull in progress: the watcher's timer and a click can arrive together, and
#: two overlapping passes fight over the same objects
PULLING = [False]


def pull(context, force=False):
    """Consume the returned model.  Returns the list of messages produced.

    One trip means one model: the protocol uses a single fixed file name, and
    3D-Coat leaves a signal in **both** exchange roots (and can write the model
    into both as well).  So all the signals are read first and then exactly one
    model - the newest - is imported.  Importing per signal is what used to make
    the same model land in Blender twice.
    """
    if PULLING[0]:
        return ["a pull is already running - skipped"]
    PULLING[0] = True
    try:
        return _pull_once(context, force)
    finally:
        PULLING[0] = False


def _pull_once(context, force):
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    roots = applink.exchange_roots(p.exchange_folder)
    load_history(p)             # what earlier sessions already handled
    dirty = [False]             # only rewrite the record when something changed
    messages = []
    candidates = []          # (mtime, path)
    already = set()          # a path listed by more than one signal
    handled = []             # (signal, may be removed: it lists nothing foreign)

    for signal in applink.signal_files(roots):
        if not os.path.isfile(signal):
            continue
        mtime = os.path.getmtime(signal)
        if not force and STATE["seen"].get(signal) == mtime:
            continue
        paths = applink.read_export_paths(signal)
        ours = [path for path in paths if _is_ours(path, roots)]
        foreign = [path for path in paths if path not in ours]
        STATE["seen"][signal] = mtime
        dirty[0] = True
        if not ours:
            # 3D-Coat exports to its own AppLink pool as well (its own target), and
            # that export.txt points outside BlenderBridge.  A file written after
            # our last send is this trip's model, so take it: refusing it was why
            # "the model never arrives".
            last_send = STATE.get("last_send") or 0.0
            fresh = [path for path in foreign
                     if last_send > 0 and os.path.isfile(path) and os.path.getmtime(path) >= last_send - 2.0]
            if fresh:
                messages.append("3D-Coat used its own AppLink folder for %s" % os.path.basename(fresh[0]))
                handled.append((signal, False))        # never touch someone else's signal
                for path in fresh:
                    if path in already:
                        continue
                    already.add(path)
                    candidates.append((os.path.getmtime(path), path))
                continue
            if foreign:
                messages.append("Ignored export.txt outside BlenderBridge: %s" % os.path.basename(paths[0]))
            continue
        handled.append((signal, not foreign))
        for path in ours:
            if path in already:
                continue
            already.add(path)
            if not os.path.isfile(path):
                messages.append("returned file is missing: %s" % os.path.basename(path))
                continue
            candidates.append((os.path.getmtime(path), path))

    imported = []
    if candidates:
        candidates.sort(reverse=True)
        path = candidates[0][1]
        try:
            key = os.path.normcase(os.path.realpath(path))
            stat = os.stat(path)
            version = (stat.st_mtime_ns, stat.st_size)
            versions = STATE.setdefault("imported_versions", {})
            if not force and versions.get(key) == version:
                for signal, removable in handled:
                    if removable:
                        try:
                            os.remove(signal)
                        except OSError:
                            pass
                if dirty[0]:
                    save_history(p)
                return []  # a delayed mirror signal, not a new export
            receipt_version = receipts.fingerprint(path)
            imported = _import_and_link(context, path)
            if imported:
                # Recorded before the receipt is written, on purpose: the receipt is
                # a note to 3D-Coat, and a folder that cannot hold it (a read-only
                # or synced folder) must not make the same model look new again -
                # it would be imported on every watcher tick.
                versions[key] = version
                dirty[0] = True
                try:
                    receipts.acknowledge(path, "blender", receipt_version, imported)
                except Exception as exc:
                    messages.append("could not write the receipt: %s" % exc)
                    _log("receipt failed for %s: %s" % (os.path.basename(path), exc))
                if len(versions) > 128:
                    del versions[next(iter(versions))]
                if len(STATE["seen"]) > 256:
                    del STATE["seen"][next(iter(STATE["seen"]))]
        except Exception as exc:
            messages.append("import failed for %s: %s" % (os.path.basename(path), exc))
            _log("import failed for %s: %s" % (os.path.basename(path), exc))
            _log("import traceback:\n%s" % traceback.format_exc().strip())
            _log("import context: target=%r objects=%d" % (
                (STATE.get("target") or {}).get("object"), len(bpy.data.objects)))
    else:
        path = ""

    if imported:
        for signal, removable in handled:      # the trip is used up
            if removable:
                try:
                    os.remove(signal)
                except OSError:
                    pass
        STATE["last_pull"] = time.time()
        note = "Pulled %s from %s (%d objects)" % (", ".join(imported), os.path.basename(path), len(imported))
        messages.append(note)
        _set_message(note)
    else:
        # A signal is not an acknowledgement until its model was imported.
        # Exporters may publish the signal before finishing the model. Leave
        # unsuccessful owned signals retryable even if export.txt is unchanged.
        for signal, _removable in handled:
            STATE["seen"].pop(signal, None)
        if messages:
            _set_message(messages[-1])

    # record the outcome where both sides can read it: a silent pull cannot be
    # diagnosed, and the watcher's idle ticks must not fill the file
    if candidates or handled or messages:
        for message in messages or ["nothing importable in the signals"]:
            _log("pull: %s" % message)

    STATE["log"] += [msg for msg in messages if msg not in STATE["log"]]
    if dirty[0]:
        save_history(p)
    return messages


def visible_meshes(context):
    return [obj for obj in context.scene.objects
            if obj.type == "MESH" and obj.visible_get()]


def _send_objects(context, whole_scene=False):
    """What a Send exports.

    `whole_scene` (the toggle left of Send) means every visible mesh; otherwise the
    selection, falling back to every visible mesh when nothing is selected - the
    behaviour this add-on always had.
    """
    if whole_scene:
        visible = visible_meshes(context)
        if not visible:
            raise RuntimeError("no visible mesh object in the scene")
        return visible, "whole scene"
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if selected:
        return selected, "selection"
    visible = visible_meshes(context)
    if not visible:
        raise RuntimeError("no mesh object in the scene")
    return visible, "whole scene (nothing selected)"


def _object(name):
    """Fetch an object by name and make sure the struct is still alive.

    Blender invalidates Python references to objects when an operator pushes an
    undo step, so a reference captured before an import can raise
    "StructRNA of type Object has been removed" afterwards.  Everything that
    spans a bpy call goes through here.
    """
    if not name:
        return None
    obj = bpy.data.objects.get(name)
    if obj is None:
        return None
    try:
        obj.name          # touching it raises ReferenceError when it is gone
    except ReferenceError:
        return None
    return obj


def _import_and_link(context, path):
    fmt = transfer.format_from_path(path)
    if not transfer.ensure_module(fmt):
        raise RuntimeError(transfer.missing_reason(fmt) or "%s unavailable" % fmt)
    # The import pushes an undo step, so the object references it hands back can
    # already be dead (touching one is what raises "StructRNA of type Object has
    # been removed").  Take the names from the scene instead of from those
    # references: they are strings and cannot go stale.
    before_names = {obj.name for obj in bpy.data.objects}
    back_overrides = transfer.axis_overrides(fmt, "import", axis_swap(context, fmt=fmt))
    factor, _origin = transfer_scale(context)
    if factor > 0 and fmt not in SELF_DESCRIBING_AXES:
        # 3D-Coat wrote the model in its own units (centimetres, usually), so undo
        # the same conversion on the way home instead of guessing from the size
        back_overrides["global_scale"] = 1.0 / factor
    imported, dropped = transfer.import_model(path, fmt, back_overrides)
    if dropped:
        STATE["log"].append("dropped import options: %s" % ", ".join(dropped))
    arriving = [obj.name for obj in bpy.data.objects if obj.name not in before_names]
    if not arriving:
        # the import's own objects as a fallback, touched defensively (they may be
        # dead references - see _object)
        for obj in imported:
            try:
                if obj.name:
                    arriving.append(obj.name)
            except ReferenceError:
                continue
    if not arriving:
        raise RuntimeError("the import produced nothing we can see")

    names = []
    used = set()
    for arriving_name in arriving:
        source = _object(arriving_name)
        if source is None or source.type != "MESH":
            continue
        # Blender adds .001 when a name is occupied. Match only registered
        # bridge aliases, never arbitrary scene objects with a similar name.
        matches = []
        for existing_name in before_names:
            existing = _object(existing_name)
            if existing is None or existing.type != "MESH" or existing_name in used:
                continue
            alias = existing.get("coat_bridge_source_name")
            if not alias:
                continue
            suffix = arriving_name[len(alias):] if arriving_name.startswith(alias) else ""
            if arriving_name == alias or (suffix.startswith(".") and suffix[1:].isdigit()):
                matches.append(existing)
        target = matches[0] if len(matches) == 1 else None
        # Retain legacy single-object linkage only for a genuinely single return.
        if target is None and len(arriving) == 1 and not matches:
            old_name = (STATE.get("target") or {}).get("object")
            if old_name in before_names:
                candidate = _object(old_name)
                if candidate and candidate.type == "MESH":
                    target = candidate
        file_materials = []
        if _strip_enabled():
            file_materials = list({slot.material for slot in source.material_slots if slot.material})
            source.data.materials.clear()
        if target is not None:
            target_name = target.name
            used.add(target_name)
            _replace_mesh(target, source)
            scale_note = _match_scale(target) if len(arriving) == 1 else ""
            bpy.data.objects.remove(source, do_unlink=True)
            live = _object(target_name)
            if live is None:
                raise RuntimeError("target disappeared during mesh replacement")
            material_note = _strip_materials(live, file_materials)
            live["coat_bridge_file"] = path
            notes = [part for part in (scale_note, material_note) if part]
            names.append(live.name + (" (%s)" % " ".join(notes) if notes else ""))
        else:
            # Keep Blender's collision-safe name; do not rename an unrelated object.
            source["coat_bridge_file"] = path
            source["coat_bridge_source_name"] = arriving_name
            _strip_materials(source, file_materials)
            names.append(source.name)
            if matches:
                _log("ambiguous object association for %s; imported separately" % arriving_name)
    return names


def _replace_mesh(target, source):
    """Keep the target's identity (name, materials, placement) but take the
    returned geometry."""
    old_materials = [slot.material for slot in target.material_slots if slot.material]
    target.data = source.data
    # The shading set-up belongs to the user, not to the file that came back.
    if old_materials:
        for index, material in enumerate(old_materials):
            if index < len(target.data.materials):
                target.data.materials[index] = material
            else:
                target.data.materials.append(material)
    target.matrix_world = source.matrix_world
    if target.data.uv_layers:
        target.data.uv_layers[0].active_render = True


def _diagonal(obj):
    """World-space bounding-box diagonal of a mesh object, in scene units."""
    bpy.context.view_layer.update()
    matrix = obj.matrix_world
    corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    if not corners:
        return 0.0
    size = Vector((
        max(c.x for c in corners) - min(c.x for c in corners),
        max(c.y for c in corners) - min(c.y for c in corners),
        max(c.z for c in corners) - min(c.z for c in corners),
    ))
    return size.length


def _match_scale(target):
    """Undo a unit mismatch on the way back.

    3D-Coat exports with its own scene scale (Scene.GetSceneScale(): "the length
    of 1 scene unit when you export the scene"), so a model often comes home at a
    fixed multiple - x100 with FBX is the classic one.  Measure the returned
    geometry against the size that was sent and scale it back; report the factor
    so the mismatch is visible instead of mysterious.
    """
    p = prefs()
    if p is not None and not p.match_scale:
        return ""
    try:
        target = _object(target.name)
    except ReferenceError:
        return "size check skipped (the object went away)"
    if target is None:
        return "size check skipped (the object went away)"
    reference = (STATE["target"] or {}).get("diagonal") or 0.0
    size = _diagonal(target)
    if reference <= 0.0 or size <= 0.0:
        return ""
    ratio = reference / size
    if abs(ratio - 1.0) <= SCALE_TOLERANCE:
        _log("scale ok: %.4f m (sent %.4f m)" % (size, reference))
        return ""
    if not any(abs(ratio - clean) <= clean * 0.05 for clean in CLEAN_FACTORS):
        # the size differs but not by a unit conversion: that is the model itself
        # (a sculpt, a reduction), so leave the geometry alone and just say so
        _log("scale: %.4f m vs sent %.4f m is not a unit factor - left alone" % (size, reference))
        return "size differs (left alone)"
    if ratio > 1000.0 or ratio < 0.001:
        _log("scale x%.6g looks wrong - left alone (%.4f m vs sent %.4f m)" % (ratio, size, reference))
        return "scale x%.4g left alone" % ratio
    matrix = target.matrix_world.inverted() @ Matrix.Scale(ratio, 4) @ target.matrix_world
    target.data.transform(matrix)
    target.data.update()
    _log("scale matched: x%.6g (%.4f m -> %.4f m)" % (ratio, size, reference))
    return "scale x%.6g" % ratio


def _trim(value):
    """100.0 -> "100" but 0.01 stays readable."""
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text or "0"


def _strip_enabled():
    p = prefs()
    return bool(p is not None and p.strip_materials)


def _strip_materials(target, file_materials):
    """"Import without materials": drop the slots the mesh came with, and the
    material datablocks the file itself brought (only if nothing else uses them -
    the user's own materials are never touched)."""
    if not _strip_enabled():
        return ""
    count = len(target.material_slots)
    target.data.materials.clear()
    removed = 0
    for material in file_materials:
        if material.users == 0:
            bpy.data.materials.remove(material)
            removed += 1
    _log("materials stripped: %d slot(s), %d material(s) removed" % (count, removed))
    return "no materials" if count else ""


def _log(message):
    """Append a line to the log the 3D-Coat side writes too."""
    try:
        path = applink.shared_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("%s | blender | %s\n" % (time.strftime("%H:%M:%S"), message))
    except Exception:
        pass  # logging must never break a transfer


def _is_ours(path, roots):
    """A model inside one of our BlenderBridge folders is ours - nothing else is."""
    folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
    for root in roots:
        if folder == os.path.normcase(os.path.normpath(applink.app_folder(root))):
            return True
    return False


def _set_message(text):
    STATE["message"] = text
    scene = getattr(bpy.context, "scene", None)
    if scene is not None and hasattr(scene, "coat_bridge_status"):
        try:
            scene.coat_bridge_status = text
        except Exception:
            pass


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _stamp(value):
    return time.strftime("%H:%M:%S", time.localtime(value)) if value else "never"
