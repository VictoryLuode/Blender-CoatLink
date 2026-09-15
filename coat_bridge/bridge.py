# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Send / pull orchestration.

Send : export the chosen meshes to <root>/BlenderBridge/bridge.<ext> and drop a
       root-level import.txt next to it, then remember where they came from.
Pull : watch <root>/BlenderBridge/export.txt for the returned model and merge it
       into the object the send came from.

Everything 3D-Coat writes into a BlenderBridge folder is ours; anything else is
left alone, so the official 3D-Coat AppLink can stay enabled.
"""

import os
import time

import bpy
from mathutils import Matrix, Vector

from . import applink, transfer

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
    "message": "Ready",
    "log": [],
}


def prefs(context=None):
    ctx = context or bpy.context
    addons = getattr(ctx.preferences, "addons", None)
    if addons is None:
        return None
    entry = addons.get(ROOT)
    return entry.preferences if entry else None


def status(context=None):
    return STATE["message"]


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
    lines.append("Last send %s / last pull %s" % (_stamp(STATE["last_send"]), _stamp(STATE["last_pull"])))
    linked = [obj for obj in bpy.data.objects if obj.get("coat_bridge_file")]
    lines.append("Linked objects: %s" % (", ".join(obj.name for obj in linked[:6]) or "none"))
    lines += STATE["log"][-3:]
    return lines


def export_options(p):
    """The "3D-Coat export" preferences, as job-file option tuples.

    Order matters: a "[field ...]" command replaces earlier option commands, so
    it goes first and the plain "[Option=value]" lines follow it.
    """
    if p is None:
        return []
    out = []
    if p.export_polycount > 0:
        out.append(("field", "$ExportOpt::DesiredPolycount", int(p.export_polycount)))
    if p.export_resolution != "unset":
        out.append(("option", "ExportResolution", p.export_resolution))
    out.append(("option", "ExportTextures", 1 if p.export_textures else 0))
    out.append(("option", "CoarseMesh", 1 if p.export_coarse_mesh else 0))
    return out


def options_note(p):
    """Short human note for the status line / log, "" when nothing is set."""
    if p is None:
        return ""
    bits = []
    if p.export_polycount > 0:
        bits.append("%d polys" % p.export_polycount)
    if p.export_resolution != "unset":
        bits.append(p.export_resolution)
    if not p.export_textures:
        bits.append("no textures")
    if p.export_coarse_mesh:
        bits.append("coarse")
    return ", ".join(bits)


def send(context):
    """Export the selection (or every visible mesh) and queue it for 3D-Coat."""
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    roots = applink.exchange_roots(p.exchange_folder)
    primary = roots[0]
    if not os.path.isdir(primary):
        raise RuntimeError("exchange folder not found: %s (press Detect in the panel)" % primary)

    objects = _send_objects(context)
    active = context.view_layer.objects.active
    if active not in objects:
        active = objects[0]

    fmt = SEND_FORMAT
    if not transfer.ensure_module(fmt):
        raise RuntimeError(transfer.missing_reason(fmt) or "%s unavailable" % fmt)
    for obj in objects:
        if not obj.data.uv_layers:  # 3D-Coat painting needs a UV set
            obj.data.uv_layers.new(name="UVMap", do_init=False)

    ext = transfer.spec(fmt)["ext"]
    out_path = applink.model_path(primary, ext)
    back_path = applink.model_path(primary, ext, name="bridge_back")
    for root in roots:  # so 3D-Coat lists the target from every root it searches
        applink.ensure_app_folder(root)

    dropped = transfer.export_model(out_path, fmt, objects, p.apply_modifiers)
    applink.write_import_txt(primary, out_path, back_path, p.mode, p.skip_dialogs, export_options(p))

    STATE["target"] = {"object": active.name, "file": out_path, "diagonal": _diagonal(objects[0])}
    STATE["last_send"] = time.time()
    for candidate in applink.signal_files(roots):
        STATE["seen"].pop(candidate, None)
    asked = options_note(p)
    _log("sent %s: %s diagonal %.4f m%s" % (active.name, os.path.basename(out_path),
                                            STATE["target"]["diagonal"] or 0.0,
                                            " [%s]" % asked if asked else ""))

    note = "" if applink.is_coat_running() is not False else " - start 3D-Coat to pick it up"
    merged = "" if len(objects) == 1 else " (%d merged)" % len(objects)
    _set_message("Sent %s%s -> %s%s%s" % (active.name, merged, os.path.basename(out_path), note,
                                          " [%s]" % asked if asked else ""))
    if dropped:
        STATE["log"].append("dropped unsupported options: %s" % ", ".join(dropped))
    return out_path


def pull(context, force=False):
    """Consume a returned model.  Returns the list of messages produced."""
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    roots = applink.exchange_roots(p.exchange_folder)
    messages = []

    for signal in applink.signal_files(roots):
        if not os.path.isfile(signal):
            continue
        mtime = os.path.getmtime(signal)
        if not force and STATE["seen"].get(signal) == mtime:
            continue
        paths = applink.read_export_paths(signal)
        ours = [path for path in paths if _is_ours(path, roots)]
        foreign = [path for path in paths if path not in ours]
        if not ours:
            STATE["seen"][signal] = mtime
            if foreign:
                messages.append("Ignored export.txt outside BlenderBridge: %s" % os.path.basename(paths[0]))
            continue

        STATE["seen"][signal] = mtime
        imported = []
        for path in ours:
            if not os.path.isfile(path):
                messages.append("returned file is missing: %s" % os.path.basename(path))
                continue
            try:
                imported += _import_and_link(context, path)
            except Exception as exc:
                messages.append("import failed for %s: %s" % (os.path.basename(path), exc))
        if imported and not foreign:
            try:
                os.remove(signal)
            except OSError:
                pass
        if imported:
            STATE["last_pull"] = time.time()
            note = "Pulled %s from %s" % (", ".join(imported), os.path.basename(paths[0]))
            messages.append(note)
            _set_message(note)
        elif messages:
            _set_message(messages[-1])

    STATE["log"] += [msg for msg in messages if msg not in STATE["log"]]
    return messages


def _send_objects(context):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if selected:
        return selected
    visible = [obj for obj in context.scene.objects
               if obj.type == "MESH" and obj.visible_get()]
    if not visible:
        raise RuntimeError("no mesh object in the scene")
    return visible


def _import_and_link(context, path):
    fmt = transfer.format_from_path(path)
    if not transfer.ensure_module(fmt):
        raise RuntimeError(transfer.missing_reason(fmt) or "%s unavailable" % fmt)
    imported, dropped = transfer.import_model(path, fmt)
    if dropped:
        STATE["log"].append("dropped import options: %s" % ", ".join(dropped))

    target_name = (STATE["target"] or {}).get("object")
    target = bpy.data.objects.get(target_name) if target_name else None
    if target is None:
        target = bpy.data.objects.get(_stem(path))
    names = []
    if target is not None and target.type == "MESH":
        file_materials = []
        if _strip_enabled():
            # collect what the file brought, then keep it out of the target
            file_materials = [slot.material for slot in imported[0].material_slots if slot.material]
            imported[0].data.materials.clear()
        _replace_mesh(target, imported[0])
        scale_note = _match_scale(target)
        target["coat_bridge_file"] = path
        bpy.data.objects.remove(imported[0], do_unlink=True)
        # only now can the imported materials be collected (nothing references them)
        material_note = _strip_materials(target, file_materials)
        notes = [note for note in (scale_note, material_note) if note]
        names.append(target.name + (" (%s)" % " ".join(notes) if notes else ""))
        imported = imported[1:]
    for extra in imported:
        extra["coat_bridge_file"] = path
        names.append(extra.name)
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
    reference = (STATE["target"] or {}).get("diagonal") or 0.0
    size = _diagonal(target)
    if reference <= 0.0 or size <= 0.0:
        return ""
    ratio = reference / size
    if abs(ratio - 1.0) <= SCALE_TOLERANCE:
        _log("scale ok: %.4f m (sent %.4f m)" % (size, reference))
        return ""
    if ratio > 1000.0 or ratio < 0.001:
        _log("scale x%.6g looks wrong - left alone (%.4f m vs sent %.4f m)" % (ratio, size, reference))
        return "scale x%.4g left alone" % ratio
    matrix = target.matrix_world.inverted() @ Matrix.Scale(ratio, 4) @ target.matrix_world
    target.data.transform(matrix)
    target.data.update()
    _log("scale matched: x%.6g (%.4f m -> %.4f m)" % (ratio, size, reference))
    return "scale x%.6g" % ratio


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
