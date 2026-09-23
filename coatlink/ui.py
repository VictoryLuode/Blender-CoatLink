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
import textwrap

import bpy

from . import applink, bridge

POPOVER_ID = "COATLINK_PT_menu"


def status_lines(message):
    """Fixed-height readout; Copy details preserves the complete text."""
    lines = textwrap.wrap(str(message), width=44) or [""]
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:41] + "..."
    return lines + [""] * (4 - len(lines))


class COATLINK_OT_send(bpy.types.Operator):
    bl_idname = "coatlink.send"
    bl_label = "Send to 3D-Coat"
    bl_description = "Export the selection (or all visible meshes) to the exchange folder and ask 3D-Coat to load it"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Switch to Object Mode to send models")
            return False
        return True

    def execute(self, context):
        try:
            path = bridge.send(context)
        except Exception as exc:
            bridge._set_message("Send failed: %s" % exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Queued for 3D-Coat: %s" % os.path.basename(path))
        return {"FINISHED"}


class COATLINK_OT_pull(bpy.types.Operator):
    bl_idname = "coatlink.pull"
    bl_label = "Pull from 3D-Coat"
    bl_description = "Look for a model returned by 3D-Coat right now and merge it into the object it came from"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT":
            cls.poll_message_set("Switch to Object Mode to receive models")
            return False
        return True

    force: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        try:
            messages = bridge.pull(context, force=self.force)
        except Exception as exc:
            bridge._set_message("Pull failed: %s" % exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not messages:
            bridge._set_message("No new model. Send from 3D-Coat first.")
            self.report({"INFO"}, "No new model. Send from 3D-Coat first.")
        for message in messages:
            self.report({"INFO"}, message)
        return {"FINISHED"}


class COATLINK_OT_detect(bpy.types.Operator):
    bl_idname = "coatlink.detect"
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


class COATLINK_OT_open_folder(bpy.types.Operator):
    bl_idname = "coatlink.open_folder"
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


class COATLINK_OT_launch(bpy.types.Operator):
    bl_idname = "coatlink.launch"
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


class COATLINK_OT_unlink(bpy.types.Operator):
    bl_idname = "coatlink.unlink"
    bl_label = "Unlink selected"
    bl_description = "Stop tracking the selected objects, so a pulled model becomes a new object instead of replacing them"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if bridge.link_path(obj):
                bridge.clear_link(obj)
                count += 1
        self.report({"INFO"}, "Unlinked %d object(s)" % count)
        return {"FINISHED"}


class COATLINK_OT_copy_details(bpy.types.Operator):
    bl_idname = "coatlink.copy_details"
    bl_label = "Copy details"
    bl_description = "Copy the full status, exchange paths and recent diagnostics to the clipboard (may contain local paths)"

    def execute(self, context):
        context.window_manager.clipboard = "\n".join(
            ["CoatLink", bridge.status(context)] + bridge.detail_lines(context))
        self.report({"INFO"}, "Details copied (includes local paths)")
        return {"FINISHED"}


class COATLINK_PT_menu(bpy.types.Panel):
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
        column.prop(p, "send_origin", text="Send to origin")
        box = column.box()
        box.prop(p, "remesh", text="Remesh on send")
        settings = box.column(align=True)
        settings.enabled = p.remesh     # always drawn, greyed when it does nothing
        settings.prop(p, "remesh_voxel", text="Voxel size (0 = auto)")
        settings.prop(p, "remesh_adaptivity", text="Adaptivity")
        # the two actions, given the room the point of the add-on deserves
        row = column.row(align=True)
        row.scale_y = 1.4
        row.operator("coatlink.send", text="Send", icon="EXPORT")
        row.operator("coatlink.pull", text="Pull", icon="IMPORT")
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
        row.operator("coatlink.detect", text="Detect", icon="VIEWZOOM")
        row.operator("coatlink.open_folder", text="Open folder", icon="FILE_FOLDER")
        row = column.row(align=True)
        row.operator("coatlink.launch", text="Start 3D-Coat", icon="PLAY")
        row.operator("coatlink.pull", text="Force re-read", icon="FILE_REFRESH").force = True
        column.operator("coatlink.unlink", text="Unlink selected", icon="UNLINKED")
        # A section like the ones above it: the divider introduces the heading, and
        # only the remesh sub-group is framed, so no section is drawn differently.
        column.separator()
        column.label(text="Status")
        for line in status_lines(bridge.status(context)):
            column.label(text=line or " ")
        column.operator("coatlink.copy_details", text="Copy details", icon="COPYDOWN")


CLASSES = (
    COATLINK_OT_send,
    COATLINK_OT_pull,
    COATLINK_OT_detect,
    COATLINK_OT_open_folder,
    COATLINK_OT_launch,
    COATLINK_OT_unlink,
    COATLINK_OT_copy_details,
    COATLINK_PT_menu,
)


def topbar_drawer(self, context):
    """Draw the top-bar entry: one button, drawn the way the buttons next to it are.

    `row.popover(...)` would paint it with the flat header widget - an outline with no
    fill - so it reads as a different kind of control next to Blender's own buttons.
    An operator gets the normal, filled button, and `wm.call_panel` opens the very same
    panel; `keep_open` keeps it up while you use it, like a popover does.
    """
    if context.region.alignment != "RIGHT":
        return
    row = self.layout.row(align=True)
    button = row.operator("wm.call_panel", text="CoatLink", icon="COLLAPSEMENU")
    button.name = POPOVER_ID
    button.keep_open = True


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
