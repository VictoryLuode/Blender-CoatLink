# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Texture hand-off: hook the maps listed in textures.txt into the materials.

Only the maps that have a direct home on the Principled BSDF are wired up.
Anything else is reported as skipped instead of guessed at.
"""

import os

import bpy

NODE_PREFIX = "CoatBridge"

# usage tag from textures.txt -> what we do with it
USAGE_MAP = {
    "diffuse": "base_color",
    "color": "base_color",
    "albedo": "base_color",
    "normal": "normal",
    "normalmap": "normal",
    "normal_map": "normal",
    "roughness": "roughness",
    "rough": "roughness",
    "metalness": "metal",
    "metallness": "metal",
    "metal": "metal",
    "emissive": "emission",
    "emission": "emission",
}

_SOCKETS = {
    "base_color": "Base Color",
    "roughness": "Roughness",
    "metal": "Metallic",
    "emission": "Emission Color",
}


def apply_maps(material, records, log):
    """Wire every record that maps onto `material` (list of texture records)."""
    applied = 0
    for _name, _secondary, usage, image_path in records:
        kind = USAGE_MAP.get(usage.lower())
        if kind is None:
            log.append("skipped '%s' (no direct socket)" % usage)
            continue
        if not os.path.isfile(image_path):
            log.append("missing file for '%s': %s" % (usage, os.path.basename(image_path)))
            continue
        try:
            _wire(material, kind, image_path)
            applied += 1
        except Exception as exc:  # surfaced, never swallowed
            log.append("failed '%s': %s" % (usage, exc))
    return applied


def resolve_materials(records, scene_objects):
    """Map each texture record to the material it belongs to.

    Fallback chain: material named like the record -> material named like the
    secondary name -> the only material of a matching object.  Unresolved
    records land in the returned list so the caller can say so.
    """
    by_record = {}
    unresolved = []
    for record in records:
        name, secondary = record[0], record[1]
        material = bpy.data.materials.get(name) or bpy.data.materials.get(secondary)
        if material is None:
            for obj in scene_objects:
                if obj.name in (name, secondary) and obj.material_slots:
                    material = obj.material_slots[0].material
                    break
        if material is None:
            unresolved.append(record)
        else:
            by_record.setdefault(material.name, []).append(record)
    return by_record, unresolved


def _wire(material, kind, image_path):
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    principled = _principled(nodes)
    if principled is None:
        raise RuntimeError("material has no Principled BSDF")

    datablock = bpy.data.images.load(image_path, check_existing=True)
    image_node = _reuse(nodes, kind, "TEX_IMAGE")
    if image_node is None:
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.name = "%s %s" % (NODE_PREFIX, kind)
        image_node.label = kind
        image_node.location = (-520, -260 * len([n for n in nodes if n.name.startswith(NODE_PREFIX)]))
    image_node.image = datablock

    if kind == "normal":
        datablock.colorspace_settings.name = "Non-Color"
        bump = _reuse(nodes, "normal_map", "NORMAL_MAP")
        if bump is None:
            bump = nodes.new("ShaderNodeNormalMap")
            bump.name = "%s normal_map" % NODE_PREFIX
            bump.location = (image_node.location.x + 260, image_node.location.y)
        _link(links, image_node.outputs["Color"], bump.inputs["Color"])
        _link(links, bump.outputs["Normal"], principled.inputs["Normal"])
        return

    if kind != "base_color":
        datablock.colorspace_settings.name = "Non-Color"
    _link(links, image_node.outputs["Color"], principled.inputs[_SOCKETS[kind]])


def _principled(nodes):
    return next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)


def _reuse(nodes, suffix, node_type=None):
    name = "%s %s" % (NODE_PREFIX, suffix)
    for node in nodes:
        if node.name == name and (node_type is None or node.type == node_type):
            return node
    return None


def _link(links, from_socket, to_socket):
    for link in list(to_socket.links):
        links.remove(link)
    links.new(from_socket, to_socket)
