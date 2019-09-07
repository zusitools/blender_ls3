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
    'name': 'Zusi Scenery Format (.ls3)',
    'author': 'Johannes',
    'version': (1, 0, 9),
    'blender': (2, 66, 0),
    'location': 'File > Import -> Zusi Scenery (.ls3) / File -> Export > Zusi Scenery (.ls3)',
    'description': 'Import and export files from/to the Zusi Scenery format (.ls3)',
    'category': 'Import-Export',
    'wiki_url': 'http://zusitools.github.io/blender_ls3/',
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
    if 'i18n' in locals():
        imp.reload(i18n)
 
import bpy
import os
import logging
from bpy.props import *
from . import zusiprops, zusicommon
from .zusicommon import zusicommon
try:
    from . import zusiconfig
except:
    pass
from . import ls3_export
from . import i18n
from bpy_extras.io_utils import ExportHelper, ImportHelper
from math import pi
import xml.etree.ElementTree as ET

_ = i18n.language.gettext

logLevel = logging.INFO

logger = logging.getLogger(__name__)
logger.setLevel(logLevel)
logger.propagate = False

if not logger.hasHandlers():
    ch = logging.StreamHandler()
    ch.setLevel(logLevel)
    logger.addHandler(ch)

# A setting to define whether to export a given variant.
class ZusiFileVariantExportSetting(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = _("Variant ID"),
        description = _("ID of the variant")
    )
    export = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = _("Export this variant")
    )
    template_list_controls = StringProperty(
        default="export",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiFileVariantExportSetting)

class ZusiFileVariantExportSettingList(zusiprops.CheckBoxList, bpy.types.UIList):
    def get_property_name(self):
        return "export"
    
    def get_property_value(self, item):
        return item.export
    
    def get_item_text(self, item):
        return str(item.name)

# A setting to define whether to show a given variant.
class ZusiFileVariantVisibilitySetting(bpy.types.PropertyGroup):
    variant_id = bpy.props.IntProperty(
        name = _("Variant ID"),
        description = _("ID of the variant")
    )
    visible = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = _("Show this variant")
    )
    template_list_controls = StringProperty(
        default="visible",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiFileVariantVisibilitySetting)

# A setting to define whether to import a given LOD
class ZusiLodImportSetting(bpy.types.PropertyGroup):
    lod_bit = bpy.props.IntProperty(
        name = _("LOD bit")
    )
    imp = bpy.props.BoolProperty(
        name = "", # for display in template_list
        description = _("Import this LOD"),
        default = True
    )
    template_list_controls = StringProperty(
        default="imp",
        options={"HIDDEN"}
    )

bpy.utils.register_class(ZusiLodImportSetting)

class ZusiLodImportSettingList(zusiprops.CheckBoxList, bpy.types.UIList):
    def get_property_name(self):
        return "imp"
    
    def get_property_value(self, item):
        return item.imp
    
    def get_item_text(self, item):
        return str(item.name)

load_linked_modes = [
    ("0", _("Don't import"), ""),
    ("1", _("Import as links"), ""),
    ("2", _("Embed"), ""),
]

# ---
# Import menu
# ---

class IMPORT_OT_ls(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.ls"
    bl_description = _('Import from Zusi 2 Scenery file format (.ls)')
    bl_label = _("Import LS")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"

    filename_ext = ".ls"
    filter_glob = StringProperty(default="*.ls", options={'HIDDEN'})

    # These properties have to be all lowercase and are assigned by the file selector
    files = bpy.props.CollectionProperty(type = bpy.types.OperatorFileListElement, options = {'HIDDEN'})
    directory = bpy.props.StringProperty()

    loadLinkedMode = bpy.props.EnumProperty(
        name = _("Load linked files"),
        description = _("Import files that are linked in the LS file"),
        items = load_linked_modes,
        default = "1"
    )

    def draw(self, context):
        self.layout.prop(self, "loadLinkedMode")

    def execute(self, context):
        from . import ls_import
        for f in self.files:
            settings = ls_import.LsImporterSettings(
                context,
                os.path.join(self.properties.directory, f.name),
                f.name,
                self.properties.directory,
                self.properties.loadLinkedMode,
            )

            importer = ls_import.LsImporter(settings)
            importer.import_ls()
        return {'FINISHED'}

class IMPORT_OT_ls3(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.ls3"
    bl_description = _('Import from Zusi Scenery file format (.ls3)')
    bl_label = _("Import LS3")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
 
    filename_ext = ".ls3"
    filter_glob = StringProperty(default="*.ls3", options={'HIDDEN'})
 
    # These properties have to be all lowercase and are assigned by the file selector
    files = bpy.props.CollectionProperty(type = bpy.types.OperatorFileListElement, options = {'HIDDEN'})
    directory = bpy.props.StringProperty()

    importFileMetadata = bpy.props.BoolProperty(
        name = _("Load author information"),
        description = _("Insert author information from the imported file into the .blend file"),
        default = False
    )

    loadLinkedMode = bpy.props.EnumProperty(
        name = _("Load linked files"),
        description = _("Import files that are linked in the LS3 file"),
        items = load_linked_modes,
        default = "1"
    )

    lod_import_setting = bpy.props.CollectionProperty(
        name = _("LODs to import"),
        type = ZusiLodImportSetting
    )

    lod_import_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "importFileMetadata")
        layout.prop(self, "loadLinkedMode")

        layout.label(_("Import LODs (only embedded linked files)"))
        row = layout.row()
        row.enabled = self.properties.loadLinkedMode == "2"
        row.template_list("ZusiLodImportSettingList", "", self, "lod_import_setting", self, "lod_import_setting_index")

    def execute(self, context):
        from . import ls3_import
        for f in self.files:
            settings = ls3_import.Ls3ImporterSettings(
                context,
                os.path.join(self.properties.directory, f.name),
                f.name,
                self.properties.directory,
                self.properties.importFileMetadata,
                self.properties.loadLinkedMode,
                lod_bit = sum([s.lod_bit for s in self.properties.lod_import_setting if s.imp])
            )

            importer = ls3_import.Ls3Importer(settings)
            importer.import_ls3()
            if len(importer.warnings) > 0:
                self.report({'WARNING'}, os.linesep.join(importer.warnings))
        return {'FINISHED'}
 
    def invoke(self, context, event):
        if not len(self.properties.lod_import_setting):
            for i in range(0, 4):
                setting = self.properties.lod_import_setting.add()
                setting.name = _("LOD %d") % i
                setting.lod_bit = 2**(3 - i)

        return super().invoke(context, event)

class OBJECT_OT_embed_linked(bpy.types.Operator):
    bl_idname = "zusi_linked_file.embed"
    bl_label = _('Embed linked file')
    bl_description = _('Load the contents of the linked file specified at this object and insert them as children of this object')
    bl_options = {'UNDO', 'INTERNAL'}

    ob = bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        ob = bpy.data.objects[self.ob]
        path = bpy.path.abspath(ob.zusi_link_file_name_realpath)

        if not os.path.exists(path):
            self.report({'ERROR'}, _("File %s not found") % path)
            return {'CANCELLED'}

        (directory, filename) = os.path.split(path)
        if filename.lower().endswith(".ls"):
            from . import ls_import
            settings = ls_import.LsImporterSettings(
                context,
                path,
                filename,
                directory,
                ls_import.IMPORT_LINKED_AS_EMPTYS,
                parent = ob,
                parent_is_ls3 = True,
            )
            importer = ls_import.LsImporter(settings)
            importer.import_ls()
            ob.zusi_is_linked_file = False
        elif filename.lower().endswith(".ls3"):
            from . import ls3_import
            settings = ls3_import.Ls3ImporterSettings(
                context,
                path,
                filename,
                directory,
                False,
                ls3_import.IMPORT_LINKED_AS_EMPTYS,
                parent = ob,
            )
            importer = ls3_import.Ls3Importer(settings)
            importer.import_ls3()
            ob.zusi_is_linked_file = False

        return {'FINISHED'}

# ---
#    Export menu
# ---
 
class EXPORT_OT_ls3(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.ls3"
    bl_description = _('Export to Zusi Scenery file format (.ls3)')
    bl_label = _("Export LS3")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
 
    # From ExportHelper. Filter filenames.
    filename_ext = ".ls3"
    filter_glob = StringProperty(default="*.ls3", options={'HIDDEN'})

    had_no_author_info = BoolProperty(default=False, options={'HIDDEN'})

    # These properties have to be all lowercase and are assigned by the file selector
    filepath = bpy.props.StringProperty()
    filename = bpy.props.StringProperty()
    directory = bpy.props.StringProperty()

    exportSelected = bpy.props.EnumProperty(
        name = _("Export mode"),
        description = _("Choose which objects to export"),
        items = [
            ("0", _("All objects"), ""),
            ("1", _("Selected objects"), ""),
            ("2", _("Subsets containing selected objects"), ""),
            ("4", _("Objects on visible layers"), ""),
        ],
        default = ls3_export.get_exporter_setting("exportSelected"),
    )

    exportAnimations = bpy.props.BoolProperty(
        name = _("Export animations"),
        description = _("Export animations from keyframes (this might create/overwrite additional files)"),
        default = ls3_export.get_exporter_setting("exportAnimations")
    )

    optimizeMesh = bpy.props.BoolProperty(
        name = _("Optimize mesh"),
        description = _("Optimize meshes in the exported file (this will not modify any meshes in the Blender file)"),
        default = ls3_export.get_exporter_setting("optimizeMesh"),
    )

    maxCoordDelta = bpy.props.FloatProperty(
        name = _("Max. distance"),
        description = _("Maximum distance between two vertices to be merged"),
        default = ls3_export.get_exporter_setting("maxCoordDelta"),
        min = 0.0
    )

    maxUVDelta = bpy.props.FloatProperty(
        name = _("Max. UV distance"),
        description = _("Maximum UV coordinate distance between two vertices to be merged"),
        default = ls3_export.get_exporter_setting("maxUVDelta"),
        min = 0.0,
        max = 1.0
    )

    maxNormalAngle = bpy.props.FloatProperty(
        name = _("Max. normal angle"),
        description = _("Maximum angle (degrees) between the normal vectors of two vertices to be merged"),
        default = ls3_export.get_exporter_setting("maxNormalAngle"),
        min = 0.0,
        max = 360.0
    )

    variant_export_setting = bpy.props.CollectionProperty(
        name = _("Variants to export"),
        description = _("Choose which variants to export"),
        type = ZusiFileVariantExportSetting
    )

    variant_export_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout
        files = self.get_exporter(context).get_files()

        if not context.scene.zusi_authors or len(context.scene.zusi_authors) == 0:
            self.had_no_author_info = True
            layout.label(_("No author information entered"), icon='ERROR')
            layout.operator("zusi_authors.add_default")
        elif self.had_no_author_info:
            layout.label(_("Author information added"), icon='INFO')
            box = layout.box()
            box.label(_("Name: %s" % context.scene.zusi_authors[0].name))
            box.label(_("E-mail: %s" % context.scene.zusi_authors[0].email))

        materials_with_intensity_less_1 = [s.identifier.material for f in files for s in f.subsets
            if s.identifier.material is not None and s.identifier.material.diffuse_intensity < 1.]
        if len(materials_with_intensity_less_1):
            layout.label(_("Materials with diffuse intensity < 1"), icon='ERROR')
            box = layout.box()
            for m in materials_with_intensity_less_1:
                box.label(text = m.name)

        layout.label(_("Variants (leave empty to export all)"))

        if len(context.scene.zusi_variants) > 0:
            num_rows = min(5, len(self.properties.variant_export_setting))
            layout.template_list("ZusiFileVariantExportSettingList", "", self, "variant_export_setting", self, "variant_export_setting_index", rows = num_rows)
        else:
            box = layout.box()
            box.label(_("Variants can be defined in the Scene settings."))

        layout.prop(self, "exportSelected", text = "Export")
        layout.prop(self, "exportAnimations")
        if self.properties.exportAnimations:
            if len(files) > 1:
                layout.label(text=_("The following files will be overwritten:"))
                box = layout.box()
                (name, ext) = os.path.splitext(self.properties.filename)
                for file in files:
                    if file.filename != self.properties.filename:
                        box.label(text = file.filename)
        layout.prop(self, "optimizeMesh")
        row = layout.row(align = False)
        row.alignment = "RIGHT"
        col = row.column()
        col.enabled = self.properties.optimizeMesh
        col.prop(self, "maxCoordDelta")
        col.prop(self, "maxUVDelta")
        col.prop(self, "maxNormalAngle")

    def get_exporter(self, context):
        if self.properties.exportSelected == '4':  # Visible layers
            is_on_visible_layer = lambda ob: any((a and b) for a, b in zip(ob.layers, context.scene.layers))
            selectedObjects = [ob.name for ob in context.scene.objects if is_on_visible_layer(ob)]
            self.properties.exportSelected = '1'  # Selected objects
        else:
            selectedObjects = [ob.name for ob in context.selected_objects]

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
            selectedObjects,
        )
        
        return ls3_export.Ls3Exporter(settings)

    def execute(self, context):
        is_editmode = (context.mode == 'EDIT_MESH')
        if is_editmode:
            bpy.ops.object.editmode_toggle()
        self.get_exporter(context).export_ls3()
        if is_editmode:
            bpy.ops.object.editmode_toggle()
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

        return super().invoke(context, event)

class EXPORT_OT_ls3_batch(bpy.types.Operator):
    bl_idname = "export_scene.ls3_batch"
    bl_description = _('Batch export to Zusi Scenery file format (.ls3)')
    bl_label = _("Batch export LS3")
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"

    def execute(self, context):
        from . import ls3_export

        batch_export_settings = {}
        try:
            root = ET.parse(os.path.join(os.path.dirname(__file__), "batchexport_settings.xml"))
            for setting_node in root.findall("./setting"):
                if "blendfile" not in setting_node.attrib:
                    logger.warning('Warning: <setting> node without "blendfile" attribute')
                    continue
                exports = []
                for export_node in setting_node.findall("./export"):
                    if "ls3file" not in export_node.attrib:
                        logger.warning('Warning: <export> node without "ls3file" attribute')
                        continue
                    export_mode = "0"
                    if "exportmode" in export_node.attrib:
                        if export_node.attrib["exportmode"] == "SelectedObjects":
                            export_mode = "1"
                        elif export_node.attrib["exportmode"] == "SubsetsOfSelectedObjects":
                            export_mode = "2"
                        elif export_node.attrib["exportmode"] == "SelectedMaterials":
                            export_mode = "3"

                    variant_names = set([v.text for v in export_node.findall("./variant")])

                    exports.append((
                        [e.text for e in export_node.findall("./select")],
                        [v.id for v in context.scene.zusi_variants if v.name in variant_names],
                        export_node.attrib["ls3file"],
                        export_mode))
                batch_export_settings[setting_node.attrib["blendfile"]] = exports
        except IOError as e:
            logger.error('Error opening batchexport_settings.xml: {}'.format(e.message))
            pass

        try:
            from . import batchexport_settings as bs
            batch_export_settings.update(bs.batch_export_settings)
        except ImportError:
            pass

        if not bpy.data.is_saved:
            self.report({'ERROR'}, _("Unsaved file, no file name available"))
            return {'CANCELLED'}
        if bpy.data.filepath not in batch_export_settings:
            self.report({'ERROR'}, _("No batch export settings found for file %s") % bpy.data.filepath)
            return {'CANCELLED'}

        def runbatch():
            is_editmode = (context.mode == 'EDIT_MESH')
            if is_editmode:
                bpy.ops.object.editmode_toggle()

            for setting in batch_export_settings[bpy.data.filepath]:
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

            if is_editmode:
                bpy.ops.object.editmode_toggle()

        if True:
            runbatch()

        elif False:
            # Profiling with LineProfiler
            import line_profiler
            p = line_profiler.LineProfiler(runbatch)
            p.add_function(zusicommon.optimize_mesh)
            p.runctx('runbatch()', {}, {'runbatch': runbatch})
            p.print_stats()

        elif False:
            # Profiling with Profile
            import profile, pstats
            p = profile.Profile()
            p.runctx('runbatch()', {}, {'runbatch': runbatch})
            s = pstats.Stats(p)
            s.strip_dirs()
            s.sort_stats('cumtime')
            s.print_stats()
            s.print_callers()

        num_files = len(batch_export_settings[bpy.data.filepath])
        self.report({'INFO'}, i18n.language.ngettext("Exported %d file", "Exported %d files", num_files) % num_files)
        return {'FINISHED'}

# ---
# Show variants
# ---

class VIEW_OT_show_variants(bpy.types.Operator):
    bl_idname = "zusi.show_variants"
    bl_description = _('Show only objects that are visible in a given set of variants')
    bl_label = _("Show Variants")
    bl_options = {'REGISTER', 'UNDO'}

    variant_visibility_setting = bpy.props.CollectionProperty(
        name = _("Variants to show"),
        description = _("Choose which variants to show"),
        type = ZusiFileVariantVisibilitySetting
    )

    variant_visibility_setting_index = bpy.props.IntProperty()

    def draw(self, context):
        layout = self.layout

        layout.label(_("Variants (leave empty to show all)"))

        if len(context.scene.zusi_variants) > 0:
            layout.template_list("ZusiFileVariantVisibilityList", "", self, "variant_visibility_setting", self, "variant_visibility_setting_index")
        else:
            box = layout.box()
            box.label(_("Variants can be defined in the Scene settings."))

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
    self.layout.operator(IMPORT_OT_ls.bl_idname, text=_("Zusi 2 Scenery (.ls) ..."))
 
def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_ls3.bl_idname, text=_("Zusi Scenery (.ls3) ..."))
 
def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_ls3.bl_idname, text=_("Zusi Scenery (.ls3) ..."))

def menu_func_show_variants(self, context):
    self.layout.operator(VIEW_OT_show_variants.bl_idname, text=_("Show variants ..."))
 
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
