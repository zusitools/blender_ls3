# coding=utf-8

#  ***** GPL LICENSE BLOCK *****
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#  All rights reserved.
#  ***** GPL LICENSE BLOCK *****

import logging
from mathutils import Color

logger = logging.getLogger(__name__)


class PrincipledBSDFWrapper:
    def __init__(self, material):
        self.base_color = Color((1, 1, 1))
        self.base_texture_image = None
        self.base_uv_map = None
        self.secondary_texture_image = None
        self.secondary_uv_map = None

        if not material.use_nodes:
            self.base_color = Color(material.diffuse_color[:3])
        elif material.node_tree.nodes:
            node_out = None
            node_principled = None

            # Main output and shader.
            for n in material.node_tree.nodes:
                if n.bl_idname == "ShaderNodeOutputMaterial" and n.inputs[0].is_linked:
                    node_out = n
                    node_principled = n.inputs[0].links[0].from_node
                elif (
                    n.bl_idname == "ShaderNodeBsdfPrincipled" and n.outputs[0].is_linked
                ):
                    node_principled = n
                    for lnk in n.outputs[0].links:
                        node_out = lnk.to_node
                        if node_out.bl_idname == "ShaderNodeOutputMaterial":
                            break
                if (
                    node_out is not None
                    and node_principled is not None
                    and node_out.bl_idname == "ShaderNodeOutputMaterial"
                    and node_principled.bl_idname == "ShaderNodeBsdfPrincipled"
                ):
                    break
                # Could not find a valid pair, let's try again
                node_out = node_principled = None

            if node_principled:
                self.base_color = self.get_color(
                    node_principled.inputs["Base Color"]
                ) or Color((1, 1, 1))
                self.base_texture_image = self.get_texture(
                    node_principled.inputs["Base Color"], 0
                )
                self.base_uv_map = self.get_uv_map(
                    node_principled.inputs["Base Color"], 0
                )
                self.secondary_texture_image = self.get_texture(
                    node_principled.inputs["Base Color"], 1
                )
                self.secondary_uv_map = self.get_uv_map(
                    node_principled.inputs["Base Color"], 1
                )

    def get_color(self, node_input):
        if not node_input.is_linked:
            logger.debug(f"get_color {node_input} -> not linked")
            return Color(node_input.default_value[:3])
        node2 = node_input.links[0].from_node
        logger.debug(f"get_color {node_input} -> {node2.bl_idname}")
        if node2.bl_idname == "ShaderNodeMixRGB":
            result = self.get_color(node2.inputs["Color1"])
            if result:
                return result
            return self.get_color(node2.inputs["Color2"])
        elif node2.bl_idname == "ShaderNodeMix" and node2.data_type == "RGBA":
            result = self.get_color(node2.inputs[6])
            if result:
                return result
            return self.get_color(node2.inputs[6])
        elif node2.bl_idname == "ShaderNodeRGB":
            logger.debug(
                f"get_color: found color {node2.outputs[0].default_value} at {node2}"
            )
            return Color(node2.outputs[0].default_value[:3])
        return None

    def get_texture(self, node_input, index):
        if not node_input.is_linked:
            logger.debug(f"get_texture({index}) {node_input} -> not linked")
            return None
        node2 = node_input.links[0].from_node
        logger.debug(f"get_texture({index}) {node_input} -> {node2.bl_idname}")
        if node2.bl_idname == "ShaderNodeMixRGB":
            if index == 0:
                return self.get_texture(node2.inputs["Color1"], 0)
            elif index == 1:
                return self.get_texture(node2.inputs["Color2"], 0)
        elif node2.bl_idname == "ShaderNodeMix" and node2.data_type == "RGBA":
            if index == 0:
                return self.get_texture(node2.inputs[6], 0)
            elif index == 1:
                return self.get_texture(node2.inputs[7], 0)
        elif node2.bl_idname == "ShaderNodeTexImage" and index == 0:
            logger.debug(f"get_texture({index}): found image {node2.image} at {node2}")
            return node2.image
        return None

    def get_uv_map(self, node_input, index):
        if not node_input.is_linked:
            logger.debug(f"get_uv_map({index}) {node_input} -> not linked")
            return None
        node2 = node_input.links[0].from_node
        logger.debug(f"get_uv_map({index}) {node_input} -> {node2.bl_idname}")
        if node2.bl_idname == "ShaderNodeMixRGB":
            if index == 0:
                return self.get_uv_map(node2.inputs["Color1"], 0)
            elif index == 1:
                return self.get_uv_map(node2.inputs["Color2"], 0)
        elif node2.bl_idname == "ShaderNodeMix" and node2.data_type == "RGBA":
            if index == 0:
                return self.get_uv_map(node2.inputs[6], 0)
            elif index == 1:
                return self.get_uv_map(node2.inputs[7], 0)
        elif node2.bl_idname == "ShaderNodeTexImage":
            logger.debug(f"get_uv_map({index}): found image {node2.image} at {node2}")
            return self.get_uv_map(node2.inputs["Vector"], 0)
        elif node2.bl_idname == "ShaderNodeUVMap":
            logger.debug(f"get_uv_map({index}): found uv map {node2.uv_map} at {node2}")
            return node2.uv_map
        return None
