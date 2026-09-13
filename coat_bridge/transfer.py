# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Model transport: export the selection, import a returned file.

Only operators that actually exist in the running Blender are used, and only
keyword arguments the operator declares are passed.  Everything dropped or
unavailable is reported instead of silently ignored.
"""

import os

import bpy

FORMATS = {
    "obj": {
        "ext": "obj",
        "export": ("wm", "obj_export"),
        "import": ("wm", "obj_import"),
        "export_kwargs": {
            "export_selected_objects": True,
            "apply_modifiers": True,
            "export_materials": True,
            "export_uv": True,
            "export_normals": True,
            "export_pbr_extensions": False,
            "path_mode": "AUTO",
            "forward_axis": "NEGATIVE_Z",
            "up_axis": "Y",
            "global_scale": 1.0,
        },
        "import_kwargs": {
            "use_split_objects": True,
            "use_split_groups": False,
            "forward_axis": "NEGATIVE_Z",
            "up_axis": "Y",
            "global_scale": 1.0,
        },
    },
    "fbx": {
        "ext": "fbx",
        "export": ("export_scene", "fbx"),
        "import": ("import_scene", "fbx"),
        "requires_module": "io_scene_fbx",
        "export_kwargs": {
            "use_selection": True,
            "apply_scale_options": "FBX_SCALE_NONE",
            "path_mode": "AUTO",
            "embed_textures": False,
            "axis_forward": "-Z",
            "axis_up": "Y",
            "global_scale": 1.0,
        },
        "import_kwargs": {
            "global_scale": 1.0,
            "use_custom_normals": True,
        },
    },
    "ply": {
        "ext": "ply",
        "export": ("wm", "ply_export"),
        "import": ("wm", "ply_import"),
        "export_kwargs": {
            "export_selected_objects": True,
            "apply_modifiers": True,
            "export_uv": True,
            "export_normals": True,
            "global_scale": 1.0,
        },
        "import_kwargs": {},
    },
    "stl": {
        "ext": "stl",
        "export": ("wm", "stl_export"),
        "import": ("wm", "stl_import"),
        "export_kwargs": {
            "export_selected_objects": True,
            "apply_modifiers": True,
            "global_scale": 1.0,
        },
        "import_kwargs": {},
    },
}

FORMAT_ITEMS = [
    ("obj", "OBJ - materials + UV, best for 3D-Coat painting", ""),
    ("fbx", "FBX - needs the FBX add-on", ""),
    ("ply", "PLY - geometry + UV, no materials", ""),
    ("stl", "STL - geometry only", ""),
]


def spec(fmt):
    return FORMATS.get(fmt) or FORMATS["obj"]


def format_items():
    return FORMAT_ITEMS


def operator(which, fmt):
    """The operator for 'export'/'import', or None when it is not registered."""
    mod, name = spec(fmt)[which]
    op = getattr(getattr(bpy.ops, mod, None), name, None)
    if op is None:
        return None
    try:
        op.get_rna_type()  # raises for names that only look like operators
    except Exception:
        return None
    return op


def missing_reason(fmt):
    """Human readable reason why this format cannot be used right now."""
    info = spec(fmt)
    needed = info.get("requires_module")
    if needed and operator("export", fmt) is None:
        return "%s needs the '%s' add-on enabled" % (fmt.upper(), needed)
    for which in ("export", "import"):
        if operator(which, fmt) is None:
            return "%s %s operator is unavailable in Blender %s" % (
                fmt.upper(), which, bpy.app.version_string)
    return ""


def ensure_module(fmt):
    """Enable the bundled I/O add-on a format needs (FBX lives in io_scene_fbx)."""
    needed = spec(fmt).get("requires_module")
    if not needed:
        return True
    import addon_utils

    try:
        addon_utils.enable(needed, default_set=True, persistent=True)
    except Exception:
        pass
    return operator("export", fmt) is not None


def select_only(objects):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def export_model(filepath, fmt, objects, apply_modifiers=True):
    """Export objects to filepath.  Returns the list of kwargs that were dropped."""
    if not objects:
        raise RuntimeError("nothing selected to export")
    op = operator("export", fmt)
    if op is None:
        raise RuntimeError(missing_reason(fmt) or "export operator unavailable")

    kwargs = dict(spec(fmt)["export_kwargs"])
    if not apply_modifiers:
        kwargs.pop("apply_modifiers", None)
    select_only(objects)
    return _call(op, filepath, kwargs, "%s export" % fmt.upper())


def import_model(filepath, fmt):
    """Import filepath, returning the objects that appeared."""
    op = operator("import", fmt)
    if op is None:
        raise RuntimeError(missing_reason(fmt) or "import operator unavailable")
    before = {obj.name for obj in bpy.data.objects}
    dropped = _call(op, filepath, dict(spec(fmt)["import_kwargs"]), "%s import" % fmt.upper())
    new = [obj for obj in bpy.data.objects if obj.name not in before]
    if not new:
        raise RuntimeError("import produced no objects (%s)" % os.path.basename(filepath))
    return new, dropped


def format_from_path(path):
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext if ext in FORMATS else "obj"


def _call(op, filepath, kwargs, label):
    declared = {prop.identifier for prop in op.get_rna_type().properties}
    dropped = sorted(key for key in kwargs if key not in declared)
    call = {key: value for key, value in kwargs.items() if key in declared}
    call["filepath"] = filepath
    result = op(**call)
    if "FINISHED" not in result:
        raise RuntimeError("%s returned %s" % (label, result))
    return dropped
