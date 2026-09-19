# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.

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
        self.report({"INFO"}, "Queued for 3D-Coat: %s" % os.path.basename(path))
        return {"FINISHED"}


class COATBRIDGE_OT_pull(bpy.types.Operator):
    bl_idname = "coatbridge.pull"
    bl_label = "Pull from 3D-Coat"
    bl_description = "Look for a model returned by 3D-Coat right now and merge it into the object it came from"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    force: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        try:
            messages = bridge.pull(context, force=self.force)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not messages:
            self.report({"INFO"}, "No new model. Send from 3D-Coat first.")
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
    bl_label = "CoatLink"
    bl_space_type = "TOPBAR"
    bl_region_type = "HEADER"
    bl_ui_units_x = 18

    def draw(self, context):
        layout = self.layout
        p = bridge.prefs(context)
        if p is None:
            layout.label(text="Preferences unavailable", icon="ERROR")
            return

        # Same order and wording as the 3D-Coat panel: the options, the two actions,
        # the return settings, then Setup.  Nothing behind a fold-out, but grouped so
        # it can be read at a glance: the remesh settings sit in a box of their own
        # because they belong together, and same-kind rows share a line.
        column = layout.column(align=True)
        column.label(text="Send options")
        column.prop(p, "scope", text="Scope")
        column.prop(p, "mode", text="Import as")
        box = column.box()
        box.prop(p, "remesh", text="Remesh on send")
        settings = box.column(align=True)
        settings.enabled = p.remesh     # always drawn, greyed when it does nothing
        settings.prop(p, "remesh_voxel", text="Voxel size (0 = auto)")
        settings.prop(p, "remesh_adaptivity", text="Adaptivity")
        column.separator()
        # the two actions, given the room the point of the add-on deserves
        row = column.row(align=True)
        row.scale_y = 1.4
        row.operator("coatbridge.send", text="Send", icon="EXPORT")
        row.operator("coatbridge.pull", text="Pull", icon="IMPORT")
        column.separator()
        column.label(text="Return")
        row = column.row(align=True)
        row.prop(p, "auto_pull", text="Auto receive")
        row.prop(p, "strip_materials", text="Without materials")
        column.separator()
        column.label(text="Setup")
        column.prop(p, "axis_mode", text="Axis")
        row = column.row(align=True)
        row.prop(p, "coat_scale", text="Scale (0 = auto)")
        row.prop(p, "match_scale", text="Match scale")
        row = column.row(align=True)
        row.prop(p, "apply_modifiers", text="Modifiers")
        row.prop(p, "skip_dialogs", text="Skip dialogs")
        row = column.row(align=True)
        row.operator("coatbridge.detect", text="Detect", icon="VIEWZOOM")
        row.operator("coatbridge.open_folder", text="Open folder", icon="FILE_FOLDER")
        row = column.row(align=True)
        row.operator("coatbridge.launch", text="Start 3D-Coat", icon="PLAY")
        row.operator("coatbridge.pull", text="Force re-read", icon="FILE_REFRESH").force = True
        column.operator("coatbridge.unlink", text="Unlink selected", icon="UNLINKED")
        for line in bridge.detail_lines(context)[1:4]:
            column.label(text=line)
        column.separator()
        column.label(text=bridge.status(context), icon="INFO")


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
    """Draw the top-bar entry: the settings menu, then the two actions that get
    used all the time right next to it, so a round trip is one click."""
    if context.region.alignment != "RIGHT":
        return
    row = self.layout.row(align=True)
    row.popover(panel=POPOVER_ID, text="CoatLink", icon="COLLAPSEMENU")


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
