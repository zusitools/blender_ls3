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
 
import bpy
import mathutils
import os
from . import i18n
from .zusicommon import zusicommon
from math import pi

_ = i18n.language.gettext

# This file defines Zusi specific custom properties and the corresponding UI.

# Functions for file paths that are stored internally as paths relative to the
# Zusi data directory (indicated by a "zusi2:"/"zusi3:" prefix) or as a regular path
def zusi_file_path_to_blender_path(zusi_path):
    if zusi_path.startswith("zusi2:"):
        return os.path.normpath(os.path.join(zusicommon.get_zusi2_data_path(),
            zusi_path[len("zusi2:"):].replace('\\', os.path.sep)))
    elif zusi_path.startswith("zusi3:"):
        result = os.path.normpath(os.path.join(zusicommon.get_zusi_data_path(),
            zusi_path[len("zusi3:"):].replace('\\', os.path.sep)))
        if os.path.exists(result):
            return result
        else:
            return os.path.normpath(os.path.join(zusicommon.get_zusi_data_path_official(),
                zusi_path[len("zusi3:"):].replace('\\', os.path.sep)))
    return zusi_path

def zusi_file_path_to_display_path(zusi_path):
    if zusi_path.startswith("zusi2:"):
        return zusi_path[len("zusi2:"):]
    elif zusi_path.startswith("zusi3:"):
        return zusi_path[len("zusi3:"):]
    return zusi_path

def blender_path_to_zusi_file_path(blender_path):
    path = os.path.realpath(bpy.path.abspath(blender_path))
    (dirname, filename) = os.path.split(path)
    # KNOWN ISSUE: https://developer.blender.org/T44137
    # In Blender <= 2.73, bpy.path.is_subdir will wrongly return True for some paths, e.g.
    # bpy.path.is_subdir("/mnt/Zusi3/DatenOffiziell/Loks/Elektroloks", "/mnt/Zusi3/Daten/") == True
    # Just ignore the issue and hope people will either use the latest version of Blender
    # or have their paths configured differently.
    if bpy.path.is_subdir(dirname, zusicommon.get_zusi_data_path()):
        return "zusi3:" + os.path.relpath(path, zusicommon.get_zusi_data_path()).replace(os.path.sep, '\\')
    if bpy.path.is_subdir(dirname, zusicommon.get_zusi_data_path_official()):
        return "zusi3:" + os.path.relpath(path, zusicommon.get_zusi_data_path_official()).replace(os.path.sep, '\\')
    if bpy.path.is_subdir(dirname, zusicommon.get_zusi2_data_path()):
        return "zusi2:" + os.path.relpath(path, zusicommon.get_zusi2_data_path()).replace(os.path.sep, '\\')
    return blender_path

class CheckBoxList():
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        icon = "CHECKBOX_HLT" if self.get_property_value(item) else "CHECKBOX_DEHLT"
        layout.prop(item, self.get_property_name(), text = "", icon = icon, toggle = True, icon_only = True, emboss = False)
        layout.label(self.get_item_text(item))

# Defines a variant in a scene with an ID (which should not be changed) and a variant name
# (Name is defined in PropertyGroup)
class ZusiFileVariant(bpy.types.PropertyGroup):
    id = bpy.props.IntProperty(
        name = _("ID"),
        description = _("Unique ID of this variant"),
    )

bpy.utils.register_class(ZusiFileVariant)

animation_types = [
    ("0", _("Undefined/signal controlled"), ""),
    ("1", _("Continuous over time"), ""),
    ("2", _("Speed (powered, braked)"), ""),
    ("3", _("Speed (braked)"), ""),
    ("4", _("Speed (powered)"), ""),
    ("5", _("Speed"), ""),
    ("6", _("Track curvature at front of vehicle"), ""),
    ("7", _("Track curvature at rear of vehicle"), ""),
    ("8", _("Pantograph A"), ""),
    ("9", _("Pantograph B"), ""),
    ("10", _("Pantograph C"), ""),
    ("11", _("Pantograph D"), ""),
    ("12", _("Doors left"), ""),
    ("13", _("Doors right"), ""),
    ("14", _("Tilt technology"), ""),
]

class ZusiLinkAnimation(bpy.types.PropertyGroup):
    animation_type = bpy.props.EnumProperty(
        name = _("Animation type"),
        description = _("Defines how the animation is triggered in the simulator"),
        items = animation_types,
        default = "0"
    )

    description = bpy.props.StringProperty(
        name = _("Name"),
        description = _("Animation name; leave empty for default"),
    )

bpy.utils.register_class(ZusiLinkAnimation)

class ZusiLinkAnimationList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "animation_type", text="", icon_value=icon)
        layout.prop(item, "description", text="", icon_value=icon)

class ZusiAnimationName(bpy.types.PropertyGroup):
    name = bpy.props.StringProperty(
        name = _("Name"),
        description = _("Animation name")
    )

bpy.utils.register_class(ZusiAnimationName)

class ZusiFileVariantList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if bpy.app.version >= (2, 70, 0):
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        else:
            layout.label(item.name, icon_value=icon)

# Defines a visibility of an object/material/texture/whatever in a certain variant
class ZusiFileVariantVisibility(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = _("Variant ID"),
        description = _("ID of the variant this object is visible in")
    )

bpy.utils.register_class(ZusiFileVariantVisibility)

class ZusiFileVariantVisibilityList(CheckBoxList, bpy.types.UIList):

    def get_property_name(self):
        return "visible"
    
    def get_property_value(self, item):
        return item.visible
    
    def get_item_text(self, item):
        return str(item.name)

licenses = [
    ("0", _("Default license (add-on pool, revenue goes to author)"), ""),
    ("1", _("Add-on pool, revenue goes to the add-on pool"), ""),
    ("2", _("Add-on pool, revenue goes to Carsten Hölscher Software"), ""),
    ("3", _("Add-on pool, no effort points, released for all types of use"), ""),
    ("4", _("Private file, not intended to be distributed"), ""),
    ("5", _("Special commercial usage"), ""),
]

# Contains information about a file's author
class ZusiAuthor(bpy.types.PropertyGroup):
    id = bpy.props.IntProperty(
        name = _("ID"),
        description = _("The ID of the author"),
        min = 0
    )

    name = bpy.props.StringProperty(
        name = _("Name"),
        description = _("The name of the author"),
        default = ""
    )

    email = bpy.props.StringProperty(
        name = _("E-mail"),
        description = _("The e-mail address of the author"),
        default = ""
    )

    effort = bpy.props.FloatProperty(
        name = _("Effort (legacy)"),
        description = _("The author's construction effort in units of one house. Use the \"Effort (h)\" property instead."),
        min = 0,
        default = 0.0
    )

    effort_hours = bpy.props.FloatProperty(
        name = _("Effort (h)"),
        description = _("The author's construction effort in hours"),
        min = 0,
        default = 0.0
    )

    remarks = bpy.props.StringProperty(
        name = _("Remarks"),
        description = _("Remarks about the author"),
        default = ""
    )

    license = bpy.props.EnumProperty(
        name = _("License"),
        description = _("The license under which the author has published this object"),
        items = licenses,
        default = "0"
    )


bpy.utils.register_class(ZusiAuthor)

class ZusiAuthorList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if bpy.app.version >= (2, 70, 0):
            layout.prop(item, "name", text="", emboss=False, icon_value=icon)
        else:
            layout.label(item.name, icon_value=icon)

class ZusiAnchorPointFile(bpy.types.PropertyGroup):
    def set_name(self, value):
        self.name = blender_path_to_zusi_file_path(value)

    name_realpath = bpy.props.StringProperty(
        name = _("File or folder name"),
        subtype = "FILE_PATH",
        get = lambda self: zusi_file_path_to_blender_path(self.name),
        set = set_name,
    )

bpy.utils.register_class(ZusiAnchorPointFile)

class ZusiAnchorPointFileList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if os.path.exists(item.name_realpath):
            layout.label(zusi_file_path_to_display_path(item.name), icon = 'FILE_FOLDER' if os.path.isdir(item.name_realpath) else 'FILE')
        else:
            layout.label(item.name_realpath, icon = 'ERROR')

# Custom texture preset properties

d3d_texture_filters = [
    ("0", "D3DTEXF_NONE", ""),
    ("1", "D3DTEXF_POINT", ""),
    ("2", "D3DTEXF_LINEAR", ""),
    ("3", "D3DTEXF_ANISOTROPHIC", ""),
    ("6", "D3DTEXF_PYRAMIDALQUAD", ""),
    ("7", "D3DTEXF_GAUSSIANQUAD", ""),
]

d3d_texture_ops = [
    ("1", "D3DTOP_DISABLE", ""),
    ("2", "D3DTOP_SELECTARG1", ""),
    ("3", "D3DTOP_SELECTARG2", ""),
    ("4", "D3DTOP_MODULATE", ""),
    ("5", "D3DTOP_MODULATE2X", ""),
    ("6", "D3DTOP_MODULATE4X", ""),
    ("7", "D3DTOP_ADD", ""),
    ("8", "D3DTOP_ADDSIGNED", ""),
    ("9", "D3DTOP_ADDSIGNED2X", ""),
    ("10", "D3DTOP_SUBTRACT", ""),
    ("11", "D3DTOP_ADDSMOOTH", ""),
    ("12", "D3DTOP_BLENDDIFFUSEALPHA", ""),
    ("13", "D3DTOP_BLENDTEXTUREALPHA", ""),
    ("14", "D3DTOP_BLENDFACTORALPHA", ""),
    ("15", "D3DTOP_BLENDTEXTUREALPHAPM", ""),
    ("16", "D3DTOP_BLENDCURRENTALPHA", ""),
    ("17", "D3DTOP_PREMODULATE", ""),
    ("18", "D3DTOP_MODULATEALPHA_ADDCOLOR", ""),
    ("19", "D3DTOP_MODULATECOLOR_ADDALPHA", ""),
    ("20", "D3DTOP_MODULATEINVALPHA_ADDCOLOR", ""),
    ("21", "D3DTOP_MODULATEINVCOLOR_ADDALPHA", ""),
    ("22", "D3DTOP_BUMPENVMAP", ""),
    ("23", "D3DTOP_BUMPENVMAPLUMINANCE", ""),
    ("24", "D3DTOP_DOTPRODUCT3", ""),
    ("25", "D3DTOP_MULTIPLYADD", ""),
    ("26", "D3DTOP_LERP", ""),
]

d3d_texture_args = [
    ("0", "D3DTA_DIFFUSE", ""),
    ("1", "D3DTA_CURRENT", ""),
    ("2", "D3DTA_TEXTURE", ""),
    ("3", "D3DTA_TFACTOR", ""),
    ("4", "D3DTA_SPECULAR", ""),
    ("5", "D3DTA_TEMP", ""),
    ("6", "D3DTA_CONSTANT", ""),
]

d3d_blend_params = [
    ("1", "D3DBLEND_ZERO", ""),
    ("2", "D3DBLEND_ONE", ""),
    ("3", "D3DBLEND_SRCCOLOR", ""),
    ("4", "D3DBLEND_INVSRCCOLOR", ""),
    ("5", "D3DBLEND_SRCALPHA", ""),
    ("6", "D3DBLEND_INVSRCALPHA", ""),
    ("7", "D3DBLEND_DESTALPHA", ""),
    ("8", "D3DBLEND_INVDESTALPHA", ""),
    ("9", "D3DBLEND_DESTCOLOR", ""),
    ("10", "D3DBLEND_INVDESTCOLOR", ""),
    ("11", "D3DBLEND_SRCALPHASAT", ""),
    ("12", "D3DBLEND_BOTHSRCALPHA", ""),
    ("13", "D3DBLEND_BOTHINVSRCALPHA", ""),
    ("14", "D3DBLEND_BLENDFACTOR", ""),
    ("15", "D3DBLEND_INVBLENDFACTOR", ""),
]

d3d_shademodes = [
    ("0", "D3DSHADE_FLAT", ""), # TODO
    ("2", "D3DSHADE_GOURAUD", ""),
    ("3", "D3DSHADE_PHONG", ""),
]

# Settings for one texture stage in a custom texture preset
class ZusiTexturePresetTextureStageSettings(bpy.types.PropertyGroup):
    D3DSAMP_MINFILTER = bpy.props.EnumProperty(
        name = "D3DSAMP_MINFILTER",
        description = _("Value for D3DSAMP_MINFILTER"),
        items = d3d_texture_filters,
    )
    
    D3DSAMP_MAGFILTER = bpy.props.EnumProperty(
        name = "D3DSAMP_MAGFILTER",
        description = _("Value for D3DSAMP_MAGFILTER"),
        items = d3d_texture_filters,
    )
    
    D3DTSS_COLOROP = bpy.props.EnumProperty(
        name = "D3DTSS_COLOROP",
        description = _("Value for D3DTSS_COLOROP"),
        items = d3d_texture_ops,
    )
    
    D3DTSS_COLORARG1 = bpy.props.EnumProperty(
        name = "D3DTSS_COLORARG1",
        description = _("Value for D3DTSS_COLORARG1"),
        items = d3d_texture_args,
    )
    
    D3DTSS_COLORARG2 = bpy.props.EnumProperty(
        name = "D3DTSS_COLORARG2",
        description = _("Value for D3DTSS_COLORARG2"),
        items = d3d_texture_args,
    )
    
    D3DTSS_COLORARG0 = bpy.props.EnumProperty(
        name = "D3DTSS_COLORARG2",
        description = _("Value for D3DTSS_COLORARG0"),
        items = d3d_texture_args,
    )
    
    D3DSAMP_ALPHAOP = bpy.props.EnumProperty(
        name = "D3DSAMP_ALPHAOP",
        description = _("Value for D3DSAMP_ALPHAOP"),
        items = d3d_texture_ops,
    )
    
    D3DTSS_ALPHAARG1 = bpy.props.EnumProperty(
        name = "D3DTSS_ALPHAARG1",
        description = _("Value for D3DTSS_ALPHAARG1"),
        items = d3d_texture_args,
    )
    
    D3DTSS_ALPHAARG2 = bpy.props.EnumProperty(
        name = "D3DTSS_ALPHAARG2",
        description = _("Value for D3DTSS_ALPHAARG2"),
        items = d3d_texture_args,
    )
    
    D3DTSS_ALPHAARG0 = bpy.props.EnumProperty(
        name = "D3DTSS_ALPHAARG0",
        description = _("Value for D3DTSS_ALPHAARG0"),
        items = d3d_texture_args,
    )
    
    D3DTSS_RESULTARG = bpy.props.EnumProperty(
        name = "D3DTSS_RESULTARG",
        description = _("Value for D3DTSS_RESULTARG"),
        items = d3d_texture_args,
    )

bpy.utils.register_class(ZusiTexturePresetTextureStageSettings)

class ZusiTexturePresetResultStageSettings(bpy.types.PropertyGroup):
    D3DRS_DESTBLEND = bpy.props.EnumProperty(
        name = "D3DRS_DESTBLEND",
        description = _("Value for D3DRS_DESTBLEND"),
        items = d3d_blend_params,
    )

    D3DRS_SRCBLEND = bpy.props.EnumProperty(
        name = "D3DRS_SRCBLEND",
        description = _("Value for D3DRS_SRCBLEND"),
        items = d3d_blend_params,
    )
    
    D3DRS_ALPHABLENDENABLE = bpy.props.BoolProperty(
        name = "D3DRS_ALPHABLENDENABLE",
        description = _("Value for D3DRS_ALPHABLENDENABLE"),
    )
    
    D3DRS_ALPHATESTENABLE = bpy.props.BoolProperty(
        name = "D3DRS_ALPHATESTENABLE",
        description = _("Value for D3DRS_ALPHATESTENABLE"),
    )
    
    alpha_ref = bpy.props.IntProperty(
        name = _("Alpha REF value"),
        min = 0,
        max = 255,
    )
    
    D3DRS_SHADEMODE = bpy.props.EnumProperty(
        name = "D3DRS_SHADEMODE",
        description = "D3DRS_SHADEMODE",
        items = d3d_shademodes,
    )

bpy.utils.register_class(ZusiTexturePresetResultStageSettings)

def on_zusi_texture_preset_update(self, context):
    # TODO call this when initializing the object
    if not hasattr(context, 'object') or context.object is None:
        return

    mat = context.object.data.materials[context.object.active_material_index]
    mat.zusi_second_pass = False
    newpreset = mat.zusi_texture_preset
    
    if newpreset == 0:
        return
    
    # Texture stage 1
    mat.texture_stage_1.D3DSAMP_MINFILTER = "3" # D3DTEXF_ANISOTROPHIC
    mat.texture_stage_1.D3DSAMP_MAGFILTER = "3" # D3DTEXF_ANISOTROPHIC
    mat.texture_stage_1.D3DTSS_COLOROP = "4" # D3DTOP_MODULATE
    mat.texture_stage_1.D3DTSS_COLORARG1 = "2" # D3DTA_TEXTURE
    mat.texture_stage_1.D3DTSS_COLORARG2 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_1.D3DTSS_COLORARG0 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_1.D3DTSS_ALPHAOP = "2" # D3DTOP_SELECTARG1
    mat.texture_stage_1.D3DTSS_ALPHAARG1 = "2" # D3DTA_TEXTURE
    mat.texture_stage_1.D3DTSS_ALPHAARG2 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_1.D3DTSS_ALPHAARG0 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_1.D3DTSS_RESULTARG = "1" # D3DTA_CURRENT
    
    # Texture stage 2
    mat.texture_stage_2.D3DSAMP_MINFILTER = "0" # D3DTEXF_NONE
    mat.texture_stage_2.D3DSAMP_MAGFILTER = "0" # D3DTEXF_NONE
    mat.texture_stage_2.D3DTSS_COLOROP = "1" # D3DTOP_DISABLE
    mat.texture_stage_2.D3DTSS_COLORARG1 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_COLORARG2 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_COLORARG0 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_ALPHAOP = "1" # D3DTOP_DISABLE
    mat.texture_stage_2.D3DTSS_ALPHAARG1 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_ALPHAARG2 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_ALPHAARG0 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_2.D3DTSS_RESULTARG = "1" # D3DTA_CURRENT
    
    # Texture stage 3
    mat.texture_stage_3.D3DTSS_COLOROP = "1" # D3DTOP_DISABLE
    mat.texture_stage_3.D3DTSS_COLORARG1 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_3.D3DTSS_COLORARG2 = "0" # D3DTA_DIFFUSE
    mat.texture_stage_3.D3DTSS_ALPHAOP = "1" # D3DTOP_DISABLE
    mat.texture_stage_3.D3DTSS_RESULTARG = "0" # D3DTA_CONSTANT
    
    # Result stage
    mat.result_stage.D3DRS_SRCBLEND = "5" # D3DBLEND_SRCALPHA
    mat.result_stage.D3DRS_DESTBLEND = "6" # D3DBLEND_INVSRCALPHA
    mat.result_stage.D3DRS_ALPHABLENDENABLE = newpreset in [4, 6, 7, 8, 9, 12]
    mat.result_stage.D3DRS_ALPHATESTENABLE = newpreset not in [1, 3]
    mat.result_stage.alpha_ref = 1
    mat.result_stage.D3DRS_SHADEMODE = "2" # D3DSHADE_GOURAUD
    
    if newpreset == 3:
        mat.texture_stage_1.D3DTSS_RESULTARG = "5" # D3DTA_TEMP
        mat.texture_stage_2.D3DTSS_COLOROP = "4" # D3DTOP_MODULATE
        mat.texture_stage_2.D3DTSS_ALPHAOP = "2" # D3DTOP_SELECTARG1
        mat.texture_stage_2.D3DTSS_ALPHAARG1 = "2" # D3DTA_TEXTURE
        mat.texture_stage_3.D3DTSS_COLOROP = "16" # D3DTOP_BLENDCURRENTALPHA
        mat.texture_stage_3.D3DTSS_COLORARG1 = "1" # D3DTA_CURRENT
        mat.texture_stage_3.D3DTSS_COLORARG2 = "5" # D3DTA_TEMP
    
    if newpreset == 5:
        mat.texture_stage_2.D3DTSS_COLOROP = "13" # D3DTOP_BLENDTEXTUREALPHA
        mat.result_stage.D3DRS_SRCBLEND = "1" # D3DBLEND_ZERO
        mat.result_stage.D3DRS_DESTBLEND = "1" # D3DBLEND_ZERO
    
    if newpreset == 6:
        mat.texture_stage_1.D3DTSS_ALPHAOP = "14" # D3DTOP_BLENDFACTORALPHA
        mat.result_stage.D3DRS_SRCBLEND = "6" # D3DBLEND_INVSRCALPHA
        mat.result_stage.D3DRS_DESTBLEND = "3" # D3DBLEND_SRCCOLOR
    
    if newpreset in [8, 12]:
        mat.texture_stage_1.D3DTSS_ALPHAOP = "4" # D3DTOP_MODULATE

    if newpreset == 8:
        mat.result_stage.alpha_ref = 100
    elif newpreset == 12:
        mat.result_stage.alpha_ref = 150
    
    if newpreset in [3, 5]:
        mat.texture_stage_2.D3DTSS_COLORARG1 = "2" # D3DTA_TEXTURE
        mat.texture_stage_2.D3DSAMP_MINFILTER = "3" # D3DTEXF_ANISOTROPHIC
        mat.texture_stage_2.D3DSAMP_MAGFILTER = "3" # D3DTEXF_ANISOTROPHIC
    
    if newpreset in [1, 3]:
        mat.texture_stage_1.D3DTSS_ALPHAARG2 = "0" # D3DTA_DIFFUSE
        mat.texture_stage_1.D3DTSS_ALPHAOP = "1" # D3DTOP_DISABLE
        mat.result_stage.D3DRS_SRCBLEND = "1" # D3DBLEND_ZERO
        mat.result_stage.D3DRS_DESTBLEND = "1" # D3DBLEND_ZERO
        mat.result_stage.alpha_ref = 0
    
    if newpreset in [7, 9]:
        mat.texture_stage_1.D3DTSS_ALPHAARG2 = "3" # D3DTA_TFACTOR


# Conversion animation speed <=> wheel diameter for wheel animations
def get_zusi_animation_wheel_diameter(self):
    if self.zusi_animation_speed == 0:
        return 0
    return 1 / (self.zusi_animation_speed * pi)

def set_zusi_animation_wheel_diameter(self, diameter):
    self.zusi_animation_speed = 0 if diameter == 0 else 1 / (diameter * pi)

# Conversion animation speed <=> animation duration for door animations
def get_zusi_animation_duration(self):
    return 0 if self.zusi_animation_speed == 0 else 1 / self.zusi_animation_speed

def set_zusi_animation_duration(self, duration):
    self.zusi_animation_speed = 0 if duration == 0 else 1 / duration

# Unified wrapper for template lists both in Blender <= 2.65 and above.
def template_list(layout, listtype_name, list_id, dataptr, propname, active_dataptr, active_propname,
        add_operator_name = "", remove_operator_name = "", move_operator_name = "", rows = 5):
    layout.template_list(listtype_name, list_id, dataptr, propname, active_dataptr, active_propname, rows = rows)

    if add_operator_name or remove_operator_name or move_operator_name:
        col = layout.column(align = True)
        if add_operator_name:
            col.operator(add_operator_name, icon = "ZOOMIN", text = "")
        if remove_operator_name:
            col.operator(remove_operator_name, icon = "ZOOMOUT", text = "")

        if move_operator_name:
            col.separator()
            col.operator(move_operator_name, icon = "TRIA_UP", text = "").move_up = True
            col.operator(move_operator_name, icon = "TRIA_DOWN", text = "").move_up = False

# ---
# Custom properties
# ---

scenery_types = [
    ("0", _("Unspecified"), ""),
    ("1", _("Base plane"), ""),
    ("2", _("Embankment"), ""),
    ("3", _("Retaining wall"), ""),
    ("4", _("Track bed"), ""),
    ("5", _("Shoulder"), ""),
    ("6", _("Cess"), ""),
    ("7", _("Six foot"), ""),
    ("8", _("Rail"), ""),
    ("9", _("Guard rail"), ""),
    ("10", _("Platform"), ""),
    ("11", _("Road"), ""),
    ("12", _("Water"), ""),
    ("13", _("Tunnel"), ""),
    ("14", _("Overhead line equipment"), ""),
    ("15", _("Forest"), ""),
    ("16", _("Dummy (invisible in the simulator)"), ""),
    ("17", _("Head light front"), ""),
    ("18", _("Tail light front"), ""),
    ("19", _("Head light rear"), ""),
    ("20", _("Tail light rear"), ""),
    ("21", _("Rail 2D"), ""),
    ("22", _("Guard rail 2D"), ""),
]

gf_types = [
    ("0", _("Ignore"), ""),
    ("1", _("Default"), ""),
    ("2", _("Tunnel"), ""),
    ("3", _("Permanent way"), ""),
    ("4", _("Forest edge"), ""),
    ("5", _("Forest plane, generated by Terrain Former"), ""),
    ("6", _("Base plane, generated by Terrain Former"), ""),
    ("7", _("Background, generated by Terrain Former"), ""),
]

texture_presets = [
    ("0", _("Custom"), ""),
    ("1", _("Default, one texture"), ""),
    ("2", _("Default, one texture, full transparency"), ""),
    ("3", _("Tex. 1 default, tex. 2 transparent"), ""),
    ("4", _("Default, one texture, semi-transparency"), ""),
    ("5", _("Tex. 1 default, tex. 2 transp./illuminated"), ""),
    ("6", _("Signal lens (shine-through)"), ""),
    ("7", _("Dimmable signal lamp (with semi-transparency)"), ""),
    ("8", _("Semi-transparency for leaf-like structures, Alpha reference value 100"), ""),
    ("9", _("Overlaying window, dimming off at day"), ""),
    ("10", _("Overlaying window, switched off at day"), ""),
    ("11", _("Wall of fog"), ""),
    ("12", _("Semi-transparency for leaf-like structures, Alpha reference value 150"), ""),
    ("13", _("Overlaying window, switched off at night"), ""),
]

variant_visibility_modes = [
    ("None", _("Visible in all variants"), ""),
    ("True", _("Visible only in the selected variants"), ""),
    ("False", _("Visible in all but the selected variants"), ""),
]

anchor_point_categories = [
    ("0", _("General"), ""),
    ("1", _("Overhead line equipment"), ""),
    ("2", _("Marker flags"), ""),
    ("3", _("Invisible"), ""),
]

anchor_point_types = [
    ("0", _("General"), ""),
    ("1", _("Contact wire"), ""),
    ("2", _("Catenary wire"), ""),
    ("3", _("Attachment point of stitch wire"), ""),
    ("4", _("Lower cross span wire"), ""),
    ("5", _("Upper cross span wire"), ""),
    ("6", _("Headspan wire"), ""),
    ("7", _("Out-of-running contact wire"), ""),
    ("8", _("Out-of-running catenary wire"), ""),
    ("9", _("Anchor wire for contact wire"), ""),
    ("10", _("Anchor wire for catenary wire"), ""),
    ("11", _("Balance weight anchor attachment pointer"), ""),
    ("12", _("Cantilever attachment point"), ""),
    ("13", _("Mid point anchor attachment point"), ""),
    ("14", _("Hectometer board attachment point"), ""),
    ("15", _("Feeder line attachment point"), ""),
    ("16", _("Control wire attachment point"), ""),
    ("17", _("Telegraph line attachment point"), ""),
    ("18", _("Power supply line attachment point"), ""),
    ("19", _("Signal"), ""),
    ("20", _("Catenary wire swivel clamp attachment point"), ""),
    ("21", _("Registration tube dropper attachment point"), ""),
    ("22", _("Position of load"), ""),
    ("23", _("View point position"), ""),
    ("24", _("Auxiliary catenary wire"), ""),
]

#
# Mesh
#

bpy.types.Mesh.zusi_is_rail = bpy.props.BoolProperty(
    name = _("Calculate normals for rail"),
    description = _("Make the normals always point upwards, for use in rail depictions"),
    default = False
)

#
# Material
#

bpy.types.Material.zusi_emit_color = bpy.props.FloatVectorProperty(
    name = _("Night color"),
    description = _("The night color aka emissive color of the material"),
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.0, 0.0, 0.0)
)

bpy.types.Material.zusi_use_emit = bpy.props.BoolProperty(
    name = _("Use night color"),
    description = _("Use a specific night color for this material"),
    default = False
)

bpy.types.Material.zusi_allow_overexposure = bpy.props.BoolProperty(
    name = _("Allow overexposure"),
    description = _("Allow the day color for this material to be overexposed"),
    default = False
)

bpy.types.Material.zusi_overexposure_addition = bpy.props.FloatVectorProperty(
    name = _('Overexposure addition (Diffuse)'),
    description = _('Color to add to the diffuse day color in order to create overexposure'),
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.0, 0.0, 0.0)
)

bpy.types.Material.zusi_overexposure_addition_ambient = bpy.props.FloatVectorProperty(
    name = _('Overexposure addition (Ambient)'),
    description = _('Color to add to the ambient day color in order to create overexposure'),
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.0, 0.0, 0.0)
)

bpy.types.Material.zusi_ambient_color = bpy.props.FloatVectorProperty(
    name = _("Ambient color"),
    description = _("The ambient color of the material"),
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.8, 0.8, 0.8)
)

bpy.types.Material.zusi_ambient_alpha = bpy.props.FloatProperty(
    name = _("Ambient color alpha"),
    description = _("The alpha value of the ambient color"),
    precision = 3,
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = 1.0
)

bpy.types.Material.zusi_use_ambient = bpy.props.BoolProperty(
    name = _("Use ambient color"),
    description = _("Use a specific ambient color for this material"),
    default = False
)

bpy.types.Material.zusi_texture_preset = bpy.props.EnumProperty(
    name = _("Texture preset"),
    description = _("The texture preset to assign to this material"),
    items = texture_presets,
    default = "1",
    update = on_zusi_texture_preset_update,
)

bpy.types.Material.zusi_day_mode_preset = bpy.props.EnumProperty(
    name = _("Day mode preset"),
    description = _("The texture preset to use when the environment brightness is greater than \"Night switch threshold\""),
    items = [(t if t[0] != "0" else (t[0], "-", t[2])) for t in texture_presets],
    default = "1",
)

# This cannot be renamed to zusi_scenery_type because of existing files.
bpy.types.Material.zusi_landscape_type = bpy.props.EnumProperty(
    name = _("Scenery type"),
    description = _("The scenery type to assign to this subset"),
    items = scenery_types,
    default = "0"
)

bpy.types.Material.zusi_gf_type = bpy.props.EnumProperty(
    name = _("TF type"),
    description = _("The Terrain Former type to assign to this subset"),
    items = gf_types,
    default = "0"
)

bpy.types.Material.zusi_force_brightness = bpy.props.FloatProperty(
    name = _("Force brightness"),
    description = _("Force this material to have a specific brightness"),
    min = -1.0,
    max = 1.0,
    default = 0.0
)

bpy.types.Material.zusi_signal_magnification = bpy.props.FloatProperty(
    name = _("Signal magnification"),
    description = _("Enlarge this object when it is far away from the viewpoint"),
    min = 0.0,
    max = 10.0,
    default = 0.0
)

bpy.types.Material.texture_stage_1 = bpy.props.PointerProperty(
    name = _("Texture stage 1"),
    description = _("Settings for the first texture stage"),
    type = ZusiTexturePresetTextureStageSettings,
)

bpy.types.Material.texture_stage_2 = bpy.props.PointerProperty(
    name = _("Texture stage 2"),
    description = _("Settings for the second texture stage"),
    type = ZusiTexturePresetTextureStageSettings,
)

bpy.types.Material.texture_stage_3 = bpy.props.PointerProperty(
    name = _("Texture stage 3"),
    description = _("Settings for the third texture stage"),
    type = ZusiTexturePresetTextureStageSettings,
)

bpy.types.Material.result_stage = bpy.props.PointerProperty(
    name = _("Result stage"),
    description = _("Settings for the result stage"),
    type = ZusiTexturePresetResultStageSettings,
)

bpy.types.Material.zusi_second_pass = bpy.props.BoolProperty(
    name = _("Additional drawing pass without Z buffer"),
    description = _("Additional drawing pass without Z buffer. Only available for 'One texture, semi-transparency' preset."),
    default = False
)

bpy.types.Material.zusi_night_switch_threshold = bpy.props.FloatProperty(
    name = _("Night switch threshold"),
    description = _("Environment brightness below which the night texture is displayed"),
    min = 0.0,
    max = 1.0,
    default = 0.0,
)

#
# Texture
#

bpy.types.Texture.zusi_meters_per_texture = bpy.props.FloatProperty(
    name = _("Meters per texture"),
    description = _("Side length of a square which this texture would completely cover"),
    min = 0.0,
    default = 0.0,
)

bpy.types.Texture.zusi_variants_visibility_mode = bpy.props.EnumProperty(
    name = "Variant visibility mode",
    items = variant_visibility_modes
)

bpy.types.Texture.zusi_variants_visibility = bpy.props.CollectionProperty(
    name = _("Variant visibility"),
    description = _("Choose which variants this object is visible in when exporting"),
    type = ZusiFileVariantVisibility
)

#
# Object
#

bpy.types.Object.zusi_subset_name = bpy.props.StringProperty(
    name = _("Subset name"),
    description = _("Name of the subset in which to export this object. Objects with different subset names will never be exported into the same subset."),
    default = ""
)

bpy.types.Object.zusi_variants_visibility_mode = bpy.props.EnumProperty(
    name = _("Variant visibility mode"),
    items = variant_visibility_modes,
    default = "None"
)

bpy.types.Object.zusi_variants_visibility = bpy.props.CollectionProperty(
    name = _("Variant visibility"),
    description = _("Choose which variants this object is visible in when exporting"),
    type = ZusiFileVariantVisibility
)

# Anchor points


bpy.types.Object.zusi_is_anchor_point = bpy.props.BoolProperty(
    name = _("Anchor point"),
    description = _("Export this object as an anchor point"),
    default = False
)

bpy.types.Object.zusi_anchor_point_category = bpy.props.EnumProperty(
    name = _("Category"),
    description = _("Anchor point category"),
    items = anchor_point_categories,
    default = "0"
)

bpy.types.Object.zusi_anchor_point_type = bpy.props.EnumProperty(
    name = _("Type"),
    description = _("Anchor point type"),
    items = anchor_point_types,
    default = "0"
)

bpy.types.Object.zusi_anchor_point_description = bpy.props.StringProperty(
    name = _("Description"),
    description = _("Anchor point description"),
    default = ""
)

bpy.types.Object.zusi_anchor_point_files = bpy.props.CollectionProperty(
    name = _("Suggested files/folders to be attached here"),
    description = _("List of files and folders of files that can be attached here"),
    type = ZusiAnchorPointFile
)

bpy.types.Object.zusi_anchor_point_files_index = bpy.props.IntProperty()

# Links

bpy.types.Object.zusi_is_linked_file = bpy.props.BoolProperty(
    name = _("Linked file"),
    description = _("Create a link to another file, with location, rotation, and scale taken from this object"),
    default = False
)

bpy.types.Object.zusi_link_file_name = bpy.props.StringProperty()

def set_zusi_link_file_name(self, value):
    self.zusi_link_file_name = blender_path_to_zusi_file_path(value)

bpy.types.Object.zusi_link_file_name_realpath = bpy.props.StringProperty(
    name = _("File name"),
    subtype = 'FILE_PATH',
    get = lambda self: zusi_file_path_to_blender_path(self.zusi_link_file_name),
    set = set_zusi_link_file_name,
)

bpy.types.Object.zusi_link_group = bpy.props.StringProperty(
    name = _("Group"),
)

bpy.types.Object.zusi_link_visible_from = bpy.props.FloatProperty(
    name = _("Visible from [m]"),
    min = 0.0,
)

bpy.types.Object.zusi_link_visible_to = bpy.props.FloatProperty(
    name = _("Visible to [m]"),
    min = 0.0,
    default = 3000.0,
)

bpy.types.Object.zusi_link_preload_factor = bpy.props.FloatProperty(
    name = _("Preload from [Factor]"),
    min = 0.0,
    default = 1.0,
)

bpy.types.Object.zusi_link_radius = bpy.props.IntProperty(
    name = _("Radius [m]"),
)

bpy.types.Object.zusi_link_forced_brightness = bpy.props.FloatProperty(
    name = _("Forced brightness [-1..1]"),
)

# Due to an implementation error in older versions of blender_ls3,
# this does not correspond to the LOD value used by Zusi.
# Instead, the flags are:
#  LOD0 - 1   [should be: 8]
#  LOD1 - 2   [4]
#  LOD2 - 4   [2]
#  LOD3 - 8   [1]
bpy.types.Object.zusi_link_lod = bpy.props.IntProperty(
    name = _("Level of detail"),
)

bpy.types.Object.zusi_link_is_tile = bpy.props.BoolProperty(
    name = _("Tile"),
    default = False,
)

bpy.types.Object.zusi_link_is_detail_tile = bpy.props.BoolProperty(
    name = _("Detail tile"),
    default = False,
)

bpy.types.Object.zusi_link_is_billboard = bpy.props.BoolProperty(
    name = _("Billboard"),
    default = False,
)

bpy.types.Object.zusi_link_is_readonly = bpy.props.BoolProperty(
    name = _("Read only"),
    default = True,
)

bpy.types.Object.zusi_link_animations = bpy.props.CollectionProperty(
    name = _("Animations"),
    description = _("Animations contained in the linked file"),
    type = ZusiLinkAnimation,
)

bpy.types.Object.zusi_link_animations_index = bpy.props.IntProperty()

#
# Scene
#

bpy.types.Scene.zusi_variants = bpy.props.CollectionProperty(
    name = _("Variants"),
    description = _("Variants contained in this file"),
    type = ZusiFileVariant
)

bpy.types.Scene.zusi_variants_index = bpy.props.IntProperty()

bpy.types.Scene.zusi_authors = bpy.props.CollectionProperty(
    name = _("Authors"),
    description = _("Information about this file's author(s)"),
    type = ZusiAuthor
)

bpy.types.Scene.zusi_authors_index = bpy.props.IntProperty()

bpy.types.Scene.zusi_object_id = bpy.props.IntProperty(
    name = _("Object ID"),
    description = _("A unique ID of this object"),
    default = 0,
    min = 0
)

# DEPRECATED. Licenses are now specified per author.
bpy.types.Scene.zusi_license = bpy.props.EnumProperty(
    name = _("License"),
    description = _("The license under which this object is published"),
    items = licenses,
    default = "0"
)

bpy.types.Scene.zusi_description = bpy.props.StringProperty(
    name = _("Description"),
    description = _("A short description of this object"),
    default = ""
)

bpy.types.Scene.zusi_animations_index= bpy.props.IntProperty()

#
# Action
#

bpy.types.Action.zusi_animation_type = bpy.props.EnumProperty(
    name = _("Animation type"),
    description = _("Defines how the animation is triggered in the simulator"),
    items = animation_types,
    default = "0"
)

bpy.types.Action.zusi_animation_speed = bpy.props.FloatProperty(
    name = _("Animation speed"),
    description = _("Speed of the animation, meaning depends on animation type"),
    default = 0.0,
    min = 0.0
)

bpy.types.Action.zusi_animation_wheel_diameter = bpy.props.FloatProperty(
    name = _("Wheel diameter"),
    description = _("The animation speed converted into a wheel diameter for wheel animations"),
    subtype = "DISTANCE",
    default = 0.0,
    min = 0.0,
    get = get_zusi_animation_wheel_diameter,
    set = set_zusi_animation_wheel_diameter
)

bpy.types.Action.zusi_animation_duration = bpy.props.FloatProperty(
    name = _("Animation duration"),
    description = _("The animation speed converted into an animation duration (in seconds) for door animations"),
    subtype = "TIME",
    default = 0.0,
    min = 0.0,
    get = get_zusi_animation_duration,
    set = set_zusi_animation_duration
)

bpy.types.Action.zusi_animation_names = bpy.props.CollectionProperty(
    name = _("Animation names"),
    description = _("Animation names this action belongs to, if animation type is 'Undefined/signal controlled'"),
    type = ZusiAnimationName,
)

bpy.types.Action.zusi_animation_names_index = bpy.props.IntProperty()

bpy.types.Action.zusi_animation_loop = bpy.props.BoolProperty(
    name = _("Loop"),
    description = _("Set this animation to looping in Zusi"),
    default = False,
)

# ===
# Custom UI
# ===

# Draws a UI part to select the visibility of the object or texture ob in file variants
def draw_variants_visibility_box(context, layout, ob, object_type = "Object"):
    if len(context.scene.zusi_variants) > 0:
        layout.prop(ob, "zusi_variants_visibility_mode", text = _("Variants"))

        selected_variants = [vis.variant_id for vis in ob.zusi_variants_visibility]
        box = layout.box()
        box.enabled = (ob.zusi_variants_visibility_mode != "None" and ob.library is None)
        for variant in context.scene.zusi_variants:
            row = box.row(align = False)
            row.alignment = "LEFT"

            icon_name = "CHECKBOX_DEHLT"
            if variant.id in selected_variants:
                icon_name = "CHECKBOX_HLT"

            op = row.operator("zusi.toggle_variant_visibility", text = variant.name, emboss = False, icon = icon_name)
            op.variant_id = variant.id
            op.object_type = object_type
    else:
        layout.label(_("Variants:"))
        box = layout.box()
        box.label(_("Variants can be defined in the Scene settings."))

# ---
# Data panel (Mesh, link, and anchor point properties)
# ---

class OBJECT_PT_data_zusi_properties(bpy.types.Panel):
    bl_label = _("Zusi specific properties")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(self, context):
        return context.mesh

    def draw(self, context):
        if context.mesh:
            self.layout.prop(context.mesh, "zusi_is_rail")

class OBJECT_PT_data_linked_file(bpy.types.Panel):
    bl_label = _("Linked file")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(self, context):
        return context.object and context.object.type == 'EMPTY'

    def draw_header(self, context):
        self.layout.prop(context.object, "zusi_is_linked_file", text = "")

    def draw(self, context):
        ob = context.object
        layout = self.layout

        layout.active = ob.zusi_is_linked_file

        op = layout.operator("zusi_linked_file.embed")
        op.ob = ob.name

        layout.prop(ob, "zusi_link_file_name_realpath")
        layout.prop(ob, "zusi_link_group")
        layout.prop(ob, "zusi_link_visible_from")
        layout.prop(ob, "zusi_link_visible_to")
        layout.prop(ob, "zusi_link_preload_factor")
        layout.prop(ob, "zusi_link_radius")
        layout.prop(ob, "zusi_link_forced_brightness")

        box = layout.box()
        for lod, lodbit in enumerate([1, 2, 4, 8]):
            row = box.row()
            row.alignment = 'LEFT'
            op = row.operator("zusi.toggle_link_lod", text = _("LOD {}").format(lod), emboss = False,
                icon = "CHECKBOX_HLT" if ob.zusi_link_lod & lodbit else "CHECKBOX_DEHLT")
            op.lodbit = lodbit

        layout.prop(ob, "zusi_link_is_tile")
        layout.prop(ob, "zusi_link_is_detail_tile")
        layout.prop(ob, "zusi_link_is_billboard")
        layout.prop(ob, "zusi_link_is_readonly")

        layout.label(_("Animations contained in the linked file"))
        template_list(layout.row(), "ZusiLinkAnimationList", "",
                ob, "zusi_link_animations", ob, "zusi_link_animations_index",
                "zusi_link_animations.add", "zusi_link_animations.remove", rows = 3)

class OBJECT_PT_data_anchor_point(bpy.types.Panel):
    bl_label = _("Anchor point")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(self, context):
        return context.object and context.object.type == 'EMPTY'

    def draw_header(self, context):
        self.layout.prop(context.object, "zusi_is_anchor_point", text = "")

    def draw(self, context):
        ob = context.object
        layout = self.layout

        layout.active = ob.zusi_is_anchor_point

        layout.prop(ob, "zusi_anchor_point_category")
        layout.prop(ob, "zusi_anchor_point_type")
        layout.prop(ob, "zusi_anchor_point_description")

        layout.label(_("Suggested files/folders to be attached here:"))
        template_list(layout.row(), "ZusiAnchorPointFileList", "",
                ob, "zusi_anchor_point_files", ob, "zusi_anchor_point_files_index",
                "zusi_anchor_point_files.add", "zusi_anchor_point_files.remove", rows = 3)

        if ob.zusi_anchor_point_files and ob.zusi_anchor_point_files_index >= 0 and ob.zusi_anchor_point_files_index < len(ob.zusi_anchor_point_files):
            layout.prop(ob.zusi_anchor_point_files[ob.zusi_anchor_point_files_index], "name_realpath")

class ZUSI_ANCHOR_POINT_FILES_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_anchor_point_files.add'
    bl_label = _("Add file/folder")
    bl_description = _("Add a suggested file or folder")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(self, context):
        return context.object is not None and context.object.type == 'EMPTY'

    def invoke(self, context, event):
        context.object.zusi_anchor_point_files.add()
        return{'FINISHED'}

class ZUSI_ANCHOR_POINT_FILES_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_anchor_point_files.remove'
    bl_label = _("Remove file/folder")
    bl_description = _("Remove the selected file or folder from the list of files")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(self, context):
        return context.object is not None and len(context.object.zusi_anchor_point_files) > 0

    def invoke(self, context, event):
        ob = context.object
        if ob.zusi_anchor_point_files_index >= 0 and len(ob.zusi_anchor_point_files) > 0:
            ob.zusi_anchor_point_files.remove(ob.zusi_anchor_point_files_index)
            ob.zusi_anchor_point_files_index = max(ob.zusi_anchor_point_files_index - 1, 0)

        return{'FINISHED'}

class ZUSI_LINK_ANIMATIONS_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_link_animations.add'
    bl_label = _("Add linked animation")
    bl_description = _("Add info about an animation contained in the linked file")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(self, context):
        return context.object is not None and context.object.type == 'EMPTY'

    def invoke(self, context, event):
        context.object.zusi_link_animations.add()
        return{'FINISHED'}

class ZUSI_LINK_ANIMATIONS_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_link_animations.remove'
    bl_label = _("Remove linked animation")
    bl_description = _("Remove the selected animation info from the list")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(self, context):
        return context.object is not None and len(context.object.zusi_link_animations) > 0

    def invoke(self, context, event):
        ob = context.object
        if ob.zusi_link_animations_index >= 0 and len(ob.zusi_link_animations) > 0:
            ob.zusi_link_animations.remove(ob.zusi_link_animations_index)
            ob.zusi_link_animations_index = max(ob.zusi_link_animations_index - 1, 0)

        return{'FINISHED'}

# ---
# Material panel
# ---

class OBJECT_PT_material_zusi_properties(bpy.types.Panel):
    bl_label = _("Zusi specific properties")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(self, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout

        mat = context.material

        if mat:
            layout.prop(mat, "zusi_landscape_type")
            layout.prop(mat, "zusi_gf_type")
            layout.prop(mat, "zusi_texture_preset")

            if mat.zusi_texture_preset == '0': # Custom
                layout.operator("zusi_texture_preset.edit")
            elif mat.zusi_texture_preset == '4': # One texture, semi-transparency
                layout.prop(mat, "zusi_second_pass")
            elif mat.zusi_texture_preset in ['5', '10']:
                layout.prop(mat, "zusi_night_switch_threshold")

            if mat.zusi_texture_preset == '5':
                layout.prop(mat, "zusi_day_mode_preset")

            layout.prop(mat, "zusi_force_brightness")
            layout.prop(mat, "zusi_signal_magnification")
            layout.prop(mat, "zusi_use_ambient", text = _("Ambient color:"))

            row = layout.row()
            row.enabled = mat.zusi_use_ambient
            row.prop(mat, "zusi_ambient_color", text="")
            row.prop(mat, "zusi_ambient_alpha", slider=True, text="Alpha")

            layout.prop(mat, "zusi_use_emit", text = _("Night color:"))
            row = layout.row()
            row.enabled = mat.zusi_use_emit
            row.prop(mat, "zusi_emit_color", text="")

            # Warn the user when night color is not exportable.
            diffuse_color = mat.diffuse_color * mat.diffuse_intensity
            if mat.zusi_use_emit:
                emit_color = mat.zusi_emit_color
                ambient_color = mat.zusi_ambient_color if mat.zusi_use_ambient else mathutils.Color((1, 1, 1))
                if emit_color.r > diffuse_color.r or emit_color.g > diffuse_color.g or emit_color.b > diffuse_color.b \
                        or emit_color.r > ambient_color.r or emit_color.g > ambient_color.g or emit_color.b > ambient_color.b:
                    layout.label(text = _("Must be darker than diffuse (%.3f, %.3f, %.3f) and ambient in all components.")
                        % (diffuse_color.r, diffuse_color.g, diffuse_color.b), icon = "ERROR")

            layout.prop(mat, "zusi_allow_overexposure", text = _("Overexposure"))

            row = layout.row()
            row.enabled = mat.zusi_allow_overexposure
            row.prop(mat, "zusi_overexposure_addition", text = _("Add to diffuse"))

            # Warn the user when overexposure is not exportable.
            if row.enabled:
                emit_color = mat.zusi_emit_color if mat.zusi_use_emit else mathutils.Color((0, 0, 0))
                resulting_diffuse = diffuse_color - emit_color + mat.zusi_overexposure_addition
                if (resulting_diffuse.r > 1.0 or resulting_diffuse.g > 1.0 or resulting_diffuse.b > 1.0):
                    # Intentionally cryptic error message, as only pros should use this feature :)
                    layout.label(text = _("Must have Diffuse - Night + Overexposure <= 1.0 in all components"),
                        icon = "ERROR")

            row = layout.row()
            row.enabled = mat.zusi_allow_overexposure and mat.zusi_use_ambient
            row.prop(mat, "zusi_overexposure_addition_ambient", text = _("Add to ambient"))

            if row.enabled:
                emit_color = mat.zusi_emit_color if mat.zusi_use_emit else mathutils.Color((0, 0, 0))
                resulting_ambient = mat.zusi_ambient_color - emit_color + mat.zusi_overexposure_addition_ambient
                if (resulting_ambient.r > 1.0 or resulting_ambient.g > 1.0 or resulting_ambient.b > 1.0):
                    # Intentionally cryptic error message, as only pros should use this feature :)
                    layout.label(text = _("Must have Ambient - Night + Overexposure <= 1.0 in all components"),
                        icon = "ERROR")

class OBJECT_PT_material_edit_custom_texture_preset(bpy.types.Operator):
    bl_idname = 'zusi_texture_preset.edit'
    bl_label = _("Edit custom texture preset")
    bl_description = _("Edit the custom texture preset")
    bl_options = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(self, context):
        return (
            context.object is not None and
            context.object.data is not None and
            len(context.object.data.materials) > 0 and
            context.object.data.materials[context.object.active_material_index].zusi_texture_preset == "0")
    
    def draw(self, context):
        layout = self.layout

        mat = context.object.data.materials[context.object.active_material_index]

        if mat:
            for (texstage, description) in [
                    (mat.texture_stage_1, _("First texture stage")),
                    (mat.texture_stage_2, _("Second texture stage"))]:
                col = layout.column()
                col.label(description)
                col.prop(texstage, "D3DSAMP_MINFILTER")
                col.prop(texstage, "D3DSAMP_MAGFILTER")
                col.prop(texstage, "D3DTSS_COLOROP")
                col.prop(texstage, "D3DTSS_COLORARG1")
                col.prop(texstage, "D3DTSS_COLORARG2")
                col.prop(texstage, "D3DTSS_COLORARG0")
                col.prop(texstage, "D3DSAMP_ALPHAOP")
                col.prop(texstage, "D3DTSS_ALPHAARG1")
                col.prop(texstage, "D3DTSS_ALPHAARG2")
                col.prop(texstage, "D3DTSS_ALPHAARG0")
                col.prop(texstage, "D3DTSS_RESULTARG")
            
            col = layout.column()
            col.label(_("Third texture stage"))
            col.prop(mat.texture_stage_3, "D3DTSS_COLOROP")
            col.prop(mat.texture_stage_3, "D3DTSS_COLORARG1")
            col.prop(mat.texture_stage_3, "D3DTSS_COLORARG2")
            
            col.label(_("Result stage"))
            col.prop(mat.result_stage, "D3DRS_DESTBLEND")
            col.prop(mat.result_stage, "D3DRS_SRCBLEND")
            col.prop(mat.result_stage, "D3DRS_ALPHABLENDENABLE")
            col.prop(mat.result_stage, "alpha_ref")
            col.prop(mat.result_stage, "D3DRS_SHADEMODE")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        return {'FINISHED'}

class OBJECT_OT_zusi_toggle_link_lod(bpy.types.Operator):
    bl_idname = "zusi.toggle_link_lod"
    bl_label = _("Toggle linked file LOD")
    bl_options = {'INTERNAL'}

    lodbit = bpy.props.IntProperty()

    def execute(self, context):
        ob = context.object
        if ob.zusi_link_lod & self.lodbit:
            ob.zusi_link_lod &= ~self.lodbit
        else:
            ob.zusi_link_lod |= self.lodbit

        return{'FINISHED'}

class OBJECT_OT_zusi_toggle_variant_visibility(bpy.types.Operator):
    bl_idname = "zusi.toggle_variant_visibility"
    bl_label = _("Toggle visibility")
    bl_options = {'INTERNAL'}

    variant_id = bpy.props.IntProperty()
    object_type = bpy.props.EnumProperty(
        items = [("Object", "", ""), ("Texture", "", "")]
    )

    def execute(self, context):
        ob = context.object
        if self.object_type == "Texture":
            ob = context.texture

        for index, vis in enumerate(ob.zusi_variants_visibility):
            if vis.variant_id == self.variant_id:
                ob.zusi_variants_visibility.remove(index)
                return{'FINISHED'}

        vis = ob.zusi_variants_visibility.add()
        vis.variant_id = self.variant_id

        return{'FINISHED'}

class OBJECT_PT_subset_zusi_properties(bpy.types.Panel):
    bl_label = _("Subset (for LS3 export)")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(self, context):
        return context.object is not None and (context.object.type == 'MESH' or context.object.type == 'EMPTY' or context.object.type == 'CURVE')

    def draw(self, context):
        if context.object.type == 'MESH':
            self.layout.prop(context.object, "zusi_subset_name")
        draw_variants_visibility_box(context, self.layout, context.object)

class TEXTURE_PT_zusi_properties(bpy.types.Panel):
    bl_label = _("Zusi specific properties")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "texture"

    @classmethod
    def poll(self, context):
        return context.texture is not None

    def draw(self, context):
        self.layout.prop(context.texture, "zusi_meters_per_texture")
        draw_variants_visibility_box(context, self.layout, context.texture, object_type = "Texture")

class SCENE_PT_zusi_properties(bpy.types.Panel):
    bl_label = _("Zusi file properties")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        layout.prop(sce, "zusi_object_id")
        layout.prop(sce, "zusi_description")

# ---
# Scene variant info UI
# ---

class ZUSI_VARIANTS_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_variants.add'
    bl_label = _("Add variant")
    bl_description = _("Add a variant to the scene")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        max_id = -1
        if len(context.scene.zusi_variants) > 0:
            max_id = max([v.id for v in context.scene.zusi_variants])
    
        new_variant = context.scene.zusi_variants.add()
        new_variant.name = _("Variant")
        new_variant.id = max_id + 1
        return{'FINISHED'}

class ZUSI_VARIANTS_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_variants.remove'
    bl_label = _("Remove variant")
    bl_description = _("Remove the selected variant from the scene")
    bl_options = {'INTERNAL'}
    
    @classmethod
    def poll(self, context):
        return len(context.scene.zusi_variants) > 0

    def invoke(self, context, event):
        sce = context.scene

        zusi_variants = sce.zusi_variants

        if sce.zusi_variants_index >= 0 and len(zusi_variants) > 0:
            variant_id = zusi_variants[sce.zusi_variants_index].id

            # Remove visibility setting for this variant from all objects
            for ob in sce.objects:
                for idx, vis in enumerate(ob.zusi_variants_visibility):
                    if vis.variant_id == variant_id:
                        ob.zusi_variants_visibility.remove(idx)
        
            zusi_variants.remove(sce.zusi_variants_index)
            sce.zusi_variants_index = max(sce.zusi_variants_index - 1, 0)

        return{'FINISHED'}

class ZUSI_VARIANTS_OT_move(bpy.types.Operator):
    bl_idname = 'zusi_variants.move'
    bl_label = _("Move variant")
    bl_description = _("Move a variant")
    bl_options = {'INTERNAL'}

    move_up = bpy.props.BoolProperty()

    @classmethod
    def poll(self, context):
        return context.scene.zusi_variants

    def execute(self, context):
        new_variant_index = context.scene.zusi_variants_index + (-1 if self.move_up else 1)
        if new_variant_index < 0 or new_variant_index >= len(context.scene.zusi_variants):
            return{'FINISHED'}
        context.scene.zusi_variants.move(context.scene.zusi_variants_index, new_variant_index)
        context.scene.zusi_variants_index = new_variant_index
        return{'FINISHED'}

class SCENE_PT_zusi_variants(bpy.types.Panel):
    bl_label = _("Variants")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        # Show list of variants with add/remove button
        template_list(layout.row(), "ZusiFileVariantList", "", sce, "zusi_variants", sce, "zusi_variants_index",
                "zusi_variants.add", "zusi_variants.remove", "zusi_variants.move", rows = 3)

        # Show input field to change variant name (in Blender >= 2.70, this is instead done by double-clicking on the item)
        if bpy.app.version < (2, 70, 0) and sce.zusi_variants:
            entry = sce.zusi_variants[sce.zusi_variants_index]
            layout.prop(entry, "name")

# ---
# Animation info UI
# ---

class ACTION_OT_add_zusi_animation_name(bpy.types.Operator):
    bl_idname = 'action.add_zusi_animation_name'
    bl_label = _("Add animation name")
    bl_description = _("Add the name of an animation this action belongs to")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        bpy.data.actions[context.scene.zusi_animations_index].zusi_animation_names.add().name = "Animation"
        return{'FINISHED'}

class ACTION_OT_del_zusi_animation_name(bpy.types.Operator):
    bl_idname = 'action.del_zusi_animation_name'
    bl_label = _("Remove animation name")
    bl_description = _("Remove the selected animation name from the list of animations this action belongs to")
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(self, context):
        return len(bpy.data.actions) > 0 and \
            len(bpy.data.actions[context.scene.zusi_animations_index].zusi_animation_names) > 0

    def invoke(self, context, event):
        action = bpy.data.actions[context.scene.zusi_animations_index]
        animation_names = action.zusi_animation_names
        if action.zusi_animation_names_index >= 0 and len(animation_names) > 0:
            animation_names.remove(action.zusi_animation_names_index)
            action.zusi_animation_names_index = max(action.zusi_animation_names_index - 1, 0)
        return{'FINISHED'}

class ACTION_OT_set_interpolation_linear(bpy.types.Operator):
    bl_idname = 'action.set_interpolation_linear'
    bl_label = _("Set interpolation to linear")
    bl_description = _("Set the interpolation mode of all animation curves of this action to 'Linear'")
    bl_options = {'INTERNAL', 'UNDO'}

    action_name = bpy.props.StringProperty(options = {'HIDDEN'})

    def execute(self, context):
        for fcurve in bpy.data.actions[self.action_name].fcurves:
            for keyframe in fcurve.keyframe_points:
                keyframe.interpolation = 'LINEAR'
        return{'FINISHED'}

class SCENE_PT_zusi_animations(bpy.types.Panel):
    bl_label = _("Zusi animations")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        template_list(layout.row(), "UI_UL_list", "zusi_animation_list", bpy.data, "actions", context.scene, "zusi_animations_index", rows = 3)

        if len(bpy.data.actions) > 0 and len(bpy.data.actions) > context.scene.zusi_animations_index:
            action = bpy.data.actions[context.scene.zusi_animations_index]
            ani_speed_enabled = action.zusi_animation_type in ["0", "1"]
            layout.prop(action, "name")
            layout.prop(action, "zusi_animation_type")
            if action.zusi_animation_type in ["0", "1"]:
                layout.prop(action, "zusi_animation_loop")
            row = layout.row()
            row.active = ani_speed_enabled
            row.prop(action, "zusi_animation_speed")
            if action.zusi_animation_type in ["2", "3", "4", "5"]:
                layout.prop(action, "zusi_animation_wheel_diameter")
            elif action.zusi_animation_type in ["12", "13"]:
                layout.prop(action, "zusi_animation_duration")
            elif action.zusi_animation_type == "0":
                box = layout.box()
                box.row().label(text = _("Part of the following animations:"))
                template_list(box.row(), "UI_UL_list", "zusi_animation_name_list",
                        action, "zusi_animation_names", action, "zusi_animation_names_index",
                        "action.add_zusi_animation_name", "action.del_zusi_animation_name", rows = 3)
                if len(action.zusi_animation_names):
                    box.prop(action.zusi_animation_names[action.zusi_animation_names_index], "name")

            layout.operator("action.set_interpolation_linear").action_name = action.name

# ---
# Author info UI
# ---

class ZUSI_AUTHORS_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_authors.add'
    bl_label = _("Add author")
    bl_description = _("Add an author to the scene")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        context.scene.zusi_authors.add().name = _("Author")
        return{'FINISHED'}

class ZUSI_AUTHORS_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_authors.remove'
    bl_label = _("Remove author")
    bl_description = _("Remove the selected author from the scene")
    
    @classmethod
    def poll(self, context):
        return len(context.scene.zusi_authors) > 0

    def invoke(self, context, event):
        sce = context.scene

        zusi_authors = sce.zusi_authors

        if sce.zusi_authors_index >= 0 and len(zusi_authors) > 0:
            zusi_authors.remove(sce.zusi_authors_index)
            sce.zusi_authors_index = max(sce.zusi_authors_index - 1, 0)

        return{'FINISHED'}

class ZUSI_AUTHORS_OT_add_default(bpy.types.Operator):
    bl_idname = 'zusi_authors.add_default'
    bl_label = _("Add default author information")
    bl_description = _("Add author information entered in the Zusi File Management application (Windows) or the configuration file (other operating systems)")
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        default_author = zusicommon.get_default_author_info()
        author = context.scene.zusi_authors.add()
        author.name = default_author['name']
        author.id = default_author['id']
        author.email = default_author['email']
        return{'FINISHED'}

class SCENE_PT_zusi_authors(bpy.types.Panel):
    bl_label = _("Author information")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        layout.operator("zusi_authors.add_default")

        # Show list of authors with add/remove buttons.
        template_list(layout.row(), "ZusiAuthorList", "", sce, "zusi_authors", sce, "zusi_authors_index",
                "zusi_authors.add", "zusi_authors.remove", rows = 3)

        # Show input fields to change author data
        if sce.zusi_authors:
            entry = sce.zusi_authors[sce.zusi_authors_index]
            row = layout.row()
            # Show input field to change author name (in Blender >= 2.70, this is instead done by double-clicking on the item)
            if bpy.app.version < (2, 70, 0):
                row.prop(entry, "name")
            row.prop(entry, "id")
            layout.prop(entry, "email")
            if entry.effort > 0:
                layout.prop(entry, "effort")
            layout.prop(entry, "effort_hours")
            layout.prop(entry, "license")
            layout.prop(entry, "remarks")
