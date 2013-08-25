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
from . import zusicommon

# This file defines Zusi specific custom properties and the corresponding UI.

# Defines a list with check boxes.
class CheckBoxList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        icon = "CHECKBOX_HLT" if self.get_property_value(item) else "CHECKBOX_DEHLT"
        layout.prop(item, self.get_property_name(), text = "", icon = icon, toggle = True, icon_only = True, emboss = False)
        layout.label(self.get_item_text(item))

bpy.utils.register_class(CheckBoxList)

# Defines a variant in a scene with an ID (which should not be changed) and a variant name
# (Name is defined in PropertyGroup)
class ZusiFileVariant(bpy.types.PropertyGroup):
    id = bpy.props.IntProperty(
        name = "ID",
        description = "Unique ID of this variant",
    )

bpy.utils.register_class(ZusiFileVariant)

class ZusiFileVariantList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.name)

# Defines a visibility of an object/material/texture/whatever in a certain variant
class ZusiFileVariantVisibility(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = "Variant ID",
        description = "ID of the variant this object is visible in"
    )

bpy.utils.register_class(ZusiFileVariantVisibility)

class ZusiFileVariantVisibilityList(CheckBoxList):
    def get_property_name(self):
        return "visible"
    
    def get_property_value(self, item):
        return item.visible
    
    def get_item_text(self, item):
        return str(item.name)

# Contains information about a file's author
class ZusiAuthor(bpy.types.PropertyGroup):
    id = bpy.props.IntProperty(
        name = "ID",
        description = "The ID of the author",
        min = 0
    )

    name = bpy.props.StringProperty(
        name = "Name",
        description = "The name of the author",
        default = ""
    )

    email = bpy.props.StringProperty(
        name = "E-mail",
        description = "The e-mail address of the author",
        default = ""
    )

    effort = bpy.props.FloatProperty(
        name = "Effort",
        description = "The effort of the author (unit: one house)",
        min = 0,
        default = 0.0
    )

    remarks = bpy.props.StringProperty(
        name = "Remarks",
        description = "Remarks about the author",
        default = ""
    )

bpy.utils.register_class(ZusiAuthor)

class ZusiAuthorList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(item.name)

# ---
# Custom properties
# ---

landscape_types = [
    ("0", "Unspecified", ""),
    ("1", "Grundplatte", ""),
    ("2", "Bahndamm", ""),
    ("3", "Stützmauer", ""),
    ("4", "Gleisbett", ""),
    ("5", "Schulter", ""),
    ("6", "Randweg", ""),
    ("7", "Gleiszwischenraum", ""),
    ("8", "Schiene", ""),
    ("9", "Radlenker", ""),
    ("10", "Bahnsteig", ""),
    ("11", "Straße", ""),
    ("12", "Wasser", ""),
    ("13", "Tunnel", ""),
    ("14", "Fahrleitung", ""),
    ("15", "Wald", ""),
    ("16", "Dummy (invisible in simulator)", ""),
    ("17", "Spitzenlicht vorne", ""),
    ("18", "Schlusslicht vorne", ""),
    ("19", "Spitzenlicht hinten", ""),
    ("20", "Schlusslicht hinten", ""),
    ("21", "Schiene 2D", ""),
    ("22", "Radlenker 2D", ""),
]

gf_types = [
    ("0", "Ignore", ""),
    ("1", "Default", ""),
    ("2", "Tunnel", ""),
    ("3", "Permanent way", ""),
    ("4", "Edge of a forest", ""),
    ("5", "Forest area, GF generated", ""),
    ("6", "Ground plane, GF generated", ""),
    ("7", "Background, GF generated", ""),
]

texture_presets = [
    ("0", "Custom", ""),
    ("1", "Default, single texture", ""),
    ("2", "Default, single texture, full transparency", ""),
    ("3", "Tex. 1 default, tex. 2 semi-transparent", ""),
    ("4", "Default, single texture, semi-transparency", ""),
    ("5", "Tex. 1 default, tex. 2 transparent/illuminated", ""),
    ("6", "Signalblende (durchleuchtet)", ""),
    ("7", "Signal lamp, fading (semi-transparent)", ""),
    ("8", "Semi-transparency for leaves and similar structures", ""),
    ("9", "Overlaying window, fading off during daytime", ""),
    ("10", "Overlaying window, turned off during daytime", ""),
]

licenses = [
    ("0", "Zusi default license (freeware for non-commercial use)", ""),
    ("1", "Public Domain", ""),
    ("2", "Commercial", ""),
    ("3", "Non-commercial", "")
]

variant_visibility_modes = [
    ("None", "Visible in all variants", ""),
    ("True", "Visible only in the selected variants", ""),
    ("False", "Visible in all but the selected variants", ""),
]


#
# Material
#

bpy.types.Material.zusi_emit_color = bpy.props.FloatVectorProperty(
    name = "Night color",
    description = "The night color aka emissive color of the material",
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.0, 0.0, 0.0)
)

bpy.types.Material.zusi_emit_alpha = bpy.props.FloatProperty(
    name = "Night color alpha",
    description = "The alpha value of the night color",
    precision = 3,
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = 1.0
)

bpy.types.Material.zusi_use_emit = bpy.props.BoolProperty(
    name = "Use night color",
    description = "Use a specific night color for this material",
    default = False
)

bpy.types.Material.zusi_ambient_color = bpy.props.FloatVectorProperty(
    name = "Ambient color",
    description = "The ambient color of the material",
    subtype = 'COLOR',
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = (0.8, 0.8, 0.8)
)

bpy.types.Material.zusi_ambient_alpha = bpy.props.FloatProperty(
    name = "Ambient color alpha",
    description = "The alpha value of the ambient color",
    precision = 3,
    min = 0.0,
    max = 1.0,
    soft_min = 0.0,
    soft_max = 1.0,
    default = 1.0
)

bpy.types.Material.zusi_use_ambient = bpy.props.BoolProperty(
    name = "Use ambient color",
    description = "Use a specific ambient color for this material",
    default = False
)

bpy.types.Material.zusi_texture_preset = bpy.props.EnumProperty(
    name = "Texture preset",
    description = "The texture preset to assign to this material",
    items = texture_presets,
    default = "1"
)

bpy.types.Material.zusi_landscape_type = bpy.props.EnumProperty(
    name = "Landscape type",
    description = "The landscape type to assign to this subset",
    items = landscape_types,
    default = "0"
)

bpy.types.Material.zusi_gf_type = bpy.props.EnumProperty(
    name = "GF type",
    description = "The GF (Geländeformer) type to assign to this subset",
    items = gf_types,
    default = "0"
)

bpy.types.Material.zusi_force_brightness = bpy.props.FloatProperty(
    name = "Force brightness",
    description = "Force this material to have a specific brightness",
    min = 0.0,
    max = 1.0,
    default = 0.0
)

bpy.types.Material.zusi_signal_magnification = bpy.props.FloatProperty(
    name = "Signal magnification",
    description = "Enlarge this object when it is far away from the viewpoint",
    min = 0.0,
    max = 10.0,
    default = 0.0
)

#
# Texture
#

bpy.types.Texture.zusi_variants_visibility_mode = bpy.props.EnumProperty(
    name = "Variant visibility mode",
    items = variant_visibility_modes
)

bpy.types.Texture.zusi_variants_visibility = bpy.props.CollectionProperty(
    name = "Variant visibility",
    description = "Choose which variants this object is visible in when exporting",
    type = ZusiFileVariantVisibility
)

#
# Object
#

bpy.types.Object.zusi_subset_name = bpy.props.StringProperty(
    name = "Subset name",
    description = "Name of the subset in which to export this object. If empty, this object will be exported into a subset with the object's material's name",
    default = ""
)

bpy.types.Object.zusi_variants_visibility_mode = bpy.props.EnumProperty(
    name = "Variant visibility mode",
    items = variant_visibility_modes,
    default = "None"
)

bpy.types.Object.zusi_variants_visibility = bpy.props.CollectionProperty(
    name = "Variant visibility",
    description = "Choose which variants this object is visible in when exporting",
    type = ZusiFileVariantVisibility
)

#
# Scene
#

bpy.types.Scene.zusi_variants = bpy.props.CollectionProperty(
    name = "Variants",
    description = "Variants contained in this file",
    type = ZusiFileVariant
)

bpy.types.Scene.zusi_variants_index = bpy.props.IntProperty()

bpy.types.Scene.zusi_authors = bpy.props.CollectionProperty(
    name = "Authors",
    description = "Information about this file's author(s)",
    type = ZusiAuthor
)

bpy.types.Scene.zusi_authors_index = bpy.props.IntProperty()

bpy.types.Scene.zusi_object_id = bpy.props.IntProperty(
    name = "Object ID",
    description = "A unique ID of this object",
    default = 0,
    min = 0
)

bpy.types.Scene.zusi_license = bpy.props.EnumProperty(
    name = "License",
    description = "The license under which this object is published",
    items = licenses,
    default = "0"
)

bpy.types.Scene.zusi_description = bpy.props.StringProperty(
    name = "Description",
    description = "A short description of this object",
    default = ""
)



# ===
# Custom UI
# ===

# Draws a UI part to select the visibility of the object ob in file variants
def draw_variants_visibility_box(context, layout, ob, object_type = "Object"):
    if len(context.scene.zusi_variants) > 0:
        row = layout.row()
        row.prop(ob, "zusi_variants_visibility_mode", text = "Variants")

        selected_variants = [vis.variant_id for vis in ob.zusi_variants_visibility]
        box = layout.box()
        box.enabled = (ob.zusi_variants_visibility_mode != "None")
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
        layout.label("Variants:")
        box = layout.box()
        box.label("Variants can be defined in the Scene settings.")

class OBJECT_PT_material_zusi_properties(bpy.types.Panel):
    bl_label = "Zusi specific properties"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(self, context):
        if context.object and context.object.type == 'MESH':
            return len(context.object.data.materials)

    def draw(self, context):
        layout = self.layout

        mat = context.object.data.materials[0]

        if mat:
            row = layout.row()
            row.prop(mat, "zusi_landscape_type")

            row = layout.row()
            row.prop(mat, "zusi_gf_type")
            
            row = layout.row()
            row.prop(mat, "zusi_texture_preset")

            row = layout.row()
            row.prop(mat, "zusi_force_brightness")

            row = layout.row()
            row.prop(mat, "zusi_signal_magnification")

            row = layout.row()
            row.prop(mat, "zusi_use_ambient", text = "Ambient color:")
            row = layout.row()
            row.enabled = mat.zusi_use_ambient
            row.prop(mat, "zusi_ambient_color", text="")
            row.prop(mat, "zusi_ambient_alpha", slider=True, text="Alpha")
            
            row = layout.row()
            row.prop(mat, "zusi_use_emit", text = "Night color:")
            row = layout.row()
            row.enabled = mat.zusi_use_emit
            row.prop(mat, "zusi_emit_color", text="")
            row.prop(mat, "zusi_emit_alpha", slider=True, text="Alpha")

class OBJECT_OT_zusi_toggle_variant_visibility(bpy.types.Operator):
    bl_idname = "zusi.toggle_variant_visibility"
    bl_label = "Toggle visibility"

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
    bl_label = "Subset (for LS3 export)"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(self, context):
        return context.object is not None and context.object.type == 'MESH'

    def draw(self, context):
        row = self.layout.row()
        row.prop(context.object, "zusi_subset_name")

        draw_variants_visibility_box(context, self.layout, context.object)

class TEXTURE_PT_variant_visibility(bpy.types.Panel):
    bl_label = "Variant visibility"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "texture"

    @classmethod
    def poll(self, context):
        return context.texture is not None

    def draw(self, context):
        draw_variants_visibility_box(context, self.layout, context.texture, object_type = "Texture")

class SCENE_PT_zusi_properties(bpy.types.Panel):
    bl_label = "Zusi file properties"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        row = layout.row()
        row.prop(sce, "zusi_object_id")

        row = layout.row()
        row.prop(sce, "zusi_license")

        row = layout.row()
        row.prop(sce, "zusi_description")

# ---
# Scene variant info UI
# ---

class ZUSI_VARIANTS_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_variants.add'
    bl_label = "Add variant"
    bl_description = "Add a variant to the scene"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        max_id = -1
        if len(context.scene.zusi_variants) > 0:
            max_id = max([v.id for v in context.scene.zusi_variants])
    
        new_variant = context.scene.zusi_variants.add()
        new_variant.name = "Variant"
        new_variant.id = max_id + 1
        return{'FINISHED'}

class ZUSI_VARIANTS_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_variants.remove'
    bl_label = "Remove variant"
    bl_description = "Remove the selected variant from the scene"
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

class SCENE_PT_zusi_variants(bpy.types.Panel):
    bl_label = "Variants"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        row = layout.row()

        # Show list of variants
        if bpy.app.version[0] == 2 and bpy.app.version[1] <= 66: # TODO which version?
            row.template_list(sce, "zusi_variants", sce, "zusi_variants_index", rows = 3, prop_list = "template_list_controls")
        else:
            row.template_list("ZusiFileVariantList", "", sce, "zusi_variants", sce, "zusi_variants_index", rows = 3)

        # Show add/remove operator
        col = row.column(align = True)
        col.operator("zusi_variants.add", icon = "ZOOMIN", text = "")
        col.operator("zusi_variants.remove", icon = "ZOOMOUT", text = "")

        # Show input field to change variant name
        if sce.zusi_variants:
            entry = sce.zusi_variants[sce.zusi_variants_index]
            row = layout.row()
            row.prop(entry, "name")

# ---
# Author info UI
# ---

class ZUSI_AUTHORS_OT_add(bpy.types.Operator):
    bl_idname = 'zusi_authors.add'
    bl_label = "Add author"
    bl_description = "Add a author to the scene"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        context.scene.zusi_authors.add().name = "Author"
        return{'FINISHED'}

class ZUSI_AUTHORS_OT_del(bpy.types.Operator):
    bl_idname = 'zusi_authors.remove'
    bl_label = "Remove author"
    bl_description = "Remove the selected author from the scene"
    
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
    bl_label = "Add default author information"
    bl_description = "Add author information entered in Zusi-Dateiverwaltung (Windows) or the configuration file (Linux)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        default_author = zusicommon.get_default_author_info()
        author = context.scene.zusi_authors.add()
        author.name = default_author['name']
        author.id = default_author['id']
        author.email = default_author['email']
        return{'FINISHED'}

class SCENE_PT_zusi_authors(bpy.types.Panel):
    bl_label = "Author information"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        sce = context.scene

        row = layout.row()
        row.operator("zusi_authors.add_default")

        # Show list of authors
        row = layout.row()
        if bpy.app.version[0] == 2 and bpy.app.version[1] <= 66: # TODO which version?
            row.template_list(sce, "zusi_authors", sce, "zusi_authors_index", rows = 3, prop_list = "template_list_controls")
        else:
            row.template_list("ZusiAuthorList", "", sce, "zusi_authors", sce, "zusi_authors_index", rows = 3)

        # Show add/remove operator
        col = row.column(align = True)
        col.operator("zusi_authors.add", icon = "ZOOMIN", text = "")
        col.operator("zusi_authors.remove", icon = "ZOOMOUT", text = "")

        # Show input field to change author name
        if sce.zusi_authors:
            entry = sce.zusi_authors[sce.zusi_authors_index]
            row = layout.row()
            row.prop(entry, "name")
            row.prop(entry, "id")
            row = layout.row()
            row.prop(entry, "email")
            row = layout.row()
            row.prop(entry, "effort")
            row = layout.row()
            row.prop(entry, "remarks")
