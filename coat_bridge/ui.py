# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""One menu in the top bar.  Everything the bridge does lives inside it.

The button is drawn the same way other top-bar extras are (see the bundled
auto_reload extension): a popover panel registered for the TOPBAR space, hooked
into TOPBAR_HT_upper_bar and drawn only in the right-hand group.
"""

import os
import subprocess

import bpy

from . import applink, bridge

POPOVER_ID = "COATBRIDGE_PT_menu"


class COATBRIDGE_OT_send(bpy.types.Operator):
    bl_idname = "coatbridge.send"
    bl_label = "Send to 3D-Coat"
    bl_description = "Export the selection (or all visible meshes) to the exchange folder and ask 3D-Coat to load it"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        try:
            path = bridge.send(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Sent to 3D-Coat: %s" % os.path.basename(path))
        return {"FINISHED"}


class COATBRIDGE_OT_pull(bpy.types.Operator):
    bl_idname = "coatbridge.pull"
    bl_label = "Pull from 3D-Coat"
    bl_description = "Look for a model returned by 3D-Coat right now and merge it into the object it came from"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        try:
            messages = bridge.pull(context, force=True)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not messages:
            self.report({"INFO"}, "Nothing to pull yet")
        for message in messages:
            self.report({"INFO"}, message)
        return {"FINISHED"}


class COATBRIDGE_OT_detect(bpy.types.Operator):
    bl_idname = "coatbridge.detect"
    bl_label = "Use detected folder"
    bl_description = "Find the 3D-Coat exchange folder and prepare the AppLink folder inside it"
    bl_options = {"REGISTER"}

    def execute(self, context):
        p = bridge.prefs(context)
        if p is None:
            self.report({"ERROR"}, "add-on preferences unavailable")
            return {"CANCELLED"}
        exchange = applink.detect_exchange(p.exchange_folder)
        p.exchange_folder = exchange
        folder = applink.ensure_app_folder(exchange)
        self.report({"INFO"}, "Exchange: %s" % exchange)
        self.report({"INFO"}, "AppLink target ready: %s" % folder)
        return {"FINISHED"}


class COATBRIDGE_OT_open_folder(bpy.types.Operator):
    bl_idname = "coatbridge.open_folder"
    bl_label = "Open exchange folder"
    bl_description = "Show the exchange folder in the file browser"
    bl_options = {"REGISTER"}

    def execute(self, context):
        p = bridge.prefs(context)
        exchange = applink.resolve_exchange(p.exchange_folder if p else "")
        if not os.path.isdir(exchange):
            self.report({"ERROR"}, "not found: %s" % exchange)
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=exchange)
        return {"FINISHED"}


class COATBRIDGE_OT_launch(bpy.types.Operator):
    bl_idname = "coatbridge.launch"
    bl_label = "Launch 3D-Coat"
    bl_description = "Start 3D-Coat so it picks up the queued import"
    bl_options = {"REGISTER"}

    def execute(self, context):
        exe = applink.find_coat_executable()
        if not exe:
            self.report({"ERROR"}, "3D-Coat executable not found")
            return {"CANCELLED"}
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
        self.report({"INFO"}, "Launched %s" % exe)
        return {"FINISHED"}


class COATBRIDGE_OT_unlink(bpy.types.Operator):
    bl_idname = "coatbridge.unlink"
    bl_label = "Unlink selected"
    bl_description = "Stop tracking the selected objects, so a pulled model becomes a new object instead of replacing them"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.get("coat_bridge_file"):
                del obj["coat_bridge_file"]
                count += 1
        self.report({"INFO"}, "Unlinked %d object(s)" % count)
        return {"FINISHED"}


class COATBRIDGE_PT_menu(bpy.types.Panel):
    """The whole bridge UI, opened from the top-bar button."""

    bl_idname = POPOVER_ID
    bl_label = "Coat Bridge"
    bl_space_type = "TOPBAR"
    bl_region_type = "HEADER"
    bl_ui_units_x = 16

    def draw(self, context):
        layout = self.layout
        p = bridge.prefs(context)
        if p is None:
            layout.label(text="Preferences unavailable", icon="ERROR")
            return

        column = layout.column(align=True)
        row = column.row()
        row.scale_y = 1.5
        row.operator("coatbridge.send", icon="EXPORT")
        row = column.row()
        row.scale_y = 1.3
        row.operator("coatbridge.pull", icon="IMPORT")

        column.separator(factor=1.2)
        column.prop(p, "mode", text="Open as")

        column.separator(factor=1.2)
        grid = column.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.prop(p, "auto_pull", text="Auto pull")
        grid.prop(p, "skip_dialogs", text="Skip dialogs")
        grid.prop(p, "apply_modifiers", text="Modifiers")
        grid.prop(p, "match_scale", text="Match scale")
        grid.prop(p, "strip_materials", text="No materials")
        grid.operator("coatbridge.detect", text="Detect")

        column.separator(factor=1.2)
        column.label(text="3D-Coat export")
        column.prop(p, "export_resolution", text="")
        export_row = column.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        export_row.prop(p, "export_textures", text="Textures")
        export_row.prop(p, "export_coarse_mesh", text="Coarse")
        column.prop(p, "export_polycount", text="Polycount")

        column.separator(factor=1.2)
        row = column.row(align=True)
        row.operator("coatbridge.open_folder", text="Folder", icon="FILE_FOLDER")
        row.operator("coatbridge.launch", text="Start 3D-Coat", icon="PLAY")

        box = layout.box()
        box.label(text=bridge.status(context), icon="INFO")
        for line in bridge.detail_lines(context)[1:4]:
            box.label(text=line)

        row = layout.row()
        row.alignment = "RIGHT"
        row.operator("coatbridge.unlink", text="Unlink selected", icon="UNLINKED")


CLASSES = (
    COATBRIDGE_OT_send,
    COATBRIDGE_OT_pull,
    COATBRIDGE_OT_detect,
    COATBRIDGE_OT_open_folder,
    COATBRIDGE_OT_launch,
    COATBRIDGE_OT_unlink,
    COATBRIDGE_PT_menu,
)


def topbar_drawer(self, context):
    """Draw the button in the right-hand group of the top bar."""
    if context.region.alignment != "RIGHT":
        return
    row = self.layout.row(align=True)
    row.popover(panel=POPOVER_ID, text="Coat Bridge", icon="EXPORT")


def _header_hook():
    return getattr(bpy.types, "TOPBAR_HT_upper_bar", None)


#: True once the button is really hooked into the top bar (checked by the tests)
HOOK_INSTALLED = False


def register():
    global HOOK_INSTALLED
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    hook = _header_hook()
    if hook is not None:  # absent when Blender runs without UI scripts
        hook.prepend(topbar_drawer)
        HOOK_INSTALLED = True


def unregister():
    global HOOK_INSTALLED
    hook = _header_hook()
    if hook is not None:
        try:
            hook.remove(topbar_drawer)
        except Exception:
            pass  # a reloaded add-on leaves a stale handler behind; nothing to fix
    HOOK_INSTALLED = False
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
