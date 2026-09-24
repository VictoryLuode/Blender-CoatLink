# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.
# Copyright (C) 2026  VictoryLuode

bl_info = {
    "name": "CoatLink",
    "author": "VictoryLuode",
    "version": (1, 18, 0),
    "blender": (4, 2, 0),
    "location": "Top Bar > CoatLink",
    "description": "Minimal two-way model bridge between Blender and 3D-Coat (AppLink protocol)",
    "category": "Import-Export",
    "doc_url": "https://3dcoat.com/documentation/manual/getting-started/app-links/blender-applink/",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import transfer, ui, watcher

MODE_ITEMS = [
    ("vox", "Sculpt Object (voxel)", "Drop the mesh as a voxel sculpt object"),
    ("autopo", "Auto-Retopology", "Drop the mesh into 3D-Coat for auto-retopology"),
    ("curv", "Curve Profile", "Use the mesh as a curve profile"),
    ("mv", "Microvertex Painting", "Paint the mesh in 3D-Coat (microvertex)"),
    ("alpha", "Pen Alpha", "Use the mesh as a pen alpha"),
    ("ppp", "Per-Pixel Painting", "Paint the mesh in 3D-Coat (per-pixel)"),
    ("ptex", "Ptex Painting", "Paint the mesh in 3D-Coat (Ptex)"),
    ("ref", "Reference Mesh", "Drop the mesh as a reference"),
    ("retopo", "Retopo Mesh", "Drop the mesh as a new retopo layer"),
    ("uv", "UV Mapping", "Unwrap the mesh in 3D-Coat"),
    ("voxcombine", "Voxel Merge", "Merge everything into one voxel volume"),
    ("prim", "Voxel Primitive", "Use the mesh as a merging primitive"),
]


class CoatLinkPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    exchange_folder: StringProperty(
        name="Exchange folder",
        description="Folder 3D-Coat watches for incoming models (Documents/AppLinks/3D-Coat/Exchange)",
        subtype="DIR_PATH",
    )
    mode: EnumProperty(
        name="Import as",
        description="How 3D-Coat should open the model",
        items=MODE_ITEMS,
        default="vox",
    )
    remesh: BoolProperty(
        name="Remesh on send",
        description="Voxel-remesh what is exported; the meshes in the scene are left alone",
        default=True,
    )
    remesh_voxel: FloatProperty(
        name="Voxel size",
        description="Voxel size for that remesh; 0 picks one from the object's size",
        default=0.0,
        min=0.0,
        subtype="DISTANCE",
    )
    remesh_adaptivity: FloatProperty(
        name="Adaptivity",
        description="Let the remesh drop polygons where the surface is flat (0 = off)",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )
    scope: EnumProperty(
        name="Export range",
        description="What Export covers: the selected objects, or every visible object",
        items=[("selected", "Selected objects", "Export the selected objects"),
               ("scene", "Visible objects", "Export every visible object in the scene")],
        default="selected",
    )
    send_origin: BoolProperty(
        name="Send to origin",
        description="Land the model on 3D-Coat's world origin instead of where it sits here: "
                    "the active object's own origin becomes 0,0,0, and the rest of the "
                    "selection keeps its offset from it.  A model that comes back still "
                    "lands where it was sent from",
        default=False,
    )
    auto_pull: BoolProperty(
        name="Auto pull",
        description="Watch the exchange folder and take a returned model automatically",
        default=True,
    )
    skip_dialogs: BoolProperty(
        name="Skip dialogs",
        description="Let 3D-Coat import and export with its current settings instead of asking every time",
        default=True,
    )
    apply_modifiers: BoolProperty(
        name="Apply modifiers",
        description="Export evaluated meshes (modifiers applied)",
        default=False,
    )
    coat_scale: FloatProperty(
        name="3D-Coat scale",
        description="Multiply the model on the way to 3D-Coat.  0 = use the scene scale 3D-Coat reports",
        default=0.0,
        min=0.0,
    )
    axis_mode: EnumProperty(
        name="Axis",
        description="Axis convention for the model going out and coming back (OBJ carries no axis of its own, so this one rule covers both directions)",
        items=[
            ("auto", "Auto (match 3D-Coat)", "Follow 3D-Coat's own swap Y/Z setting"),
            ("normal", "Normal (Y up)", "Blender's own convention"),
            ("swap", "Swap Y/Z", "Z-up convention"),
        ],
        default="auto",
    )
    strip_materials: BoolProperty(
        name="Import without materials",
        description="Drop the materials of a returned model, so only the geometry comes back",
        default=False,
    )
    replace_in_place: BoolProperty(
        name="Replace in place",
        description="A returned model takes the place of the object the send came from - "
                    "same name, same materials, same place in the outliner, new geometry.  "
                    "Off, it arrives as an object of its own and nothing already in the "
                    "scene is touched",
        default=True,
    )
    match_scale: BoolProperty(
        name="Match scale on pull",
        description="Measure the returned model against the sent one and undo a unit mismatch (3D-Coat scene units are not always metres)",
        default=True,
    )
    shader_materials: BoolProperty(
        name="Shaders as materials",
        description="Give every returned object a material named after the 3D-Coat shader it "
                    "was sent with - one material per shader, so the shader-to-object "
                    "assignment does not have to be rebuilt by hand.  The values come from the "
                    "shader preset itself; the look cannot be copied, a sculpt shader is "
                    "3D-Coat's own display shading",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "exchange_folder")
        layout.label(text="Other settings are in the top-bar CoatLink menu.", icon="INFO")


def register():
    bpy.utils.register_class(CoatLinkPreferences)
    ui.register()
    bpy.types.Object.coatlink_file = StringProperty(
        name="CoatLink file",
        description="Model file this object is linked to, used to update it in place",
        default="",
    )
    bpy.types.Scene.coatlink_status = StringProperty(
        name="CoatLink status",
        default="Ready",
    )
    watcher.start()


def unregister():
    watcher.stop()
    del bpy.types.Object.coatlink_file
    del bpy.types.Scene.coatlink_status
    ui.unregister()
    bpy.utils.unregister_class(CoatLinkPreferences)
