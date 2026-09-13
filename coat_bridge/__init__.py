# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.
# Copyright (C) 2026  VictoryLuode

bl_info = {
    "name": "Coat Bridge",
    "author": "VictoryLuode",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > 3D-Coat",
    "description": "Minimal two-way model bridge between Blender and 3D-Coat (AppLink protocol)",
    "category": "Import-Export",
    "doc_url": "https://3dcoat.com/documentation/manual/getting-started/app-links/blender-applink/",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

from . import transfer, ui, watcher

MODE_ITEMS = [
    ("autopo", "Auto-Retopology", "Drop the mesh into 3D-Coat for auto-retopology"),
    ("curv", "Curve Profile", "Use the mesh as a curve profile"),
    ("mv", "Microvertex Painting", "Paint the mesh in 3D-Coat (microvertex)"),
    ("alpha", "Pen Alpha", "Use the mesh as a pen alpha"),
    ("ppp", "Per-Pixel Painting", "Paint the mesh in 3D-Coat (per-pixel)"),
    ("ptex", "Ptex Painting", "Paint the mesh in 3D-Coat (Ptex)"),
    ("ref", "Reference Mesh", "Drop the mesh as a reference"),
    ("retopo", "Retopo Mesh", "Drop the mesh as a new retopo layer"),
    ("vox", "Sculpt Object (voxel)", "Drop the mesh as a voxel sculpt object"),
    ("uv", "UV Mapping", "Unwrap the mesh in 3D-Coat"),
    ("voxcombine", "Voxel Merge", "Merge everything into one voxel volume"),
    ("prim", "Voxel Primitive", "Use the mesh as a merging primitive"),
]


class CoatBridgePreferences(bpy.types.AddonPreferences):
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
        default="ppp",
    )
    fmt: EnumProperty(
        name="Format",
        description="File format used for the round trip",
        items=transfer.format_items(),
        default="obj",
    )
    preset: StringProperty(
        name="Export preset",
        description="3D-Coat export preset used when the model comes back",
        default="Blender Cycles",
    )
    skip_import: BoolProperty(
        name="Skip import dialog",
        description="Let 3D-Coat load the model with the settings above instead of asking",
        default=True,
    )
    skip_export: BoolProperty(
        name="Skip export dialog",
        description="Let 3D-Coat send the model back with the last export settings instead of asking",
        default=True,
    )
    apply_modifiers: BoolProperty(
        name="Apply modifiers",
        description="Export evaluated meshes (modifiers applied)",
        default=False,
    )
    apply_textures: BoolProperty(
        name="Apply textures on pull",
        description="Wire the maps listed in textures.txt into the materials after a pull",
        default=False,
    )
    auto_pull: BoolProperty(
        name="Auto pull",
        description="Watch the exchange folder and take a returned model automatically",
        default=True,
    )
    interval: FloatProperty(
        name="Interval",
        description="Seconds between two checks of the exchange folder",
        default=2.0,
        min=0.5,
        max=30.0,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "exchange_folder")
        layout.label(text="The panel in the 3D view sidebar has the rest.", icon="INFO")


def register():
    bpy.utils.register_class(CoatBridgePreferences)
    ui.register()
    bpy.types.Object.coat_bridge_file = StringProperty(
        name="Coat Bridge file",
        description="Model file this object is linked to, used to update it in place",
        default="",
    )
    bpy.types.Scene.coat_bridge_status = StringProperty(
        name="Coat Bridge status",
        default="Ready",
    )
    watcher.start()


def unregister():
    watcher.stop()
    del bpy.types.Object.coat_bridge_file
    del bpy.types.Scene.coat_bridge_status
    ui.unregister()
    bpy.utils.unregister_class(CoatBridgePreferences)
