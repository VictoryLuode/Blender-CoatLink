# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Send / pull orchestration.

Send   : export the chosen meshes to <exchange>/coat_bridge_out.<ext> and drop
         an import.txt next to it, then remember what is expected back.
Pull   : watch <exchange>/export.txt (and our own AppLink folder) for the
         returned model and merge it into the object it came from.

Only files this bridge owns are ever consumed, so the official 3D-Coat AppLink
can stay enabled without the two add-ons fighting over the same signal files.
"""

import os
import time

import bpy

from . import applink, textures as textures_module, transfer

ROOT = __package__.split(".")[0]

STATE = {
    "pending": {},      # normalised return path -> {"active": name, "objects": [names]}
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
    lines = []
    p = prefs(context)
    if p is None:
        return ["Add-on preferences unavailable"]
    exchange = applink.resolve_exchange(p.exchange_folder)
    lines.append("Exchange: %s" % exchange)
    lines.append("AppLink folder: %s" % applink.app_folder(exchange))
    if STATE["pending"]:
        for path, info in STATE["pending"].items():
            lines.append("Waiting for: %s -> %s" % (os.path.basename(path), info["active"]))
    else:
        lines.append("Waiting for: nothing")
    lines.append("Last send: %s" % _stamp(STATE["last_send"]))
    lines.append("Last pull: %s" % _stamp(STATE["last_pull"]))
    linked = [(obj.name, obj.get("coat_bridge_file", "")) for obj in bpy.data.objects
              if obj.get("coat_bridge_file")]
    lines.append("Linked objects: %d" % len(linked))
    for name, path in linked[:8]:
        lines.append("   %s <- %s" % (name, os.path.basename(path)))
    lines += STATE["log"][-4:]
    return lines


def send(context):
    """Export the selection (or every visible mesh) and queue it for 3D-Coat."""
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    exchange = applink.resolve_exchange(p.exchange_folder)
    if not os.path.isdir(exchange):
        raise RuntimeError("exchange folder not found: %s (press Detect in the Coat Bridge panel)" % exchange)

    objects = _send_objects(context)
    active = context.view_layer.objects.active
    if active not in objects:
        active = objects[0]

    fmt = p.fmt
    if not transfer.ensure_module(fmt):
        raise RuntimeError(transfer.missing_reason(fmt) or "%s unavailable" % fmt)
    for obj in objects:
        if not obj.data.uv_layers:  # 3D-Coat painting needs a UV set
            obj.data.uv_layers.new(name="UVMap", do_init=False)

    out_path = os.path.join(exchange, "%s_out.%s" % (applink.PREFIX, transfer.spec(fmt)["ext"]))
    back_path = os.path.join(exchange, "%s_back.%s" % (applink.PREFIX, transfer.spec(fmt)["ext"]))
    applink.ensure_folders(exchange, transfer.spec(fmt)["ext"])

    dropped = transfer.export_model(out_path, fmt, objects, p.apply_modifiers)
    applink.write_import_txt(exchange, out_path, back_path, p.mode, p.preset,
                             p.skip_import, p.skip_export)

    STATE["pending"][_norm(back_path)] = {"active": active.name, "objects": [o.name for o in objects]}
    STATE["last_send"] = time.time()
    for candidate in applink.export_txt_candidates(exchange):
        STATE["seen"].pop(candidate, None)

    running = applink.is_coat_running()
    note = "" if running is not False else " - 3D-Coat is not running, start it to pick this up"
    merged = "" if len(objects) == 1 else " (%d merged)" % len(objects)
    _set_message("Sent %s%s -> %s%s" % (active.name, merged, os.path.basename(out_path), note))
    if dropped:
        STATE["log"].append("dropped unsupported options: %s" % ", ".join(dropped))
    return out_path


def pull(context, force=False):
    """Consume a returned model.  Returns the list of messages produced."""
    p = prefs(context)
    if p is None:
        raise RuntimeError("add-on preferences unavailable")
    exchange = applink.resolve_exchange(p.exchange_folder)
    messages = []

    for signal in applink.export_txt_candidates(exchange):
        if not os.path.isfile(signal):
            continue
        mtime = os.path.getmtime(signal)
        if not force and STATE["seen"].get(signal) == mtime:
            continue
        paths = applink.read_export_paths(signal)
        ours = [path for path in paths if _is_ours(path, exchange)]
        foreign = [path for path in paths if path not in ours]
        if not ours:
            STATE["seen"][signal] = mtime
            if foreign:
                messages.append("Left export.txt alone (not ours): %s" % os.path.basename(paths[0]))
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
            if p.apply_textures:
                texture_notes = _apply_textures(context, imported)
                messages += texture_notes
                if texture_notes:
                    _set_message("%s | %s" % (note, texture_notes[0]))
        elif messages:
            _set_message(messages[-1])

    STATE["log"] += [msg for msg in messages if msg not in STATE["log"]]
    return messages


def arm(context):
    """Forget what was already seen so the next return is picked up at once."""
    for candidate in applink.export_txt_candidates(applink.resolve_exchange(
            prefs(context).exchange_folder)):
        STATE["seen"].pop(candidate, None)


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
    pending = STATE["pending"].get(_norm(path))
    imported, dropped = transfer.import_model(path, fmt)
    if dropped:
        STATE["log"].append("dropped import options: %s" % ", ".join(dropped))

    target = bpy.data.objects.get(pending["active"]) if pending else None
    if target is None:
        target = bpy.data.objects.get(_stem(path))
    names = []
    if target is not None and target.type == "MESH":
        _replace_mesh(target, imported[0])
        target["coat_bridge_file"] = path
        bpy.data.objects.remove(imported[0], do_unlink=True)
        names.append(target.name)
        imported = imported[1:]
    for extra in imported:
        extra["coat_bridge_file"] = path
        names.append(extra.name)
    return names


def _replace_mesh(target, source):
    """Keep the target's identity (name, materials, transform chain) but take
    the returned geometry and placement."""
    old_materials = [slot.material for slot in target.material_slots if slot.material]
    target.data = source.data
    # The object's shading set-up belongs to the user, not to the file that
    # came back: keep the original materials and only take the new mesh.
    if old_materials:
        for index, material in enumerate(old_materials):
            if index < len(target.data.materials):
                target.data.materials[index] = material
            else:
                target.data.materials.append(material)
    target.matrix_world = source.matrix_world
    if target.data.uv_layers:
        target.data.uv_layers[0].active_render = True


def _apply_textures(context, object_names):
    p = prefs(context)
    exchange = applink.resolve_exchange(p.exchange_folder)
    path = applink.textures_txt(exchange)
    records = applink.read_texture_records(path)
    if not records:
        return ["no textures.txt found next to the model"]
    scene_objects = [bpy.data.objects[name] for name in object_names if name in bpy.data.objects]
    by_material, unresolved = textures_module.resolve_materials(records, scene_objects)
    log = []
    applied = 0
    for material_name, material_records in by_material.items():
        material = bpy.data.materials.get(material_name)
        if material:
            applied += textures_module.apply_maps(material, material_records, log)
    if unresolved:
        log.append("%d texture record(s) had no matching material" % len(unresolved))
    return ["textures: %d map(s) applied" % applied] + log


def _is_ours(path, exchange):
    if _norm(path) in STATE["pending"]:
        return True
    folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
    if folder == os.path.normcase(os.path.normpath(applink.app_folder(exchange))):
        return True
    return os.path.basename(path).startswith(applink.PREFIX)


def _set_message(text):
    STATE["message"] = text
    scene = getattr(bpy.context, "scene", None)
    if scene is not None and hasattr(scene, "coat_bridge_status"):
        try:
            scene.coat_bridge_status = text
        except Exception:
            pass


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _stamp(value):
    return time.strftime("%H:%M:%S", time.localtime(value)) if value else "never"
