# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Panel and buttons.  Everything the bridge does is two clicks away."""

import os
import subprocess

import bpy

from . import applink, bridge, transfer

CATEGORY = "3D-Coat"


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


class COATBRIDGE_PT_main(bpy.types.Panel):
    bl_label = "Coat Bridge"
    bl_idname = "COATBRIDGE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY

    def draw(self, context):
        layout = self.layout
        p = bridge.prefs(context)
        if p is None:
            layout.label(text="Add-on preferences unavailable", icon="ERROR")
            return

        column = layout.column(align=True)
        row = column.row()
        row.scale_y = 1.7
        row.operator("coatbridge.send", icon="EXPORT")
        row = column.row()
        row.scale_y = 1.4
        row.operator("coatbridge.pull", icon="IMPORT")

        column.separator(factor=1.2)
        column.prop(p, "mode", text="")
        column.prop(p, "fmt", text="Format")

        column.separator(factor=1.2)
        grid = column.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.prop(p, "auto_pull", text="Auto pull")
        grid.prop(p, "skip_dialogs", text="Skip dialogs")
        grid.prop(p, "apply_modifiers", text="Modifiers")
        grid.operator("coatbridge.detect", text="Detect")

        box = layout.box()
        box.label(text=bridge.status(context), icon="INFO")
        row = box.row(align=True)
        row.operator("coatbridge.open_folder", text="Folder", icon="FILE_FOLDER")
        row.operator("coatbridge.launch", text="Start 3D-Coat", icon="PLAY")
        row.operator("coatbridge.unlink", text="", icon="UNLINKED")


class COATBRIDGE_PT_details(bpy.types.Panel):
    bl_label = "Details"
    bl_idname = "COATBRIDGE_PT_details"
    bl_parent_id = "COATBRIDGE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        p = bridge.prefs(context)
        if p is None:
            return
        exchange = applink.resolve_exchange(p.exchange_folder)
        row = layout.row()
        row.alert = not os.path.isdir(exchange)
        row.prop(p, "exchange_folder", text="")
        layout.separator(factor=0.8)
        box = layout.box()
        for line in bridge.detail_lines(context):
            box.label(text=line)


CLASSES = (
    COATBRIDGE_OT_send,
    COATBRIDGE_OT_pull,
    COATBRIDGE_OT_detect,
    COATBRIDGE_OT_open_folder,
    COATBRIDGE_OT_launch,
    COATBRIDGE_OT_unlink,
    COATBRIDGE_PT_main,
    COATBRIDGE_PT_details,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
