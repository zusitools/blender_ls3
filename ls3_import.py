# coding=utf-8

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import array
import os
import bpy
import logging
import struct
import mathutils
import xml.dom.minidom as dom
from . import ls_import, i18n, lsb
from .zusicommon import zusicommon
from math import pi
from mathutils import *
from bpy_extras.io_utils import unpack_list

_ = i18n.language.gettext

logger = logging.getLogger(__name__)

IMPORT_LINKED_NO = "0"
IMPORT_LINKED_AS_EMPTYS = "1"
IMPORT_LINKED_EMBED = "2"

# Converts a hex string "0AABBGGRR"/"AARRGGBB" into a tuple of a Color object and an alpha value
bgr_string_to_rgba = lambda str : (mathutils.Color((int(str[7:9], 16) / 255, int(str[5:7], 16) / 255, int(str[3:5], 16) / 255)), int(str[1:3], 16) / 255)
rgb_string_to_rgba = lambda str : (mathutils.Color((int(str[2:4], 16) / 255, int(str[4:6], 16) / 255, int(str[6:8], 16) / 255)), int(str[0:2], 16) / 255)
hex_string_to_rgba = lambda str, use_bgr_order : bgr_string_to_rgba(str) if use_bgr_order else rgb_string_to_rgba(str)

# Loads the data from a node's X, Y, and Z attributes into the given vector.
def fill_xyz_vector(node, vector):
    if node.getAttribute("X") != "":
        vector[0] = float(node.getAttribute("X"))
    if node.getAttribute("Y") != "":
        vector[1] = float(node.getAttribute("Y"))
    if node.getAttribute("Z") != "":
        vector[2] = float(node.getAttribute("Z"))

# Loads the data from a node's X, Y, Z, and W attributes into the given vector.
def fill_xyzw_vector(node, vector):
    if node.getAttribute("W") != "":
        vector[0] = float(node.getAttribute("W"))
    if node.getAttribute("X") != "":
        vector[1] = float(node.getAttribute("X"))
    if node.getAttribute("Y") != "":
        vector[2] = float(node.getAttribute("Y"))
    if node.getAttribute("Z") != "":
        vector[3] = float(node.getAttribute("Z"))

# Loads the data from a node's U and V attributes into the given vector.
# If suffix is specified, it is appended to the attribute name (e.g. suffix=2 → U2, V2)
def fill_uv_vector(node, vector, suffix = ""):
    if node.getAttribute("U" + suffix) != "":
        vector[0] = float(node.getAttribute("U" + suffix))
    if node.getAttribute("V" + suffix) != "":
        vector[1] = float(node.getAttribute("V" + suffix))

def blender_to_zusi(vector):
    return Vector((-vector[1], vector[0], vector[2]))

def zusi_to_blender(vector):
    return Vector((vector[1], -vector[0], vector[2]))

def zusi_to_blender_euler(euler):
    return Euler((euler[1], -euler[0], euler[2]), 'YXZ')

def zusi_to_blender_scale(scale):
    return Vector((scale[1], scale[0], scale[2]))

def lod_convert(lod):
    result = 0
    if (lod & 1) != 0:
        result |= 8
    if (lod & 2) != 0:
        result |= 4
    if (lod & 4) != 0:
        result |= 2
    if (lod & 8) != 0:
        result |= 1
    return result

def get_float_attr(node, name):
    attr = node.getAttribute(name)
    return float(attr) if len(attr) else 0.0

def get_int_attr(node, name):
    attr = node.getAttribute(name)
    return int(attr) if len(attr) else 0

class Ls3ImporterSettings:
    def __init__(self,
                context,
                filePath,
                fileName,
                fileDirectory,
                importFileMetadata = True,
                loadLinkedMode = IMPORT_LINKED_AS_EMPTYS,
                location = [0.0, 0.0, 0.0], # in Blender coords
                rotation = [0.0, 0.0, 0.0], # in Blender coords
                scale = [1.0, 1.0, 1.0],    # in Blender coords
                lod_bit = 15,
                parent = None,
                ):
        self.context = context
        self.filePath = filePath
        self.fileName = fileName
        self.fileDirectory = fileDirectory
        self.importFileMetadata = importFileMetadata
        self.loadLinkedMode = loadLinkedMode
        self.location = location
        self.rotation = rotation
        self.scale = scale
        self.lod_bit = lod_bit
        self.parent = parent

class Ls3Importer:
    def __init__(self, config):
        self.config = config
        self.lsb_reader = None  # created on demand

        # Imported subsets (= Blender objects) indexed by their subset number.
        # Imported linked files (= Blender objects) indexed by the order they occur in the LS3 file.
        self.subsets = []
        self.linked_files = []
        self.object_to_animate = None

        # Last rotation vector for the currently animated subset.
        self.last_rotation = None

        # No. of current subset and anchor point
        self.subsetno = 0
        self.anchor_point_no = 0

        # Currently edited object
        self.currentobject = None

        # Currently edited mesh
        self.currentmesh = None

        # List of vertices for current mesh
        # Vertex data is stored in tuples: (x, y, z, normal_x, normal_y, normal_z, u1, v1, u2, v2)
        self.currentvertices = []

        # List of faces (vertex indices) for current mesh
        # Each item contains a tuple of three vertex indices.
        self.currentfaces = []

        self.current_meters_per_tex = [0, 0]

        # Path to Zusi data dir
        self.datapath = zusicommon.get_zusi_data_path()
        self.datapath_official = zusicommon.get_zusi_data_path_official()

        # Some nodes have to be visited in a certain order. Nodes with a level specified here
        # are visited only after all other nodes with lower or unspecified levels have been visited.
        self.work_list_level = 0
        self.work_list_levels = {
            "SubSet": 0,

            "Verknuepfte": 1,

            "MeshAnimation": 2,
            "VerknAnimation": 2,
        }

        self.warnings = []

    def visitNode(self, node):
        name = "visit" + node.nodeName + "Node"

        # Call the method "visit<node_name>Node"; if it does not exist, traverse the DOM tree recursively.
        # Normally we would just try to call it and catch an AttributeError, but this makes it really hard to
        # debug if an AttributeError is thrown *inside* the called function
        if name in dir(self):
            # If the call is due in a later work list iteration, don't call the visitX method immediately.
            if node.nodeName in self.work_list_levels:
                level = self.work_list_levels[node.nodeName]
                assert(level >= self.work_list_level)
                if level > self.work_list_level:
                    if level not in self.work_list:
                        self.work_list[level] = []
                    self.work_list[level].append(node)
                    return

            getattr(self, name)(node)
        else:
            for child in node.childNodes:
                self.visitNode(child)

    #
    # Visits a <SubSet> node.
    #
    def visitSubSetNode(self, node):
        self.currentvertices = []
        self.currentfaces = []

        # Create new mesh
        self.currentmesh = bpy.data.meshes.new(self.config.fileName + "." + str(self.subsetno))

        # Create new object
        self.currentobject = bpy.data.objects.new(self.config.fileName + "." + str(self.subsetno), self.currentmesh)
        # TODO: only when not animated
        #self.currentobject.location = self.config.location
        #self.currentobject.rotation_euler = self.config.rotation
        #self.currentobject.scale = self.config.scale
        self.currentobject.parent = self.config.parent
        bpy.context.scene.objects.link(self.currentobject)

        self.subsets.append(self.currentobject)

        # Assign material to object
        mat = bpy.data.materials.new(self.config.fileName + "." + str(self.subsetno))
        self.currentmesh.materials.append(mat)

        self.current_meters_per_tex[0] = float(node.getAttribute("MeterProTex")) if len(node.getAttribute("MeterProTex")) else 0
        self.current_meters_per_tex[1] = float(node.getAttribute("MeterProTex2")) if len(node.getAttribute("MeterProTex2")) else 0

        # Set ambient/diffuse colors of mesh
        (ambient_bgr, ambient_color) = (True, node.getAttribute("CA")) if node.hasAttribute("CA") else (False, node.getAttribute("Ca"))
        (diffuse_bgr, diffuse_color) = (True, node.getAttribute("C")) if node.hasAttribute("C") else (False, node.getAttribute("Cd"))
        (night_bgr, night_color) = (True, node.getAttribute("E")) if node.hasAttribute("E") else (False, node.getAttribute("Ce"))
        mat.zusi_night_switch_threshold = float(node.getAttribute("Nachtumschaltung")) if len(node.getAttribute("Nachtumschaltung")) else 0
        mat.zusi_day_mode_preset = node.getAttribute("NachtEinstellung") if node.hasAttribute("NachtEinstellung") else "0"

        if diffuse_color != "":
            (mat.diffuse_color, mat.alpha) = hex_string_to_rgba(diffuse_color, diffuse_bgr)
        else:
            (mat.diffuse_color, mat.alpha) = ((0, 0, 0), 1)
        mat.diffuse_intensity = 1

        if ambient_color != "":
            mat.zusi_use_ambient = True
            (mat.zusi_ambient_color, mat.zusi_ambient_alpha) = hex_string_to_rgba(ambient_color, ambient_bgr)
        else:
            mat.zusi_use_ambient = False

        if night_color != "":
            mat.zusi_use_emit = True
            (mat.zusi_emit_color, ignored) = hex_string_to_rgba(night_color, night_bgr)
            mat.diffuse_color += mat.zusi_emit_color

            if mat.diffuse_color.r > 1.0 or mat.diffuse_color.g > 1.0 or mat.diffuse_color.b > 1.0:
                mat.zusi_allow_overexposure = True
                mat.zusi_overexposure_addition = mathutils.Color((
                    max(0.0, mat.diffuse_color.r - 1),
                    max(0.0, mat.diffuse_color.g - 1),
                    max(0.0, mat.diffuse_color.b - 1)
                ))
                mat.diffuse_color = mathutils.Color((
                    min(mat.diffuse_color.r, 1.0),
                    min(mat.diffuse_color.g, 1.0),
                    min(mat.diffuse_color.b, 1.0)
                ))

            if mat.zusi_use_ambient:
                ambient_color = mat.zusi_ambient_color + mat.zusi_emit_color

                if ambient_color.r > 1.0 or ambient_color.g > 1.0 or ambient_color.b > 1.0:
                    mat.zusi_allow_overexposure = True
                    mat.zusi_overexposure_addition_ambient = mathutils.Color((
                        max(0.0, ambient_color.r - 1),
                        max(0.0, ambient_color.g - 1),
                        max(0.0, ambient_color.b - 1)
                    ))
                    mat.zusi_ambient_color = mathutils.Color((
                        min(ambient_color.r, 1.0),
                        min(ambient_color.g, 1.0),
                        min(ambient_color.b, 1.0)
                    ))
        else:
            mat.zusi_use_emit = False

        # Set some other properties
        if node.getAttribute("TypLs3") != "":
            mat.zusi_landscape_type = node.getAttribute("TypLs3")
        elif node.getAttribute("ls3Typ") != "": # older file format versions
            mat.zusi_landscape_type = node.getAttribute("ls3Typ")
        if node.getAttribute("TypGF") != "":
            mat.zusi_gf_type = node.getAttribute("TypGF")
        if node.getAttribute("Zwangshelligkeit") != "":
            mat.zusi_force_brightness = float(node.getAttribute("Zwangshelligkeit"))
        if node.getAttribute("zZoom") != "":
            mat.zusi_signal_magnification = float(node.getAttribute("zZoom"))
        if node.getAttribute("DoppeltRendern") == "1":
            mat.zusi_second_pass = True
        if node.getAttribute("zBias") != "":
            mat.offset_z = float(node.getAttribute("zBias"))

        # Visit child nodes (such as texture and vertices/faces)
        for child in node.childNodes:
            self.visitNode(child)

        # Read LSB file. This is not the filename given in the <lsb> node,
        # which serves as information only.
        if node.hasAttribute("MeshI") or node.hasAttribute("MeshV"):
            if self.lsb_reader is None:
                self.lsb_reader = lsb.LsbReader()
                lsbname = os.path.splitext(self.config.filePath)[0] + ".lsb"
                try:
                    self.lsb_reader.set_lsb_file(lsbname)
                except FileNotFoundError:
                    logger.error("Failed to open LSB file {}".format(lsbname))
                    self.lsb_reader.lsbfile = None
            if self.lsb_reader.lsbfile is not None:
                (self.currentvertices, self.currentfaces) = self.lsb_reader.read_subset_data(node)

        # Fill the mesh with verts, edges, faces
        self.currentmesh.vertices.add(len(self.currentvertices))
        self.currentmesh.loops.add(3 * len(self.currentfaces))
        self.currentmesh.polygons.add(len(self.currentfaces))

        self.currentmesh.vertices.foreach_set("co", unpack_list([(v[1], -v[0], v[2]) for v in self.currentvertices]))
        self.currentmesh.loops.foreach_set("vertex_index", unpack_list([(f[0], f[1], f[2]) for f in self.currentfaces]))

        self.currentmesh.polygons.foreach_set("loop_start", range(0, 3 * len(self.currentfaces), 3))
        self.currentmesh.polygons.foreach_set("loop_total", [3] * len(self.currentfaces))

        if bpy.app.version >= (2, 74, 0):
            self.currentmesh.create_normals_split()
            normals = []
            for f in self.currentfaces:
                for i in range(0, 3):
                    v = self.currentvertices[f[i]]
                    normals += [v[4], -v[3], v[5]]
            self.currentmesh.loops.foreach_set("normal", normals)

        # Set UV coordinates
        # Additionally, if we found a texture image in one of the child nodes, assign it to all faces
        texture_slots = self.currentmesh.materials[0].texture_slots
        for idx in range(0, min(2, len(texture_slots))):
            img = texture_slots[idx].texture.image if texture_slots[idx] else None
            uvlayer_name = "UVLayer." + str(idx+1)
            uv_texture = self.currentmesh.uv_textures.new(name = uvlayer_name)
            uv_layer = self.currentmesh.uv_layers[idx]

            if texture_slots[idx]:
                texture_slots[idx].texture_coords = 'UV'
                texture_slots[idx].uv_layer = uv_layer.name

            for faceidx, face in enumerate(self.currentfaces):
                uv_texture.data[faceidx].image = img
                for i in range(0, 3):
                    # Take UV coordinates from old facedata (from when the mesh was not optimized yet)
                    v = self.currentvertices[face[i]]
                    uv_layer.data[3 * faceidx + i].uv = [v[6 + 2 * idx], 1 - v[7 + 2 * idx]]

        # Set custom normals
        if bpy.app.version >= (2, 74, 0):
            self.currentmesh.validate(clean_customdata = False) # False in order to preserve normals stored in loops
            self.currentmesh.update(calc_edges = False)

            custom_normals = array.array('f', [0.0] * (len(self.currentmesh.loops) * 3))
            self.currentmesh.loops.foreach_get("normal", custom_normals)
            self.currentmesh.normals_split_custom_set(tuple(zip(*(iter(custom_normals),) * 3)))
            self.currentmesh.use_auto_smooth = True

        self.currentmesh.update(calc_edges = True)

        # Merge vertices that have the same coordinates
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(self.currentmesh)
        bmesh.ops.remove_doubles(bm, verts = bm.verts[:], dist = 0.0001)
        bm.to_mesh(self.currentmesh)
        bm.free()

        self.subsetno += 1

    # Visits a <RenderFlags> node
    def visitRenderFlagsNode(self, node):
        if node.getAttribute("TexVoreinstellung") != "":
            self.currentmesh.materials[0].zusi_texture_preset = node.getAttribute("TexVoreinstellung")
            self.currentmesh.materials[0].zusi_second_pass &= self.currentmesh.materials[0].zusi_texture_preset == '4'

    # Visits an <Info> node
    def visitInfoNode(self, node):
        if self.config.importFileMetadata:
            if node.getAttribute("ObjektID") != "":
                bpy.context.scene.zusi_object_id = int(node.getAttribute("ObjektID"))
            if node.getAttribute("Lizenz") != "":
                bpy.context.scene.zusi_license = node.getAttribute("Lizenz")
            bpy.context.scene.zusi_description = node.getAttribute("Beschreibung")

        for child in node.childNodes:
            self.visitNode(child)

    #
    # Visits an <AutorEintrag> node
    #
    def visitAutorEintragNode(self, node):
        if self.config.importFileMetadata:
            author = None
            for a in bpy.context.scene.zusi_authors:
                if a.id != 0 and node.getAttribute("AutorID") != "" and int(node.getAttribute("AutorID")) != a.id:
                    continue
                if a.name != "" and node.getAttribute("AutorName") != a.name:
                    continue
                if a.email != "" and node.getAttribute("AutorEmail") != a.email:
                    continue
                if a.remarks != "" and node.getAttribute("AutorBemerkung") != a.remarks:
                    continue
                if node.getAttribute("AutorLizenz") != "" and a.license != node.getAttribute("AutorLizenz"):
                    continue

                author = a
                break

            if author is None:
                author = bpy.context.scene.zusi_authors.add()

            if node.getAttribute("AutorID") != "":
                author.id = int(node.getAttribute("AutorID"))
            if node.getAttribute("AutorAufwand") != "":
                author.effort += float(node.getAttribute("AutorAufwand"))
            if node.getAttribute("AutorAufwandStunden") != "":
                author.effort_hours += float(node.getAttribute("AutorAufwandStunden"))
            if node.getAttribute("AutorName") != "":
                author.name = node.getAttribute("AutorName")
            if node.getAttribute("AutorEmail") != "":
                author.email = node.getAttribute("AutorEmail")
            if node.getAttribute("AutorBeschreibung") != "":
                author.remarks = node.getAttribute("AutorBeschreibung")
            license = node.getAttribute("AutorLizenz")
            try:
                author.license = node.getAttribute("AutorLizenz")
            except TypeError:
                author.license = "0"

    #
    # Visits a <Verknuepfte> node.
    #
    def visitVerknuepfteNode(self, node):
        if self.config.loadLinkedMode == IMPORT_LINKED_NO:
            return

        if self.config.loadLinkedMode == IMPORT_LINKED_EMBED \
                and node.getAttribute("LODbit") != "" \
                and (self.config.lod_bit & int(node.getAttribute("LODbit"))) == 0:
            return

        try:
            dateinode = [x for x in node.childNodes if x.nodeName == "Datei"][0] #may raise IndexError
            dateiname = zusicommon.resolve_file_path(dateinode.getAttribute("Dateiname"),
                self.config.fileDirectory, self.datapath, self.datapath_official)
            loc = [0.0] * 3
            rot = [0.0] * 3
            scale = [1.0] * 3

            loc_node = [x for x in node.childNodes if x.nodeName == "p"]
            rot_node = [x for x in node.childNodes if x.nodeName == "phi"]
            scale_node = [x for x in node.childNodes if x.nodeName == "sk"]

            if len(loc_node) > 0:
                fill_xyz_vector(loc_node[0], loc)
            if len(rot_node) > 0:
                fill_xyz_vector(rot_node[0], rot)
            if len(scale_node) > 0:
                fill_xyz_vector(scale_node[0], scale)

            # Transform location and rotation into Blender coordinates
            loc = zusi_to_blender(loc)
            rot = zusi_to_blender_euler(rot)
            scale = zusi_to_blender_scale(scale)

            (directory, filename) = os.path.split(dateiname)

            empty = bpy.data.objects.new("%s_%s.%03d" % (self.config.fileName, filename, len(self.linked_files) + 1), None)
            empty.location = loc
            empty.rotation_euler = rot
            empty.rotation_mode = rot.order
            empty.scale = scale
            empty.parent = self.config.parent

            empty.zusi_link_file_name_realpath = dateiname
            empty.zusi_link_group = node.getAttribute("GruppenName")
            empty.zusi_link_visible_from = get_float_attr(node, "SichtbarAb")
            empty.zusi_link_visible_to = get_float_attr(node, "SichtbarBis")
            empty.zusi_link_preload_factor = get_float_attr(node, "Vorlade")
            empty.zusi_link_radius = get_int_attr(node, "BoundingR")
            empty.zusi_link_forced_brightness = get_float_attr(node, "Helligkeit")
            empty.zusi_link_lod = lod_convert(get_int_attr(node, "LODbit"))

            flags = get_int_attr(node, "Flags")
            empty.zusi_link_is_tile = flags & 4 != 0
            empty.zusi_link_is_detail_tile = flags & 32 != 0
            empty.zusi_link_is_billboard = flags & 8 != 0
            empty.zusi_link_is_readonly = flags & 16 != 0

            self.config.context.scene.objects.link(empty)
            self.linked_files.append(empty)

            if self.config.loadLinkedMode == IMPORT_LINKED_EMBED:
                if filename.lower().endswith("ls"):
                    settings = ls_import.LsImporterSettings(
                        self.config.context,
                        dateiname,
                        filename,
                        directory,
                        self.config.loadLinkedMode,
                        (0, 0, 0),
                        (0, 0, 0),
                        empty
                    )
                    ls_import.LsImporter(settings).import_ls()
                else:
                    settings = Ls3ImporterSettings(
                        self.config.context,
                        dateiname,
                        filename,
                        directory,
                        self.config.importFileMetadata,
                        self.config.loadLinkedMode,
                        [loc[x] + self.config.location[x] for x in [0,1,2]],
                        [rot[x] + self.config.rotation[x] for x in [0,1,2]],
                        [scale[x] * self.config.scale[x] for x in [0,1,2]],
                        self.config.lod_bit,
                        empty,
                    )
                    ls3importer = Ls3Importer(settings)
                    ls3importer.import_ls3()
                    self.warnings.extend(ls3importer.warnings)
            else:
                empty.zusi_is_linked_file = True
        except(IndexError):
            pass

    #
    # Visits an <Ankerpunkt> node.
    #
    def visitAnkerpunktNode(self, node):
        self.anchor_point_no += 1
        empty = bpy.data.objects.new("%s_AnchorPoint.%03d" % (self.config.fileName, self.anchor_point_no), None)
        empty.empty_draw_type = 'ARROWS'
        empty.zusi_is_anchor_point = True

        if node.getAttribute("AnkerKat"):
            empty.zusi_anchor_point_category = node.getAttribute("AnkerKat")
        if node.getAttribute("AnkerTyp"):
            try:
                empty.zusi_anchor_point_type = node.getAttribute("AnkerTyp")
            except TypeError:
                pass
        if node.getAttribute("Beschreibung"):
            empty.zusi_anchor_point_description = node.getAttribute("Beschreibung")

        loc = [0.0]*3
        rot = [0.0]*3

        for n in node.childNodes:
            if n.nodeName == "Datei":
                if n.getAttribute("Dateiname"):
                    entry = empty.zusi_anchor_point_files.add()
                    entry.name_realpath = zusicommon.resolve_file_path(n.getAttribute("Dateiname"),
                        self.config.fileDirectory, self.datapath, self.datapath_official)
            elif n.nodeName == "p":
                fill_xyz_vector(n, loc)
            elif n.nodeName == "phi":
                fill_xyz_vector(n, rot)

        loc = zusi_to_blender(loc)
        rot = zusi_to_blender_euler(rot)

        empty.location = loc
        empty.rotation_euler = rot
        empty.rotation_mode = rot.order
        empty.parent = self.config.parent
        bpy.context.scene.objects.link(empty)

    #
    # Visits a <MeshAnimation> node.
    #
    def visitMeshAnimationNode(self, node):
        self.last_rotation = None
        ani_index = node.getAttribute("AniIndex")
        if ani_index == "":
            ani_index = 0
        else:
            ani_index = int(ani_index)

        if ani_index < 0 or ani_index >= len(self.subsets):
            self.object_to_animate = None
            return

        self.object_to_animate = self.subsets[ani_index]

        for child in node.childNodes:
            self.visitNode(child)

    #
    # Visits a <VerknAnimation> node.
    #
    def visitVerknAnimationNode(self, node):
        self.last_rotation = None
        ani_index = node.getAttribute("AniIndex")
        if ani_index == "":
            ani_index = 0
        else:
            ani_index = int(ani_index)

        if ani_index < 0 or ani_index >= len(self.linked_files):
            self.object_to_animate = None
            return

        self.object_to_animate = self.linked_files[ani_index]

        for child in node.childNodes:
            self.visitNode(child)

    #
    # Visits an <AniPunkt> node.
    #
    def visitAniPunktNode(self, node):
        ob = self.object_to_animate
        if ob is None:
            return

        if ob.animation_data is None:
            ob.animation_data_create()
        if ob.animation_data.action is None:
            ob.animation_data.action = bpy.data.actions.new(
                ob.name + "Action")

        # Make sure all FCurves are present on the Action.
        fcurves_by_datapath = dict([((curve.data_path, curve.array_index), curve)
            for curve in ob.animation_data.action.fcurves])
        for datapath in ["location", "rotation_euler"]:
            for idx in range(0, 3):
                if (datapath, idx) not in fcurves_by_datapath:
                    fcurves_by_datapath[(datapath, idx)] = \
                        ob.animation_data.action.fcurves.new(datapath, idx)

        # Get X coordinate of control point.
        ani_zeit = node.getAttribute("AniZeit")
        if ani_zeit == "":
            ani_zeit = 0
        else:
            ani_zeit = float(ani_zeit)

        controlpoint_x = self.config.context.scene.frame_start + \
            (ani_zeit * (self.config.context.scene.frame_end - self.config.context.scene.frame_start))

        # Get location and rotation information.
        loc_vector = mathutils.Vector((0.0, 0.0, 0.0))
        rot_quaternion = mathutils.Quaternion((0.0, 0.0, 0.0, 0.0))

        loc_nodes = [x for x in node.childNodes if x.nodeName == "p"]
        rot_nodes = [x for x in node.childNodes if x.nodeName == "q"]

        if len(loc_nodes):
            fill_xyz_vector(loc_nodes[0], loc_vector)
            loc_vector = zusi_to_blender(loc_vector)
        if len(rot_nodes):
            fill_xyzw_vector(rot_nodes[0], rot_quaternion)

        if self.last_rotation is None:
            rot_euler = rot_quaternion.to_euler('XYZ')
        else:
            rot_euler = rot_quaternion.to_euler('XYZ', self.last_rotation)
        rot_euler = zusi_to_blender_euler(rot_euler)
        self.last_rotation = rot_euler

        # Write keyframe control points.
        fcurves_by_datapath[("location", 0)].keyframe_points.insert(controlpoint_x, loc_vector.x + ob.location[0]).interpolation = "LINEAR"
        fcurves_by_datapath[("location", 1)].keyframe_points.insert(controlpoint_x, loc_vector.y + ob.location[1]).interpolation = "LINEAR"
        fcurves_by_datapath[("location", 2)].keyframe_points.insert(controlpoint_x, loc_vector.z + ob.location[2]).interpolation = "LINEAR"

        fcurves_by_datapath[("rotation_euler", 0)].keyframe_points.insert(controlpoint_x, rot_euler.x + ob.rotation_euler[0]).interpolation = "LINEAR"
        fcurves_by_datapath[("rotation_euler", 1)].keyframe_points.insert(controlpoint_x, rot_euler.y + ob.rotation_euler[1]).interpolation = "LINEAR"
        fcurves_by_datapath[("rotation_euler", 2)].keyframe_points.insert(controlpoint_x, rot_euler.z + ob.rotation_euler[2]).interpolation = "LINEAR"

    #
    # Visits a <Vertex> node.
    #
    def visitVertexNode(self, node):
        loc_nodes = [x for x in node.childNodes if x.nodeName == "p"]
        nor_nodes = [x for x in node.childNodes if x.nodeName == "n"]

        loc = [0.0] * 3
        nor = [0.0] * 3
        uv1 = [0.0] * 2
        uv2 = [0.0] * 2

        if len(loc_nodes) > 0:
            fill_xyz_vector(loc_nodes[0], loc)
        if len(nor_nodes) > 0:
            fill_xyz_vector(nor_nodes[0], nor)
        fill_uv_vector(node, uv1)
        fill_uv_vector(node, uv2, "2")

        # Add new vertex. (x,y,z) coordinates are calculated as (y, -x, z) from Zusi coordinates
        # to fit the Blender coordinate system
        self.currentvertices.append((loc + nor + uv1 + uv2))

    #
    # Visits a <Face> node.
    #
    def visitFaceNode(self, node):
        # - Split the value of the "i" attribute by ";"
        # - Convert the values to integers
        # - Convert this to a tuple
        # - As above, reverse vertex order for Blender to get the normals correct
        self.currentfaces.append(tuple(map(int, node.getAttribute("i").rstrip(";").split(";")))[::-1])

    #
    # Visits a <Textur> node.
    #
    def visitTexturNode(self, node):
        try:
            dateinode = [x for x in node.childNodes if x.nodeName == "Datei"][0] # may raise IndexError

            # Add texture to current object
            mat = self.currentmesh.materials[0]
            slotidx = sum(s is not None for s in mat.texture_slots)

            imgpath = zusicommon.resolve_file_path(dateinode.getAttribute("Dateiname"),
                    self.config.fileDirectory, self.datapath, self.datapath_official) # may raise RuntimeError
            existing_images = [i for i in bpy.data.images if bpy.path.abspath(i.filepath) == bpy.path.abspath(imgpath)]
            img = existing_images[0] if len(existing_images) else bpy.data.images.load(imgpath)
            tex = bpy.data.textures.new(self.config.fileName + "." + str(self.subsetno),  type='IMAGE')
            tex.image = img

            texslot = mat.texture_slots.create(slotidx)
            texslot.texture = tex
            texslot.texture_coords = 'UV'
            texslot.blend_type = 'COLOR'

            if slotidx < 2:
                tex.zusi_meters_per_texture = self.current_meters_per_tex[slotidx]

        except(IndexError,  RuntimeError):
            pass

    def read_effort_from_expense_xml(self, root):
        print(root)
        for child in root.firstChild.childNodes:
            if child.nodeName != 'Info':
                continue
            info_node = child
            break
        else:
            return

        for child in info_node.childNodes:
            if child.nodeName != 'AutorEintrag':
                continue
            if child.getAttribute('AutorAufwand') == "":
                continue
            effort = float(child.getAttribute("AutorAufwand"))
            if not effort:
                continue
            author_id = 0 if child.getAttribute('AutorID') == "" else float(child.getAttribute("AutorID"))

            for a in bpy.context.scene.zusi_authors:
                if a.id == author_id:
                    a.effort = effort

    def work_list_insert(level, node):
        assert level >= self.work_list_level
        if level == self.work_list_level:
            return True
        else:
            self.work_list.get(level, []).append(node)
            return False

    def import_ls3(self):
        self.subsetno = 0
        (shortName, ext) = os.path.splitext(self.config.fileName)
        logger.info("Opening LS3 file {}".format(self.config.filePath))
        self.lsb_reader = None

        # Open the file as bytes, else a Unicode BOM at the beginning of the file could confuse the XML parser.
        with open(self.config.filePath, "rb") as fp:
            with dom.parse(fp) as xml:
                self.work_list = { 0: [xml.firstChild] }
                while len(self.work_list.keys()):
                    least_key = min(self.work_list.keys())
                    self.work_list_level = least_key
                    for node in self.work_list[least_key]:
                        self.visitNode(node)
                    del self.work_list[least_key]

        if self.config.importFileMetadata:
            try:
                with open(self.config.filePath + '.expense.xml', "rb") as fp:
                    self.read_effort_from_expense_xml(dom.parse(fp))
            except FileNotFoundError:
                pass

        return self.subsets[0] if len(self.subsets) else None
