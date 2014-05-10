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
 
bl_info = {
    'name': 'Zusi Landscape Format (.ls3)',
    'author': 'Johannes',
    'version': (0, 1, 0),
    'blender': (2, 6, 3),
    'location': 'File > Import -> Zusi Landscape (.ls3) / File -> Export > Zusi Landscape (.ls3)',
    'description': 'Import and export files from/to the Zusi Landscape format (.ls3)',
    'category': 'Import-Export',
}
 
# To support reload properly, try to access a package var, 
# if it's there, reload everything
if "bpy" in locals():
    import imp
    if 'lsb' in locals():
        imp.reload(lsb)
    if 'ls_import' in locals():
        imp.reload(ls_import)
    if 'ls3_import' in locals():
        imp.reload(ls3_import)
    if 'ls3_export' in locals():
        imp.reload(ls3_export)
    if 'zusiprops' in locals():
        imp.reload(zusiprops)
    if 'zusicommon' in locals():
        imp.reload(zusicommon)
    if 'zusiconfig' in locals():
        imp.reload(zusiconfig)
    if 'batchexport_settings' in locals():
        imp.reload(batchexport_settings)
 
import bpy
import os
from bpy.props import *
from . import zusiprops, zusicommon
from . import ls3_export
from bpy_extras.io_utils import ExportHelper, ImportHelper
from math import pi

# A setting to define whether to export a given variant.
class ZusiFileVariantExportSetting(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = "Variant ID",
        description = "ID of the variant"
    )
    export = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = "Export this variant"
    )
    template_list_controls = StringProperty(
        default="export",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiFileVariantExportSetting)

class ZusiFileVariantExportSettingList(zusiprops.CheckBoxList):
    def get_property_name(self):
        return "export"
    
    def get_property_value(self, item):
        return item.export
    
    def get_item_text(self, item):
        return str(item.name)

# A setting to define whether to show a given variant.
class ZusiFileVariantVisibilitySetting(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = "Variant ID",
        description = "ID of the variant"
    )
    visible = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = "Show this variant"
    )
    template_list_controls = StringProperty(
        default="visible",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiFileVariantVisibilitySetting)

# A setting to define whether to import a given LOD
class ZusiLodImportSetting(bpy.types.PropertyGroup):
    lod_bit = bpy.props.IntProperty(
        name = "LOD bit"
    )
    imp = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = "Import this LOD",
        default = True
    )
    template_list_controls = StringProperty(
        default="imp",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiLodImportSetting)

class ZusiLodImportSettingList(zusiprops.CheckBoxList):
    def get_property_name(self):
        return "imp"
    
    def get_property_value(self, item):
        return item.imp
    
    def get_item_text(self, item):
        return str(item.name)

# ---
# Import menu
# ---

class IMPORT_OT_ls(bpy.types.Operator, ImportHelper):
    bl_idname = "io_import_scene.ls"
    bl_description = 'Import from Zusi 2 Landscape file format (.ls)'
    bl_label = "Import LS"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"

    filename_ext = ".ls"
    filter_glob = StringProperty(default="*.ls", options={'HIDDEN'})

    # These properties have to be all lowercase and are assigned by the file selector
    filepath = bpy.props.StringProperty()
    filename = bpy.props.StringProperty()
    directory = bpy.props.StringProperty()

    loadLinked = bpy.props.BoolProperty(
        name = "Load linked files",
        description = "Import files that are linked in the LS3 file",
        default = True
    )

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(self, "loadLinked")

    def execute(self, context):
        from . import ls_import
        settings = ls_import.LsImporterSettings(
            context,
            self.properties.filepath,
            self.properties.filename,
            self.properties.directory,
            self.properties.loadLinked,
        )

        importer = ls_import.LsImporter(settings)
        importer.import_ls()
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class IMPORT_OT_ls3(bpy.types.Operator, ImportHelper):
    bl_idname = "io_import_scene.ls3"
    bl_description = 'Import from Zusi Landscape file format (.ls3)'
    bl_label = "Import LS3"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
 
    filename_ext = ".ls3"
    filter_glob = StringProperty(default="*.ls3", options={'HIDDEN'})
 
    # These properties have to be all lowercase and are assigned by the file selector
    filepath = bpy.props.StringProperty()
    filename = bpy.props.StringProperty()
    directory = bpy.props.StringProperty()

    loadAuthorInformation = bpy.props.BoolProperty(
        name = "Load author information",
        description = "Insert author information from the imported file into the .blend file",
        default = True
    )

    loadLinked = bpy.props.BoolProperty(
        name = "Load linked files",
        description = "Import files that are linked in the LS3 file",
        default = True
    )

    lod_import_setting = bpy.props.CollectionProperty(
        name = "LODs to import",
        type = ZusiLodImportSetting
    )

    lod_import_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(self, "loadAuthorInformation")

        row = layout.row()
        row.prop(self, "loadLinked")

        layout.label("Import LODs (only linked files)")
        row = layout.row()
        row.enabled = self.properties.loadLinked
        
        if bpy.app.version[0] == 2 and bpy.app.version[1] <= 65:
            row.template_list(self, "lod_import_setting", self, "lod_import_setting_index", prop_list = "template_list_controls")
        else:
            row.template_list("ZusiLodImportSettingList", "", self, "lod_import_setting", self, "lod_import_setting_index")

    def execute(self, context):
        from . import ls3_import
        settings = ls3_import.Ls3ImporterSettings(
            context,
            self.properties.filepath,
            self.properties.filename,
            self.properties.directory,
            self.properties.loadAuthorInformation,
            self.properties.loadLinked,
            lod_bit = sum([s.lod_bit for s in self.properties.lod_import_setting if s.imp])
        )

        importer = ls3_import.Ls3Importer(settings)
        importer.import_ls3()
        return {'FINISHED'}
 
    def invoke(self, context, event):
        for i in range(0, 4):
            setting = self.properties.lod_import_setting.add()
            setting.name = "LOD" + str(i)
            setting.lod_bit = 2**(3 - i)
    
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
        
# ---
#    Export menu
# ---
 
class EXPORT_OT_ls3(bpy.types.Operator, ExportHelper):
    bl_idname = "io_export_scene.ls3"
    bl_description = 'Export to Zusi Landscape file format (.ls3)'
    bl_label = "Export LS3"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
 
    # From ExportHelper. Filter filenames.
    filename_ext = ".ls3"
    filter_glob = StringProperty(default="*.ls3", options={'HIDDEN'})

    # These properties have to be all lowercase and are assigned by the file selector
    filepath = bpy.props.StringProperty()
    filename = bpy.props.StringProperty()
    directory = bpy.props.StringProperty()

    exportSelected = bpy.props.EnumProperty(
        name = "Export mode",
        description = "Choose which objects to export",
        items = [
            ("0", "All objects", ""),
            ("1", "Selected objects", ""),
            ("2", "Subsets containing selected objects", "")
        ],
        default = ls3_export.get_exporter_setting("exportSelected"),
    )

    exportAnimations = bpy.props.BoolProperty(
        name = "Export animations",
        description = "Export animations from keyframes (this might create/overwrite additional files)",
        default = ls3_export.get_exporter_setting("exportAnimations")
    )

    optimizeMesh = bpy.props.BoolProperty(
        name = "Optimize mesh",
        description = "Optimize mesh before exporting",
        default = ls3_export.get_exporter_setting("optimizeMesh"),
    )

    maxCoordDelta = bpy.props.FloatProperty(
        name = "Max. distance",
        description = "Maximum distance between two vertices to be merged",
        default = ls3_export.get_exporter_setting("maxCoordDelta"),
        min = 0.0
    )

    maxUVDelta = bpy.props.FloatProperty(
        name = "Max. UV distance",
        description = "Maximum UV coordinate distance between two vertices to be merged",
        default = ls3_export.get_exporter_setting("maxUVDelta"),
        min = 0.0,
        max = 1.0
    )

    maxNormalAngle = bpy.props.FloatProperty(
        name = "Max. normal angle",
        description = "Maximum angle (degrees) between the normal vectors of two vertices to be merged",
        default = ls3_export.get_exporter_setting("maxNormalAngle"),
        min = 0.0,
        max = 360.0
    )

    variant_export_setting = bpy.props.CollectionProperty(
        name = "Variants to export",
        description = "Choose which variants to export",
        type = ZusiFileVariantExportSetting
    )

    variant_export_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.label("Variants (leave empty to export all)")

        if len(context.scene.zusi_variants) > 0:
            num_rows = min(5, len(self.properties.variant_export_setting))

            if bpy.app.version[0] == 2 and bpy.app.version[1] <= 65:
                layout.template_list(self, "variant_export_setting", self, "variant_export_setting_index", prop_list = "template_list_controls", rows = num_rows)
            else:
                layout.template_list("ZusiFileVariantExportSettingList", "", self, "variant_export_setting", self, "variant_export_setting_index", rows = num_rows)
        else:
            box = layout.box()
            box.label("Variants can be defined in the Scene settings.")

        row = layout.row()
        row.prop(self, "exportSelected", text = "Export")
        row = layout.row()
        row.prop(self, "exportAnimations")
        row = layout.row()
        row.prop(self, "optimizeMesh")
        row = layout.row(align = False)
        row.alignment = "RIGHT"
        col = row.column()
        col.enabled = self.properties.optimizeMesh
        col.prop(self, "maxCoordDelta")
        col.prop(self, "maxUVDelta")
        col.prop(self, "maxNormalAngle")
 
    def execute(self, context):
        settings = ls3_export.Ls3ExporterSettings(
            context,
            self.properties.filepath,
            self.properties.filename,
            self.properties.directory,
            self.properties.exportSelected,
            self.properties.exportAnimations,
            self.properties.optimizeMesh,
            self.properties.maxUVDelta,
            self.properties.maxCoordDelta,
            (self.properties.maxNormalAngle / 360) * 2 * pi,
            [setting.variant_id for setting in self.properties.variant_export_setting if setting.export == True],
            [ob.name for ob in context.selected_objects],
        )
        
        exporter = ls3_export.Ls3Exporter(settings)
        exporter.export_ls3()
        return {'FINISHED'}
 
    def invoke(self, context, event):
        # Clear variant_export_setting, else too many variants will be displayed when multiple files are
        # opened during one blender session.
        # Keep the selected variant IDs, however.
        old_selected = [setting.variant_id for setting in self.properties.variant_export_setting if setting.export]
        while len(self.properties.variant_export_setting) > 0:
            self.properties.variant_export_setting.remove(0)

        for variant in context.scene.zusi_variants:
            setting = self.properties.variant_export_setting.add()
            setting.name = variant.name
            setting.variant_id = variant.id
            setting.export = setting.variant_id in old_selected

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class EXPORT_OT_ls3_batch(bpy.types.Operator):
    bl_idname = "io_export_scene.ls3_batch"
    bl_description = 'Batch export to Zusi Landscape file format (.ls3)'
    bl_label = "Batch export LS3"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"

    def execute(self, context):
        from . import ls3_export
        try:
            from . import batchexport_settings as bs
        except ImportError:
            self.report({'ERROR'}, "Batch export settings not found")
            return {'CANCELLED'}

        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Unsaved file, no file name found")
            return {'CANCELLED'}
        if bpy.data.filepath not in bs.batch_export_settings:
            self.report({'ERROR'}, "No batch export settings found for file %s" % bpy.data.filepath)
            return {'CANCELLED'}

        for setting in bs.batch_export_settings[bpy.data.filepath]:
            (directory, filename) = os.path.split(setting[2])
        
            settings = ls3_export.Ls3ExporterSettings(
                context,
                setting[2],
                filename,
                directory,
                str(setting[3]),    # exportSelected
                ls3_export.get_exporter_setting("exportAnimations"),
                ls3_export.get_exporter_setting("optimizeMesh"),
                ls3_export.get_exporter_setting("maxUVDelta"),
                ls3_export.get_exporter_setting("maxCoordDelta"),
                ls3_export.get_exporter_setting("maxNormalAngle"),
                variantIDs = setting[1],
                selectedObjects = setting[0],
            )

            exporter = ls3_export.Ls3Exporter(settings)
            exporter.export_ls3()

        self.report({'INFO'}, "Successfully exported %d files" % len(bs.batch_export_settings[bpy.data.filepath]))
        return {'FINISHED'}

# ---
# Show variants
# ---

class VIEW_OT_show_variants(bpy.types.Operator):
    bl_idname = "zusi.show_variants"
    bl_description = 'Show only objects that are visible in a given set of variants'
    bl_label = "Show Variants"
    bl_options = {'REGISTER', 'UNDO'}

    variant_visibility_setting = bpy.props.CollectionProperty(
        name = "Variants to show",
        description = "Choose which variants to show",
        type = ZusiFileVariantVisibilitySetting
    )

    variant_visibility_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.label("Variants (leave empty to show all)")

        if len(context.scene.zusi_variants) > 0:
            if bpy.app.version[0] == 2 and bpy.app.version[1] <= 65:
                layout.template_list(self, "variant_visibility_setting", self, "variant_visibility_setting_index", prop_list = "template_list_controls")
            else:
                layout.template_list("ZusiFileVariantVisibilityList", "", self, "variant_visibility_setting", self, "variant_visibility_setting_index")
        else:
            box = layout.box()
            box.label("Variants can be defined in the Scene settings.")

    def execute(self, context):
        variantIDs = [setting.variant_id for setting in self.properties.variant_visibility_setting if setting.visible == True]
        for ob in context.scene.objects:
            ob.hide = not zusicommon.is_object_visible(ob, variantIDs)
        for mat in bpy.data.materials:
            for slot in mat.texture_slots:
                if slot and slot.texture:
                    slot.use = zusicommon.is_object_visible(slot.texture, variantIDs)
        return {'FINISHED'}

    def invoke(self, context, event):
        # see comment for EXPORT_OT_ls3.invoke
        old_selected = [setting.variant_id for setting in self.properties.variant_visibility_setting if setting.visible]
        while len(self.properties.variant_visibility_setting) > 0:
            self.properties.variant_visibility_setting.remove(0)

        for variant in context.scene.zusi_variants:
            setting = self.properties.variant_visibility_setting.add()
            setting.name = variant.name
            setting.variant_id = variant.id
            setting.visible = False

        return self.execute(context)
 
# ---
# Registration
# ---

def menu_func_import_ls(self, context):
    self.layout.operator(IMPORT_OT_ls3.bl_idname, text="Zusi 2 Landscape (.ls) ...")
 
def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_ls3.bl_idname, text="Zusi Landscape (.ls3) ...")
 
def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_ls3.bl_idname, text="Zusi Landscape (.ls3) ...")

def menu_func_show_variants(self, context):
    self.layout.operator(VIEW_OT_show_variants.bl_idname, text="Show variants ...")
 
def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import_ls)
    bpy.types.INFO_MT_file_import.append(menu_func_import)
    bpy.types.INFO_MT_file_export.append(menu_func_export)
    bpy.types.VIEW3D_MT_view.append(menu_func_show_variants)
 
def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import_ls)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)
    bpy.types.VIEW3D_MT_view.remove(menu_func_show_variants)
 
if __name__ == "__main__":
    register()
