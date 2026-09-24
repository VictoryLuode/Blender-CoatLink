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
    bl_label = "Export to 3D-Coat"
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
            bridge._set_message("Export failed: %s" % exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Queued for 3D-Coat: %s" % os.path.basename(path))
        return {"FINISHED"}


class COATLINK_OT_pull(bpy.types.Operator):
    bl_idname = "coatlink.pull"
    bl_label = "Import from 3D-Coat"
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
            bridge._set_message("Import failed: %s" % exc)
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
        # Detecting is the first thing anyone runs, so it must report rather than raise:
        # creating the folder can fail (a read-only Documents, a folder held by a sync
        # client, a path over the Windows limit) and an uncaught error there is a traceback
        # in the middle of the setup.
        try:
            exchange = applink.detect_exchange(p.exchange_folder)
            p.exchange_folder = exchange
            folder = applink.ensure_app_folder(exchange)
        except Exception as exc:
            bridge._set_message("Detect failed: %s" % exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
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

        # The two actions lead, so the panel opens on the thing the add-on is for.  The
        # four sections that follow are the same sections, in the same order, with the
        # same words as the 3D-Coat panel (which opens on its two buttons too) - drawn
        # as fold-out sections the way Blender's own popovers group things: a small
        # header carrying the title, and a body only drawn while the section is open.
        # All but Setup start open: folding is for putting a long tail away, never for
        # hiding something a first run needs.  Inside a section, same-kind switches
        # share a line and anything with longer text keeps a line to itself.
        row = layout.row(align=True)
        row.scale_y = 1.6
        row.operator("coatlink.send", text="Export", icon="EXPORT")
        row.operator("coatlink.pull", text="Import", icon="IMPORT")

        header, body = layout.panel("coatlink_send_options", default_closed=False)
        header.label(text="Export options")
        if body:
            column = body.column(align=True)
            column.prop(p, "scope", text="Export range")
            column.prop(p, "mode", text="Import as")
            column.prop(p, "send_origin", text="Send to origin")
            column.prop(p, "remesh", text="Remesh on send")
            # The box frames the remesh settings themselves - they are one idea, and
            # they grey out as a block while the switch right above them is off.
            box = column.box()
            settings = box.column(align=True)
            settings.enabled = p.remesh     # always drawn, greyed when it does nothing
            settings.prop(p, "remesh_voxel", text="Voxel size (0 = auto)")
            settings.prop(p, "remesh_adaptivity", text="Adaptivity")

        header, body = layout.panel("coatlink_return", default_closed=False)
        header.label(text="Import options")
        if body:
            column = body.column(align=True)
            row = column.row(align=True)
            row.prop(p, "auto_pull", text="Auto receive")
            row.prop(p, "strip_materials", text="Without materials")
            # Two switches to a line: these two are what a return does to the scene, and
            # "Replace in place" is the one of them that can write over a model by name.
            row = column.row(align=True)
            row.prop(p, "replace_in_place", text="Replace in place")
            row.prop(p, "shader_materials", text="Shaders as materials")

        header, body = layout.panel("coatlink_setup", default_closed=True)
        header.label(text="Setup")
        if body:
            column = body.column(align=True)
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

        # The readout stays open: this is where an error stays visible after the toast
        # has gone, so folding it away would fold away the failures too.
        header, body = layout.panel("coatlink_status", default_closed=False)
        header.label(text="Status")
        if body:
            column = body.column(align=True)
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
