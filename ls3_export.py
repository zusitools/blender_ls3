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
import os
import array
import struct
import xml.dom.minidom as dom
import logging
from . import zusiprops
from .zusicommon import zusicommon
from .zusi_material_wrapper import PrincipledBSDFWrapper
try:
    from . import zusiconfig
except:
    pass
from math import floor, ceil, sqrt, radians
from mathutils import *
from bpy_extras import node_shader_utils
from collections import defaultdict

logger = logging.getLogger(__name__)

# Converts a color value (of type Color) and an alpha value (value in [0..1])
# to a hex string "AARRGGBB"
rgba_to_rgb_hex_string = lambda color, alpha : "{:02X}{:02X}{:02X}{:02X}".format(*[round(x * 255) for x in [alpha, color.r, color.g, color.b]])

# Returns the length of the projection of the specified vector projected onto the XY plane.
vector_xy_length = lambda vec : sqrt(vec.x * vec.x + vec.y * vec.y)

# The default settings for the exporter
default_export_settings = {
    "exportSelected" : "4",
    "exportAnimations" : False,
    "optimizeMesh" : True,
    "maxCoordDelta" : 0.001,
    "maxUVDelta" : 0.002,
    "maxNormalAngle" : radians(10),
    "writeLsb" : True,
}

registry_export_settings = None

def get_registry_export_settings():
    result = {}
    try:
        import winreg
        values = zusicommon.read_registry_strings([
            (winreg.HKEY_CURRENT_USER, "Software\\Zusi3\\3DEditor\\Einstellungen"),
        ], set(["MeshOptimierungAbstand", "MeshOptimierungUV", "MeshOptimierungWinkel", "xmlls3Schreiben"]))
        if values is not None:
            if "MeshOptimierungAbstand" in values:
                result["maxCoordDelta"] = struct.unpack("d", values["MeshOptimierungAbstand"])[0]
            if "MeshOptimierungUV" in values:
                result["maxUVDelta"] = struct.unpack("d", values["MeshOptimierungUV"])[0]
            if "MeshOptimierungWinkel" in values:
                result["maxNormalAngle"] = struct.unpack("d", values["MeshOptimierungWinkel"])[0]
            if "xmlls3Schreiben" in values:
                result["writeLsb"] = (values["xmlls3Schreiben"] == 0)
    except Exception:
        pass

    return result

EXPORT_ALL_OBJECTS = "0"
EXPORT_SELECTED_OBJECTS = "1"
EXPORT_SUBSETS_OF_SELECTED_OBJECTS = "2"
EXPORT_SELECTED_MATERIALS = "3"
EXPORT_VISIBLE_COLLECTIONS = "4"

EPSILON = 0.00001

def debug(msg, *args, **kwargs):
    logger.debug(msg.format(*args, **kwargs))

def info(msg, *args, **kwargs):
    logger.info(msg.format(*args, **kwargs))

def warn(msg, *args, **kwargs):
    logger.warn(msg.format(*args, **kwargs))

# Returns the value with the given key in the default_export_settings dictionary in zusiconfig.py,
# the appropriate value from the Windows Registry or the default value specified above if an error occurs.
def get_exporter_setting(key):
    try:
        return zusiconfig.default_export_settings[key]
    except Exception:
        try:
            global registry_export_settings
            if registry_export_settings is None:
                registry_export_settings = get_registry_export_settings()
            return registry_export_settings[key]
        except Exception:
            return default_export_settings[key]

def fill_node_xyz(node, x, y, z, default = 0):
    if abs(x - default) > EPSILON:
        node.setAttribute("X", str(x))
    if abs(y - default) > EPSILON:
        node.setAttribute("Y", str(y))
    if abs(z - default) > EPSILON:
        node.setAttribute("Z", str(z))

def fill_node_wxyz(node, w, x, y, z, default = 0):
    fill_node_xyz(node, x, y, z, default = default)
    if abs(w - default) > EPSILON:
        node.setAttribute("W", str(w))

def clamp_color(color):
    """Returns a clamped version (RGB components between 0.0 and 1.0) of a color."""
    return Color((
        min(1.0, max(0.0, color.r)),
        min(1.0, max(0.0, color.g)),
        min(1.0, max(0.0, color.b))
    ))

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

def zusi_rotation_from_quaternion(quat, euler_compat=None):
    # Blender uses extrinsic Euler rotation (the order can be specified).
    # Zusi uses intrinsic ZYX Euler rotation, which corresponds to extrinsic XYZ Euler rotation,
    # and because the X and Y axes are swapped compared to Blender, this corresponds to YXZ rotation
    # in Blender.
    # euler_compat is given in Zusi coordinates as well (i.e. axis swapped)
    rot = quat.to_euler('YXZ', Euler((euler_compat.y, -euler_compat.x, euler_compat.z))) if euler_compat is not None else quat.to_euler('YXZ')
    return Euler((-rot.y, rot.x, rot.z))

def get_used_materials_for_object(ob):
    """Returns a set of pairs (material index, material) for all materials used (i.e. assigned to any face) in the given object."""
    if ob.data and (len(ob.material_slots) > 0):
        if ob.type == 'MESH':
            elements = ob.data.polygons
        elif ob.type == 'CURVE':
            elements = ob.data.splines
        used_material_indices = set(elem.material_index for elem in elements)
        return set((i, ob.material_slots[i].material) for i in used_material_indices if ob.material_slots[i].material is not None and ob.material_slots[i].name != 'Unsichtbar')
    else:
        return set([(0, None)])

# Returns a list of all descendants of the given object.
def get_children_recursive(ob):
    result = set(ob.children)
    for child in ob.children:
        result |= get_children_recursive(child)
    return result

def get_ani_description(ani_id):
    try:
        # Animation descriptions are always in German to increase consistency
        # and facilitating the use of exported objects in other files.
        return {
            "0"  : 'Undefiniert/signalgesteuert',
            "1"  : 'Zeitlich kontinuierlich',
            "2"  : 'Geschwindigkeit (angetrieben, gebremst)',
            "3"  : 'Geschwindigkeit (gebremst)',
            "4"  : 'Geschwindigkeit (angetrieben)',
            "5"  : 'Geschwindigkeit',
            "6"  : 'Gleiskrümmung Fahrzeuganfang',
            "7"  : 'Gleiskrümmung Fahrzeugende',
            "8"  : 'Stromabnehmer A',
            "9"  : 'Stromabnehmer B',
            "10" : 'Stromabnehmer C',
            "11" : 'Stromabnehmer D',
            "12" : 'Türen rechts',
            "13" : 'Türen links',
            "14" : 'Neigetechnik',
        }[ani_id]
    except KeyError:
        return ""

def is_lt_name(a, b):
    """Returns a.name < b.name, taking into account None values (which are smaller than all other values)."""
    if b is None:
        return False
    if a is None:
        return True
    else:
        return a.name < b.name

class Keyframe:
    """A keyframe of a Zusi animation (corresponding to an <AniPunkt> node)."""
    def __init__(self, time, loc, rotation_quaternion):
        self.time = time
        self.loc = loc
        self.rotation_quaternion = rotation_quaternion

class Ls3File:
    """Stores all the things that later go into one LS3 file, as well as the relation to its parent file."""
    def __init__(self):
        self.is_main_file = False
        """Whether this is the main exported file whose file name is specified by the user."""

        self.must_export = True 
        """Whether this file must be processed. Set this to False for links to existing files."""

        self.filename = ""
        """The file name of this file. For files with must_export = False, this does not contain the path."""

        self.subsets = []
        """A list of Ls3Subset objects contained in this file."""

        self.linked_files = []
        """A list of Ls3File objects linked to this file."""

        self.boundingr = 0
        """The bounding radius (in meters) of this file."""

        self.objects = set()
        """The objects that will be exported into this file."""

        self.root_obj = None
        """The object that caused this file to be created (e.g. because it is animated)."""

        self.animation_keys = set()
        """Animation keys (AniID, AniBeschreibung, AniLoopen) of the animation contained in this file or its children."""

        # Settings for linked files
        self.group_name = ""
        self.visible_from = 0.0
        self.visible_to = 0.0
        self.preload_factor = 0.0
        self.forced_brightness = 0.0
        self.lod = 0
        self.is_tile = False
        self.is_detail_tile = False
        self.is_billboard = False
        self.is_readonly = False

        # Relation to the parent file
        self.boundingr_in_parent = 0
        """The bounding radius of this file as included in the parent file --
            i.e. with applied scale and taking into account translation animations."""

        self.location = None
        """The location of this file within the parent file, without animation"""

        self.rotation_euler = None
        """The rotation of this file within the parent file, without animation"""

        self.scale = None
        """The scale of this file within the parent file."""

# Stores information about one subset of a LS3 file.
#     identifier: The internal identifier of the subset. 
#     boundingr: The bounding radius of this subset.
#     vertexdata, facedata: The mesh data of this subset.
class Ls3Subset:
    def __init__(self, identifier):
        self.identifier = identifier
        self.boundingr = 0
        self.vertexdata = []
        # The LSB format only allows for up to 65,536 vertices per mesh subset,
        # however before mesh optimization this number may be larger,
        # which is why using 'H' (unsigned short, min. 2 bytes) does not suffice.
        self.facedata = array.array('L')

    def __str__(self):
        return str(self.identifier)

    def __repr__(self):
        return str(self.identifier)

# A unique identifier for a subset of a LS3 file.
#     name: The name of the subset (internal to the exporter).
#     material: The Blender material of this subset.
#     animated_obj: The object that defines this subset's animation, or None.
class SubsetIdentifier:
    def __init__(self, name, material, animated_obj):
        self.name = name
        self.material = material
        self.animated_obj = animated_obj

    def __eq__(self, other):
        return (other is not None
                and self.name == other.name
                and self.material == other.material
                and self.animated_obj == other.animated_obj)

    def __str__(self):
        return "['%s', %s, %s]" % (self.name,
                self.material.name if self.material is not None else '-',
                self.animated_obj.name if self.animated_obj is not None else '-')

    def __hash__(self):
        return hash(self.name) + hash(self.material) + hash(self.animated_obj)

    def __repr__(self):
        return str(self)

    def __lt__(self, other):
        if self.name < other.name:
            return True
        elif self.name == other.name:
            if is_lt_name(self.material, other.material):
                return True
            elif self.material == other.material:
                return is_lt_name(self.animated_obj, other.animated_obj)
        return False

class OrderedAttrElement(dom.Element):
    """An XML element that writes its attributes in a defined order per tag name"""

    # This is the order in which Zusi writes node attributes. This is to minimize diffs when editing a file with Zusi afterwards.
    # Only specify orders for elements where the order differs from the alphabetical order.
    # In the latter case we can just sort the attributes by keys.
    orders = {
        "Info": ["DateiTyp", "Version", "MinVersion", "ObjektID", "Beschreibung", "EinsatzAb", "EinsatzBis", "DateiKategorie"],
        "SubSet": ["Cd", "Ca", "Ce", "TypLs3", "TypGF", "GruppenName", "BeleuchtungTyp", "Zwangshelligkeit", "Blink", "MeterProTex", "MeterProTex2", "zBias", "zZoom", "DoppeltRendern", "Nachtumschaltung", "NachtEinstellung", "MeshV", "MeshI"],
        "AutorEintrag": ["AutorID", "AutorName", "AutorEmail", "AutorAufwand", "AutorLizenz", "AutorBeschreibung"],
        "Verknuepfte": ["Flags", "GruppenName", "BoundingR", "SichtbarAb", "SichtbarBis", "Vorlade", "LODbit", "Helligkeit"],
        "RenderFlags": ["TexVoreinstellung", "SHADEMODE", "DESTBLEND", "SRCBLEND", "ALPHABLENDENABLE", "ALPHATESTENABLE", "ALPHAREF"],
        "SubSetTexFlags": ["MINFILTER", "MAGFILTER", "COLOROP", "COLORARG1", "COLORARG2", "COLORARG0", "ALPHAOP", "ALPHAARG1", "ALPHAARG2", "ALPHAARG0", "RESULTARG"],
        "SubSetTexFlags2": ["MINFILTER", "MAGFILTER", "COLOROP", "COLORARG1", "COLORARG2", "COLORARG0", "ALPHAOP", "ALPHAARG1", "ALPHAARG2", "ALPHAARG0", "RESULTARG"],
        "SubSetTexFlags3": ["MINFILTER", "MAGFILTER", "COLOROP", "COLORARG1", "COLORARG2", "COLORARG0", "ALPHAOP", "ALPHAARG1", "ALPHAARG2", "ALPHAARG0", "RESULTARG"],
        "Ankerpunkt": ["AnkerTyp", "AnkerKat", "Beschreibung"],
        "MeshAnimation": ["AniIndex", "AniNr", "AniGeschw"],
        "AniPunkt": ["AniZeit", "AniDimmung"],
        "VerknAnimation": ["AniIndex", "AniNr", "AniGeschw"],
        "q": ["X", "Y", "Z", "W"],
    }

    def writexml(self, writer, indent="", addindent="", newl=""):
        # Copied from xml.dom.minidom except attribute writing code.

        writer.write(indent+"<" + self.tagName)

        attrs = self._get_attributes()
        try:
            for attr_name in self.orders[self.tagName]:
                if attr_name in attrs:
                    writer.write(" %s=\"" % attr_name)
                    dom._write_data(writer, attrs[attr_name].value)
                    writer.write("\"")
        except KeyError:
            for a_name in sorted(attrs.keys()):
                writer.write(" %s=\"" % a_name)
                dom._write_data(writer, attrs[a_name].value)
                writer.write("\"")
        if self.childNodes:
            writer.write(">")
            if (len(self.childNodes) == 1 and
                self.childNodes[0].nodeType == dom.Node.TEXT_NODE):
                self.childNodes[0].writexml(writer, '', '', '')
            else:
                writer.write(newl)
                for node in self.childNodes:
                    node.writexml(writer, indent+addindent, addindent, newl)
                writer.write(indent)
            writer.write("</%s>%s" % (self.tagName, newl))
        else:
            writer.write("/>%s"%(newl))

class SubsetDataElement(dom.Text):
    """An XML node that, when writing to XML, generates XML for <Vertex> and <Face> nodes of a subset."""
    def __init__(self, ownerDocument, subset):
        dom.Text.__init__(self)
        self.ownerDocument = ownerDocument
        self.subset = subset

    def writexml(self, writer, indent="", addindent="", newl=""):
        for entry in self.subset.vertexdata:
            if entry is not None:
                writer.write(indent + '<Vertex U="' + str(entry[6]) + '" V="' + str(entry[7])
                    + '" U2="' + str(entry[8]) + '" V2="' + str(entry[9]) + '">'
                    + '<p X="' + str(entry[0]) + '" Y="' + str(entry[1]) + '" Z="' + str(entry[2]) + '"/>'
                    + '<n X="' + str(entry[3]) + '" Y="' + str(entry[4]) + '" Z="' + str(entry[5]) + '"/>'
                    + '</Vertex>' + newl)
        for i in range(0, len(self.subset.facedata) // 3):
            writer.write(indent + '<Face i="' + str(self.subset.facedata[3*i]) + ";"
                + str(self.subset.facedata[3*i+1]) + ";" + str(self.subset.facedata[3*i+2]) + '"/>' + newl)

# Container for the exporter settings
class Ls3ExporterSettings:
    def __init__(self,
                context,
                filePath,
                fileName,
                fileDirectory,
                exportSelected,
                exportAnimations,
                optimizeMesh,
                maxUVDelta,
                maxCoordDelta,
                maxNormalAngle,  # in radians
                writeLsb,
                variantIDs = [],
                selectedObjects = [],
                ):
        self.context = context
        self.filePath = filePath
        self.fileName = fileName
        self.fileDirectory = fileDirectory
        self.exportSelected = exportSelected
        self.exportAnimations = exportAnimations
        self.optimizeMesh = optimizeMesh
        self.maxUVDelta = maxUVDelta
        self.maxCoordDelta = maxCoordDelta
        self.maxNormalAngle = maxNormalAngle
        self.writeLsb = writeLsb
        self.variantIDs = variantIDs
        self.selectedObjects = selectedObjects

class Ls3Exporter:
    def __init__(self, config):
        self.config = config

        # The XML document node
        self.xmldoc = None

        # Build file structure
        self.get_animations()
        self.exported_subsets = self.get_exported_subsets()

    def create_element(self, tag_name):
        e = OrderedAttrElement(tag_name)
        e.ownerDocument = self.xmldoc
        return e

    def create_child_element(self, parent, tag_name):
        result = self.create_element(tag_name)
        parent.appendChild(result)
        return result

    # Convert a Blender path to a path where Zusi can find the specified file.
    # Returns
    #  - only the file name: if the file resides in the same directory as the .ls3 file (this can be turned off by setting force_relative_to_root=True)
    #  - a path relative to the Zusi data directory: if the file resides on the same drive as the Zusi data directory,
    #    (this is checked for both user and official data directory)
    #  - the path, otherwise.
    # The path separator will always be a backslash, regardless of the operating system.
    def relpath(self, path, force_relative_to_root=False):
        path = os.path.realpath(bpy.path.abspath(path))
        (dirname, filename) = os.path.split(path)

        if not force_relative_to_root and os.path.normpath(dirname) == os.path.normpath(self.config.fileDirectory):
            return filename

        datadir_official = os.path.realpath(zusicommon.get_zusi_data_path_official())
        if bpy.path.is_subdir(dirname, datadir_official):
            result = os.path.relpath(path, datadir_official)
        else:
            datadir = os.path.realpath(zusicommon.get_zusi_data_path())
            try:
                result = os.path.relpath(path, datadir)
            except ValueError:
                # path and datadir are not on the same drive
                try:
                    result = os.path.relpath(path, datadir_official)
                except ValueError:
                    # path and datadir_official are not on the same drive either
                    return path.replace(os.sep, "\\")

        return result.replace(os.sep, "\\") if os.sep in result else '\\' + result

    def get_file_root(self, ob):
        """Returns the object that has to be the root of the LS3 file in which 'ob' is placed
        in order to animate 'ob' correctly."""
        # Return the second animated ancestor (where the current object counts if it's animated)
        if not self.config.exportAnimations:
            return None

        num_animations = 1 if self.is_animated(ob) else 0
        cur = ob.parent
        while cur is not None:
            if self.is_animated(cur):
                num_animations += 1
                if num_animations == 2 or ob.zusi_is_linked_file:
                    break
            cur = cur.parent
        return cur

    def is_animated(self, ob):
        """Returns whether the object ob has an animation of its own (this is not the case if the object
        is animated through its parent)."""
        return self.config.exportAnimations and self.animations[ob] is not None and \
            ((ob.animation_data is not None and ob.animation_data.action is not None) or len(ob.constraints) > 0)

    def get_animated_ob(self, ob):
        """Gets the first object in ob's parent hierarchy that is animated, or None"""
        while ob is not None:
            if self.is_animated(ob):
                return ob
            ob = ob.parent
        return None

    def transformation_relative(self, ob, root, scale_root):
        """Returns a matrix that describes ob's transformation relative to 'scale_root', where location and rotation
        transformation are only included up to 'root', which must be a descendant of 'scale_root'.
        For meshes, this is how the mesh will be transformed before writing it to the subset data.
        For linked files, this is how the coordinates of the <Verknuepfte> node will be specified if the linked file
        is not animated."""

        # In Blender, the transformation of an object O with parents P_0, ..., P_n is calclulated using:
        #     P_0.matrix_local * ... * P_n.matrix_local * O.matrix_local
        # where all transformation matrices are animatable.
        #
        # In Zusi, only one layer of animated transformations can be specified per file, and it is relative
        # to the file's origin (the transformation of the file's root object in Blender)"""

        if root is None: # => then scale_root must also be None
            return ob.matrix_world

        result = Matrix()
        found_root = False
        while ob != scale_root:
            found_root = found_root or ob == root
            if found_root:
                # TODO: Warn if scaling is animated (Zusi does not support this and the export result
                # will depend on the current frame.
                loc, rot, scale = ob.matrix_local.decompose()
                scale1 = Matrix.Scale(scale.x, 4, Vector((1.0, 0.0, 0.0)))
                scale2 = Matrix.Scale(scale.y, 4, Vector((0.0, 1.0, 0.0)))
                scale3 = Matrix.Scale(scale.z, 4, Vector((0.0, 0.0, 1.0)))
                result = scale1 @ scale2 @ scale3 @ result
            else:
                result = ob.matrix_local @ result
            ob = ob.parent
        return result

    # Returns a list of the active usable texture slots of the given material.
    def get_active_texture_slots(self, material):
        if not material:
            return []

        # Create a list of active image texture slots.
        # The use flag (checkbox) of the texture slot is only taken into account if no variants are defined.
        variants_defined = len(self.config.context.scene.zusi_variants) > 0
        return [] # XXX
        return [texture_slot for texture_slot in material.texture_slots
            if texture_slot
                and texture_slot.texture
                and texture_slot.texture.type == "IMAGE"
                and (variants_defined or texture_slot.use)
                and getattr(texture_slot.texture.image, "source", "") == "FILE"
                and zusicommon.is_object_visible(texture_slot.texture, self.config.variantIDs)]

    # Writes all objects that have the "Is anchor point" property set to true.
    def write_anchor_points(self, landschaftNode):
        anchor_points = {}
        for ob in self.config.context.scene.objects:
            if ob.zusi_is_anchor_point and zusicommon.is_object_visible(ob, self.config.variantIDs):
                ankerpunktNode = self.create_element("Ankerpunkt")
                anchor_points[ob.name] = ankerpunktNode

                if ob.zusi_anchor_point_category != "0":
                    ankerpunktNode.setAttribute("AnkerKat", ob.zusi_anchor_point_category)
                if ob.zusi_anchor_point_type != "0":
                    ankerpunktNode.setAttribute("AnkerTyp", ob.zusi_anchor_point_type)
                if ob.zusi_anchor_point_description != "":
                    ankerpunktNode.setAttribute("Beschreibung", ob.zusi_anchor_point_description)

                translation, rotation_quaternion, scale = ob.matrix_world.decompose()

                fill_node_xyz(self.create_child_element(ankerpunktNode, "p"), -translation[1], translation[0], translation[2])

                rotation = zusi_rotation_from_quaternion(rotation_quaternion)
                fill_node_xyz(self.create_child_element(ankerpunktNode, "phi"), rotation.x, rotation.y, rotation.z)

                for entry in ob.zusi_anchor_point_files:
                    dateiNode = self.create_child_element(ankerpunktNode, "Datei")
                    dateiNode.setAttribute("Dateiname", self.relpath(entry.name_realpath, force_relative_to_root=True))
                    dateiNode.setAttribute("NurInfo", "1")

        for name in sorted(anchor_points.keys()):
            landschaftNode.appendChild(anchor_points[name])

    # Adds a new subset node to the specified <Landschaft> node. The subset is given by a Ls3Subset object
    # containing the objects and the material to export.
    def write_subset_node(self, landschaftNode, subset, ls3file):
        subsetNode = self.create_child_element(landschaftNode, "SubSet")
        material = subset.identifier.material

        self.write_subset_material(subsetNode, material)
        if material is not None:
            if material.zusi_landscape_type != "0":
                subsetNode.setAttribute("TypLs3", material.zusi_landscape_type)
            if material.zusi_gf_type != "0":
                subsetNode.setAttribute("TypGF", material.zusi_gf_type)
            if material.zusi_force_brightness:
                subsetNode.setAttribute("Zwangshelligkeit", str(material.zusi_force_brightness))
            if material.zusi_signal_magnification:
                subsetNode.setAttribute("zZoom", str(material.zusi_signal_magnification))
            if material.zusi_second_pass and material.zusi_texture_preset == '4':
                subsetNode.setAttribute("DoppeltRendern", "1")

        if not self.config.writeLsb:
            # Generating all <Vertex> and <Face> nodes via the xmldoc functions is slooooow.
            # Therefore, a special node is inserted that generates the necessary <Vertex> and
            # <Face> XML on the fly. Yes, this is ugly.
            subsetNode.appendChild(SubsetDataElement(self.xmldoc, subset))

        return subsetNode

    # Writes the mesh of the specified object to the appropriate subsets.
    def write_object_data(self, ob_original, ls3file):
        debug("Exporting object {}", ob_original.name)
        subsets = self.exported_subsets[ob_original]
        if not len(subsets):
            return

        depsgraph = self.config.context.evaluated_depsgraph_get()
        ob = ob_original.evaluated_get(depsgraph)

        # For each subset, the square of the length of the longest vertex belonging to that subset (projected onto the XY plane).
        # Used for bounding radius calculation.
        max_v_len_squared = dict((x, 0) for x in subsets.keys())

        vgroup_xy = -1 if "Normal constraint XY" not in ob.vertex_groups else ob.vertex_groups["Normal constraint XY"].index
        vgroup_yz = -1 if "Normal constraint YZ" not in ob.vertex_groups else ob.vertex_groups["Normal constraint YZ"].index
        vgroup_xz = -1 if "Normal constraint XZ" not in ob.vertex_groups else ob.vertex_groups["Normal constraint XZ"].index

        use_rail_normals = ob.type == 'MESH' and ob.data and ob.data.zusi_is_rail

        # Apply modifiers and transform the mesh so that the vertex coordinates
        # are global coordinates. Also recalculate the vertex normals.
        # preserve_all_data_layers=True: https://blender.stackexchange.com/a/170069
        # TODO: use render settings
        mesh = ob.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph) # , settings="PREVIEW")

        transform_matrix = self.transformation_relative(ob_original, self.get_animated_ob(ob_original), ls3file.root_obj)
        mesh.transform(transform_matrix)

        if bpy.app.version == (3, 1, 0):
            # Workaround for a Blender bug
            mesh.flip_normals()
            mesh.flip_normals()
        else:
            mesh.calc_normals()
        use_auto_smooth = mesh.use_auto_smooth
        if mesh.use_auto_smooth:
            mesh.calc_normals_split()
        mesh.calc_loop_triangles()

        # If the object is mirrored/negatively scaled, the normals will come out the wrong way
        # when applying the transformation.
        must_flip_normals = transform_matrix.determinant() < 0.0

        # List vertex indices of edges that are marked as "sharp edges",
        # which means we won't merge them later during mesh optimization.
        # The order of the vertices in face.edge_keys does not seem to be consistent,
        # so we include both (v0,v1) and (v1,v0) in the set.
        no_merge_vertex_pairs = set([(e.vertices[0], e.vertices[1]) for e in mesh.edges if e.use_edge_sharp]).union(
            set([(e.vertices[1], e.vertices[0]) for e in mesh.edges if e.use_edge_sharp]))

        # For each subset, and i in {0, 1}, get the UV layer from which the UV coordinates
        # for texture i in the subset shall be taken. Can be None.
        uvlayers = {}
        for material_index in subsets.keys():
            if material_index < len(ob.material_slots):
                mat = ob.material_slots[material_index].material
                wrapper = PrincipledBSDFWrapper(mat)
                uvlayers[material_index] = [
                    None if wrapper.base_texture_image is None
                        else mesh.uv_layers[wrapper.base_uv_map] if wrapper.base_uv_map is not None
                        else mesh.uv_layers.active,
                    None if wrapper.secondary_texture_image is None
                        else mesh.uv_layers[wrapper.secondary_uv_map] if wrapper.secondary_uv_map is not None
                        else mesh.uv_layers.active]
            else:
                uvlayers[material_index] = [None, None]

        # Write vertices, faces and UV coordinates.
        # Access faces via the loop_triangles API which automatically triangulates the mesh.
        # A vertex that appears in two faces with different normals or different UV coordinates will
        # have to be exported as two Zusi vertices. Therefore, all vertices are exported once per face,
        # and mesh optimization will later re-merge vertices that have the same location, normal, and
        # UV coordinates.
        for face in mesh.loop_triangles:
            if face.material_index not in subsets:
                continue
            subset = subsets[face.material_index]
            maxvertexindex = len(subset.vertexdata)

            # Write the triangle.
            # Optionally reverse order of faces to flip normals
            if must_flip_normals:
                subset.facedata.extend((maxvertexindex + 2, maxvertexindex + 1, maxvertexindex))
            else:
                subset.facedata.extend((maxvertexindex, maxvertexindex + 1, maxvertexindex + 2))

            # Compile a list of all vertices to mark as "don't merge".
            # Those are the vertices that form a sharp edge in the current face.
            face_no_merge_vertex_pairs = set(face.edge_keys).intersection(no_merge_vertex_pairs)
            face_no_merge_vertices = [pair[0] for pair in face_no_merge_vertex_pairs] + [pair[1] for pair in face_no_merge_vertex_pairs]

            # Write vertex coordinates (location, normal, and UV coordinates)
            for i, loop_index in enumerate(face.loops):  # i in [0..2]
                loop = mesh.loops[loop_index]
                v = mesh.vertices[loop.vertex_index]
                face_uv_layers = uvlayers[face.material_index]

                # Retrieve UV data. The loop over range(0, min(active_uvmaps_count, 2)) is
                # unrolled for performance reasons.
                if face_uv_layers[0] is not None:
                    uvdata1 = face_uv_layers[0].data[loop_index].uv
                else:
                    uvdata1 = (0.0, 1.0)

                if face_uv_layers[1] is not None:
                    uvdata2 = face_uv_layers[1].data[loop_index].uv
                else:
                    uvdata2 = (0.0, 1.0)

                # Since the vertices are exported per-face, get the vertex normal from the face normal,
                # except when the face is set to "smooth"
                if use_rail_normals:
                    normal = (0, 0, 1)
                else:
                    if use_auto_smooth:
                        normal = loop.normal
                    elif face.use_smooth:
                        normal = v.normal
                        for g in v.groups:
                            if g.weight == 0.0:
                                continue
                            if g.group == vgroup_yz:
                                normal[0] = 0
                            elif g.group == vgroup_xz:
                                normal[1] = 0
                            elif g.group == vgroup_xy:
                                normal[2] = 0
                        normal.normalize()
                    else:
                        normal = face.normal

                    if must_flip_normals:
                        normal = -normal

                # Calculate square of vertex length (projected onto the XY plane)
                # for the bounding radius.
                v_len_squared = v.co.x * v.co.x + v.co.y * v.co.y
                if v_len_squared > max_v_len_squared[face.material_index]:
                    max_v_len_squared[face.material_index] = v_len_squared

                # The coordinates are transformed into the Zusi coordinate system.
                # The vertex index is appended for reordering vertices
                subset.vertexdata.append((
                    -v.co[1], v.co[0], v.co[2],
                    -normal[1], normal[0], normal[2],
                    uvdata1[0], 1 - uvdata1[1],
                    uvdata2[0], 1 - uvdata2[1],
                    maxvertexindex + i,
                    loop.vertex_index in face_no_merge_vertices
                ))

        # Remove the generated preview mesh
        ob.to_mesh_clear()

        for matidx, boundingr_squared in max_v_len_squared.items():
            subset = subsets[matidx]
            subset.boundingr = max(subset.boundingr, sqrt(boundingr_squared))

    def write_subset_material(self, subsetNode, material):
        renderFlagsNode = self.create_child_element(subsetNode, "RenderFlags")

        if material is None:
            renderFlagsNode.setAttribute("TexVoreinstellung", "1")
            return

        wrapper = PrincipledBSDFWrapper(material)

        # Set ambient, diffuse, and emit color.
        # Zusi's lighting model works as follows:
        # An object will always have its night color (day and night).
        # By day the diffuse and ambient color are added to the night color.
        # It follows from this that an object can only get darker at night, not lighter.

        diffuse_color = wrapper.base_color
        ambient_color = material.zusi_ambient_color if material.zusi_use_ambient else Color((1, 1, 1))

        # Adjust emit color to be always darker than the diffuse and ambient color.
        emit_color = material.zusi_emit_color if material.zusi_use_emit else Color((0, 0, 0))
        debug("Base values: Diffuse {}, Ambient {}, Emit {}", diffuse_color, ambient_color, emit_color)
        emit_color = Color((
            min(emit_color[0], diffuse_color[0], ambient_color[0]),
            min(emit_color[1], diffuse_color[1], ambient_color[1]),
            min(emit_color[2], diffuse_color[2], ambient_color[2]),
        ))

        # Subtract emit color from the diffuse and ambient color.
        diffuse_color -= emit_color
        ambient_color -= emit_color

        # Add overexposure to the diffuse color.
        if material.zusi_allow_overexposure:
            diffuse_color = clamp_color(diffuse_color + material.zusi_overexposure_addition)
            ambient_color = clamp_color(ambient_color + material.zusi_overexposure_addition_ambient)

        subsetNode.setAttribute("Cd", rgba_to_rgb_hex_string(diffuse_color, 1)) #material.alpha)) # XXX
        if material.zusi_use_ambient:
            subsetNode.setAttribute("Ca", rgba_to_rgb_hex_string(ambient_color,
                material.zusi_ambient_alpha))
        if emit_color != Color((0, 0, 0)):
            # Emit alpha is ignored in Zusi.
            subsetNode.setAttribute("Ce", rgba_to_rgb_hex_string(emit_color, 0))
        if material.zusi_texture_preset in ['5', '10'] and material.zusi_night_switch_threshold != 0.0:
            subsetNode.setAttribute("Nachtumschaltung", str(material.zusi_night_switch_threshold))
        if material.zusi_texture_preset == '5' and material.zusi_day_mode_preset != '0':
            subsetNode.setAttribute("NachtEinstellung", material.zusi_day_mode_preset)

        renderFlagsNode.setAttribute("TexVoreinstellung", material.zusi_texture_preset)
        if material.zusi_texture_preset == "0":
            # Custom texture preset
            renderFlagsNode.setAttribute("SHADEMODE", material.result_stage.D3DRS_SHADEMODE)
            renderFlagsNode.setAttribute("DESTBLEND", material.result_stage.D3DRS_DESTBLEND)
            renderFlagsNode.setAttribute("SRCBLEND", material.result_stage.D3DRS_SRCBLEND)
            
            if material.result_stage.D3DRS_ALPHABLENDENABLE:
                renderFlagsNode.setAttribute("ALPHABLENDENABLE", "1")
            # TODO
            #if material.result_stage.D3DRS_ALPHATESTENABLE:
            #    renderFlagsNode.setAttribute("ALPHATESTENABLE", "1")
            renderFlagsNode.setAttribute("ALPHAREF", str(material.result_stage.alpha_ref))

            for (texstage, node_name) in [(material.texture_stage_1, "SubSetTexFlags"), (material.texture_stage_2, "SubSetTexFlags2"), (material.texture_stage_3, "SubSetTexFlags3")]:
                texflagsNode = self.create_child_element(renderFlagsNode, node_name)
                texflagsNode.setAttribute("MINFILTER", texstage.D3DSAMP_MINFILTER)
                texflagsNode.setAttribute("MAGFILTER", texstage.D3DSAMP_MAGFILTER)
                texflagsNode.setAttribute("COLOROP", texstage.D3DTSS_COLOROP)
                texflagsNode.setAttribute("COLORARG1", texstage.D3DTSS_COLORARG1)
                texflagsNode.setAttribute("COLORARG2", texstage.D3DTSS_COLORARG2)
                texflagsNode.setAttribute("COLORARG0", texstage.D3DTSS_COLORARG0)
                texflagsNode.setAttribute("ALPHAOP", texstage.D3DSAMP_ALPHAOP)
                texflagsNode.setAttribute("ALPHAARG1", texstage.D3DTSS_ALPHAARG1)
                texflagsNode.setAttribute("ALPHAARG2", texstage.D3DTSS_ALPHAARG2)
                texflagsNode.setAttribute("ALPHAARG0", texstage.D3DTSS_ALPHAARG0)
                texflagsNode.setAttribute("RESULTARG", texstage.D3DTSS_RESULTARG)

        # Write textures
        if wrapper.base_texture_image:
            texture_node = self.create_child_element(subsetNode, "Textur")
            datei_node = self.create_child_element(texture_node, "Datei")
            datei_node.setAttribute("Dateiname", self.relpath(wrapper.base_texture_image.filepath))
        if wrapper.secondary_texture_image:
            texture_node = self.create_child_element(subsetNode, "Textur")
            datei_node = self.create_child_element(texture_node, "Datei")
            datei_node.setAttribute("Dateiname", self.relpath(wrapper.secondary_texture_image.filepath))

    def write_ani_keyframes(self, keyframes, animation_node):
        """Writes a list of keyframes into an animation node (<MeshAnimation> or <VerknAnimation>)"""
        for keyframe in keyframes:
            aniPunktNode = self.create_child_element(animation_node, "AniPunkt")
            aniPunktNode.setAttribute("AniZeit", str(keyframe.time))
            fill_node_xyz(self.create_child_element(aniPunktNode, "p"), -keyframe.loc.y, keyframe.loc.x, keyframe.loc.z)
            fill_node_wxyz(self.create_child_element(aniPunktNode, "q"), *keyframe.rotation_quaternion)

    def minimize_translation_length(self, keyframes):
        """Changes the translation vectors in a list of keyframes (which are relative to (0,0,0))
        so that the maximum translation length is minimized. Returns a vector to which the new
        translation vectors are relative."""
        if not len(keyframes):
            return Vector((0, 0, 0))

        min_translation = keyframes[0].loc.copy()
        max_translation = keyframes[0].loc.copy()

        for keyframe in keyframes[1:]:
            min_translation.x = min(min_translation.x, keyframe.loc.x)
            min_translation.y = min(min_translation.y, keyframe.loc.y)
            min_translation.z = min(min_translation.z, keyframe.loc.z)
            max_translation.x = max(max_translation.x, keyframe.loc.x)
            max_translation.y = max(max_translation.y, keyframe.loc.y)
            max_translation.z = max(max_translation.z, keyframe.loc.z)

        new_origin = (max_translation + min_translation) / 2

        for keyframe in keyframes:
            keyframe.loc -= new_origin

        return new_origin

    def get_max_xy_translation_length(self, keyframes):
        """Returns the length of the longest translation vector (projected onto the xy plane) in a keyframe list."""
        return max(vector_xy_length(keyframe.loc) for keyframe in keyframes) if len(keyframes) else 0

    def get_ani_keyframes(self, ob, root, animation):
        """Returns a sorted list of keyframes (translation and rotation relative to `root`) for `ob`
        where the keyframe times are taken from `animation`."""
        translation_length = 0

        # Get frame numbers of the 0.0 and 1.0 frames.
        frame0 = self.config.context.scene.frame_start
        frame1 = self.config.context.scene.frame_end

        # Get frame numbers of keyframes. Make sure that the start and end keyframes are at an integer
        # (because Zusi does not have a continuation mode setting like Blender).
        keyframe_nos = set([round(keyframe.co.x) for fcurve in animation.fcurves for keyframe in fcurve.keyframe_points])
        if len(keyframe_nos) and frame0 != frame1:
            min_keyframe = frame0 + floor(float(min(keyframe_nos) - frame0) / (frame1 - frame0)) * (frame1 - frame0)
            max_keyframe = frame0 + ceil(float(max(keyframe_nos) - frame0) / (frame1 - frame0)) * (frame1 - frame0)
            keyframe_nos.add(min_keyframe)
            keyframe_nos.add(max_keyframe)

        # Compute keyframes.
        original_current_frame = self.config.context.scene.frame_current
        rotation_euler = None
        result = []
        for keyframe_no in sorted(keyframe_nos):
            time = float(keyframe_no - frame0) / (frame1 - frame0) if frame0 != frame1 else 0
            self.config.context.scene.frame_set(keyframe_no)
            loc, rot, scale = self.transformation_relative(ob, root, root).decompose()

            # Make rotation Euler compatible with the previous frame to prevent axis flipping.
            rotation_euler = zusi_rotation_from_quaternion(rot, rotation_euler)
            rotation_quaternion = rotation_euler.to_quaternion()

            result.append(Keyframe(time, loc, rotation_quaternion))

        self.config.context.scene.frame_set(original_current_frame)
        return result

    def get_animations(self):
        """Creates the dictionary self.animations, which contains for every object in the scene
        the Action that controls this object's animation."""
        self.animations = {}
        for ob in self.config.context.scene.objects:
            self.get_animation_recursive(ob)

    def get_animation_recursive(self, ob):
        if ob in self.animations:
            return self.animations[ob]

        self.animations[ob] = None

        # Get animation from the object or its parent.
        if ob.animation_data is not None and ob.animation_data.action is not None:
            self.animations[ob] = ob.animation_data.action
        elif ob.parent is not None:
            self.animations[ob] = self.get_animation_recursive(ob.parent)

        # Get animation from constraint targets.
        if self.animations[ob] is None:
            for c in ob.constraints:
                if hasattr(c, 'target'):
                    animation = self.get_animation_recursive(c.target)
                    if animation is not None:
                        self.animations[ob] = animation
                        break

        return self.animations[ob]

    # Build list of files from the scene's objects. The main file will always be the first item in the list.
    def get_files(self):
        split_file_name = self.config.fileName.split(os.extsep, 1)
        if len(split_file_name) > 1:
            basename, ext = split_file_name[0], (os.extsep + split_file_name[1])
        else:
            basename, ext = split_file_name[0], ""
        main_file = Ls3File()
        main_file.filename = self.config.fileName
        main_file.objects = set()
        main_file.is_main_file = True

        # The resulting files are indexed by their root object. The main file is the only file without a root object.
        result = { None : main_file }

        def is_object_exported(ob):
            return ((
                len(self.exported_subsets[ob]) or
                ob.zusi_is_linked_file and
                    (ob.name in self.config.selectedObjects or self.config.exportSelected in [EXPORT_ALL_OBJECTS, EXPORT_SELECTED_MATERIALS])
                ) and zusicommon.is_object_visible(ob, self.config.variantIDs))

        # Collect all objects that have to be the root of a file.
        # Those are the root objects for all exported objects, then the root objects of those objects, and so on.
        work_list = [ob for ob in self.config.context.scene.objects.values() if is_object_exported(ob)]
        visited = set()
        while len(work_list):
            ob = work_list.pop()
            if ob not in visited:
                visited.add(ob)

                root_obj = self.get_file_root(ob)
                debug("Root object of {} is {}", ob, root_obj)
                if root_obj is not None and root_obj not in visited:
                    work_list.append(root_obj)
                if root_obj not in result:
                    new_file = Ls3File()
                    new_file.filename = basename + "_" + root_obj.name.replace(" ", "_") + ext
                    new_file.root_obj = root_obj
                    result[root_obj] = new_file

        for ob in self.config.context.scene.objects.values():
            if ob in result:
                result[ob].objects.add(ob)
                result[self.get_file_root(ob)].linked_files.append(result[ob])
            elif is_object_exported(ob):
                cur = ob.parent
                while cur is not None and cur not in result:
                    cur = cur.parent
                result[cur].objects.add(ob)

            if ob.zusi_is_linked_file and is_object_exported(ob):
                linked_file = Ls3File()
                linked_file.filename = self.relpath(ob.zusi_link_file_name_realpath)
                linked_file.root_obj = ob
                linked_file.objects.add(ob)
                linked_file.group_name = ob.zusi_link_group
                linked_file.visible_from = ob.zusi_link_visible_from
                linked_file.visible_to = ob.zusi_link_visible_to
                linked_file.preload_factor = ob.zusi_link_preload_factor
                linked_file.boundingr = ob.zusi_link_radius
                linked_file.forced_brightness = ob.zusi_link_forced_brightness
                linked_file.lod = lod_convert(ob.zusi_link_lod)
                linked_file.is_tile = ob.zusi_link_is_tile
                linked_file.is_detail_tile = ob.zusi_link_is_detail_tile
                linked_file.is_billboard = ob.zusi_link_is_billboard
                linked_file.is_readonly = ob.zusi_link_is_readonly
                linked_file.must_export = False

                parent = result[self.get_file_root(ob)]
                parent.linked_files.append(linked_file)
                for animation in ob.zusi_link_animations:
                    parent.animation_keys.add((
                        int(animation.animation_type),
                        animation.description if len(animation.description) > 0 \
                                else get_ani_description(animation.animation_type),
                        False))

        for root_obj, ls3file in result.items():
            ls3file.subsets = sorted(set([s for ob in ls3file.objects for s in self.exported_subsets[ob].values()]),
                    key = lambda s: s.identifier)

        debug("Files:")
        for root_obj, ls3file in result.items():
            debug("{} (root object {}, objects {}, linked files {})", ls3file.filename,
                root_obj.name if root_obj is not None else "None",
                ", ".join(ob.name for ob in ls3file.objects),
                ", ".join(linkedfile.filename for linkedfile in ls3file.linked_files))
            for sub in ls3file.subsets:
                debug("   {}", str(sub.identifier))

        # Main file is the first item in the list.
        return [result[None]] + [ls3file for ls3file in result.values() if ls3file.root_obj is not None]

    def get_exported_subsets(self):
        """Builds a dictionary that maps exported material indices to the appropriate subset
        for every object in the scene. The export settings (e.g. "export only selected objects") are taken into account.
        Also builds the self.subsets dictionary that maps subset identifiers to Ls3Subset objects."""

        result = {}
        self.subsets = {}
        # A set of all subset identifiers that will be exported. It is only filled if
        # self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS.
        all_exported_identifiers = set()

        for ob in self.config.context.scene.objects:
            # For "export subsets of selected objects" mode, only treat selected objects in the first phase.
            if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS and ob.name not in self.config.selectedObjects:
                continue

            result[ob] = {}
            # Filter out complete objects.
            if ob.type != 'MESH' and ob.type != 'CURVE':
                continue
            if (self.config.exportSelected == EXPORT_SELECTED_OBJECTS and
                    ob.name not in self.config.selectedObjects):
                continue
            if (self.config.exportSelected == EXPORT_VISIBLE_COLLECTIONS and
                    all(collection.hide_viewport for collection in ob.users_collection)):
                continue

            for matidx, mat in get_used_materials_for_object(ob):
                if self.config.exportSelected != EXPORT_SELECTED_MATERIALS or (mat is not None and mat.name in self.config.selectedObjects):
                    identifier = SubsetIdentifier(ob.zusi_subset_name, mat, self.get_animated_ob(ob))
                    if identifier not in self.subsets:
                        subset = Ls3Subset(identifier)
                        self.subsets[identifier] = subset
                    else:
                        subset = self.subsets[identifier]

                    # Selected objects that are not visible in the current variants can still influence
                    # the exported subsets (via all_exported_identifiers), but they themselves are not exported.
                    if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS:
                        all_exported_identifiers.add(identifier)
                    if zusicommon.is_object_visible(ob, self.config.variantIDs):
                        result[ob][matidx] = subset

        # For "export subsets of selected objects" mode, we need a second pass
        # for all unselected objects which might have a subset in common with
        # a selected object.
        if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS:
            for ob in self.config.context.scene.objects:
                if ob.type != 'MESH' or not zusicommon.is_object_visible(ob, self.config.variantIDs):
                    result[ob] = {}
                    continue
                if ob.name in self.config.selectedObjects:
                    continue
                result[ob] = {}
                for matidx, mat in get_used_materials_for_object(ob):
                    identifier = SubsetIdentifier(ob.zusi_subset_name, mat, self.get_animated_ob(ob))
                    if identifier in all_exported_identifiers:
                        result[ob][matidx] = self.subsets[identifier]

        return result

    def get_animation_keys(self, animation):
        """Returns the keys (AniID, AniBeschreibung, AniLoopen) of the <Animation> nodes this animation has to be entered in."""
        loop = animation.zusi_animation_loop if animation.zusi_animation_type in ["0", "1"] else False
        if animation.zusi_animation_type == "0":
            if len(animation.zusi_animation_names) == 0:
                return [(0, get_ani_description(animation.zusi_animation_type) + (" (loop)" if loop else ""), loop)]
            else:
                return [(0, name_wrapper.name, loop) for name_wrapper in animation.zusi_animation_names]
        else:
            return [(int(animation.zusi_animation_type),
                    get_ani_description(animation.zusi_animation_type) + (" (loop)" if loop else ""),
                    loop)]

    def write_ls3_file(self, ls3file):
        def fill_author_info(infoNode, authors, write_effort):
            for author in sce.zusi_authors:
                autorEintragNode = self.create_child_element(infoNode, "AutorEintrag")

                if author.id != 0:
                    autorEintragNode.setAttribute("AutorID", str(author.id))
                if author.name != "":
                    autorEintragNode.setAttribute("AutorName", author.name)
                if author.email != "":
                    autorEintragNode.setAttribute("AutorEmail", author.email)
                if write_effort and author.effort != 0:
                    autorEintragNode.setAttribute("AutorAufwand", str(round(author.effort, 5)))
                if author.remarks != "":
                    autorEintragNode.setAttribute("AutorBeschreibung", author.remarks)
                if author.license != "":
                    autorEintragNode.setAttribute("AutorLizenz", author.license)

        sce = self.config.context.scene

        # Create a new XML document
        self.xmldoc = dom.getDOMImplementation().createDocument(None, "Zusi", None)

        # Write file info
        infoNode = self.create_child_element(self.xmldoc.documentElement, "Info")
        infoNode.setAttribute("DateiTyp", "Landschaft")
        infoNode.setAttribute("Version", "A.1")
        infoNode.setAttribute("MinVersion", "A.1")

        if sce.zusi_object_id != 0:
            infoNode.setAttribute("ObjektID", str(sce.zusi_object_id))
        if sce.zusi_license != 0:
            infoNode.setAttribute("Lizenz", sce.zusi_license) # Deprecated
        if sce.zusi_description != "":
            infoNode.setAttribute("Beschreibung", sce.zusi_description)
        # TODO: Einsatz ab/bis

        fill_author_info(infoNode, sce.zusi_authors, write_effort=False)

        # Write the Landschaft node.
        landschaftNode = self.create_child_element(self.xmldoc.documentElement, "Landschaft")

        # Write anchor points (into the main file)
        if ls3file.is_main_file:
            self.write_anchor_points(landschaftNode)

        # Write subsets.
        subset_nodes = [self.write_subset_node(landschaftNode, subset, ls3file) for subset in ls3file.subsets]

        # Write animation definitions for this file and any linked file.
        ani_nr = 0
        ani_nrs_by_key = defaultdict(list)
        animation_nodes = []

        for idx, subset in enumerate(ls3file.subsets):
            # The root subset of a file is not animated via subset animation, but rather through a
            # linked animation in the parent file.
            if subset.identifier.animated_obj is not None and subset.identifier.animated_obj != ls3file.root_obj:
                animation = self.animations[subset.identifier.animated_obj]
                meshAnimationNode = self.create_element("MeshAnimation")
                meshAnimationNode.setAttribute("AniNr", str(ani_nr))
                meshAnimationNode.setAttribute("AniIndex", str(idx))
                meshAnimationNode.setAttribute("AniGeschw", str(animation.zusi_animation_speed))
                animation_nodes.append(meshAnimationNode)
                keyframes = self.get_ani_keyframes(subset.identifier.animated_obj, ls3file.root_obj, animation)
                self.write_ani_keyframes(keyframes, meshAnimationNode)

                for key in self.get_animation_keys(animation):
                    ls3file.animation_keys.add(key)
                    ani_nrs_by_key[key].append(ani_nr)
                ani_nr += 1

                ls3file.boundingr = max(ls3file.boundingr, subset.boundingr + self.get_max_xy_translation_length(keyframes))
            else:
                ls3file.boundingr = max(ls3file.boundingr, subset.boundingr)

        ls3file.linked_files.sort(key = lambda lf: lf.root_obj.name)
        for idx, linked_file in enumerate(ls3file.linked_files):
            ls3file.animation_keys.update(linked_file.animation_keys)

            linked_file.location, rotation_quaternion, linked_file.scale = \
                    self.transformation_relative(linked_file.root_obj, ls3file.root_obj, ls3file.root_obj).decompose()
            linked_file.rotation_euler = zusi_rotation_from_quaternion(rotation_quaternion)
            # TODO: Warn if scaling is animated
            max_scale_factor = max(linked_file.scale.x, linked_file.scale.y, linked_file.scale.z)

            if self.is_animated(linked_file.root_obj):
                animation = self.animations[linked_file.root_obj]
                verknAnimationNode = self.create_element("VerknAnimation")
                verknAnimationNode.setAttribute("AniNr", str(ani_nr))
                verknAnimationNode.setAttribute("AniIndex", str(idx))
                verknAnimationNode.setAttribute("AniGeschw", str(animation.zusi_animation_speed))
                animation_nodes.append(verknAnimationNode)

                keyframes = self.get_ani_keyframes(linked_file.root_obj, ls3file.root_obj, animation)
                linked_file.location = self.minimize_translation_length(keyframes)
                linked_file.rotation_euler = Vector((0, 0, 0))
                linked_file.boundingr_in_parent = linked_file.boundingr * max_scale_factor + self.get_max_xy_translation_length(keyframes)
                self.write_ani_keyframes(keyframes, verknAnimationNode)

                for key in self.get_animation_keys(animation):
                    ls3file.animation_keys.add(key)
                    ani_nrs_by_key[key].append(ani_nr)
                ani_nr += 1
            else:
                linked_file.boundingr_in_parent = linked_file.boundingr * max_scale_factor

            ls3file.boundingr = max(ls3file.boundingr, linked_file.boundingr_in_parent + vector_xy_length(linked_file.location))

        # Write animation declarations for this file and any linked file.
        for ani_key in sorted(ls3file.animation_keys):
            animationNode = self.create_child_element(landschaftNode, "Animation")
            animationNode.setAttribute("AniID", str(ani_key[0]))
            animationNode.setAttribute("AniBeschreibung", ani_key[1])
            if ani_key[2]:
                animationNode.setAttribute("AniLoopen", "1")

            # Write <AniNrs> nodes.
            for aninr in ani_nrs_by_key[ani_key]:
                self.create_child_element(animationNode, "AniNrs").setAttribute("AniNr", str(aninr))

        for node in animation_nodes:
            landschaftNode.appendChild(node)

        # Write linked files (*after* writing the animations because that computes loc/rot/scale/boundingr_in_parent for each linked file).
        for linked_file in reversed(ls3file.linked_files):
            verknuepfteNode = self.create_element("Verknuepfte")
            boundingr = int(ceil(linked_file.boundingr_in_parent))
            if boundingr != 0:
                verknuepfteNode.setAttribute("BoundingR", str(boundingr))
            self.create_child_element(verknuepfteNode, "Datei").setAttribute("Dateiname", linked_file.filename)
            landschaftNode.insertBefore(verknuepfteNode, landschaftNode.childNodes[0] if len(landschaftNode.childNodes) else None)

            if len(linked_file.group_name):
                verknuepfteNode.setAttribute("GruppenName", linked_file.group_name)
            if linked_file.visible_from != 0.0:
                verknuepfteNode.setAttribute("SichtbarAb", str(linked_file.visible_from))
            if linked_file.visible_to != 0.0:
                verknuepfteNode.setAttribute("SichtbarBis", str(linked_file.visible_to))
            if linked_file.preload_factor != 0.0:
                verknuepfteNode.setAttribute("Vorlade", str(linked_file.preload_factor))
            if linked_file.forced_brightness != 0.0:
                verknuepfteNode.setAttribute("Helligkeit", str(linked_file.forced_brightness))
            if linked_file.lod != 0.0:
                verknuepfteNode.setAttribute("LODbit", str(linked_file.lod))
            flags = linked_file.is_tile * 4 + linked_file.is_detail_tile * 32 + linked_file.is_billboard * 8 + linked_file.is_readonly * 16
            if flags != 0:
                verknuepfteNode.setAttribute("Flags", str(flags))

            fill_node_xyz(self.create_child_element(verknuepfteNode, "p"), -linked_file.location.y, linked_file.location.x, linked_file.location.z)
            fill_node_xyz(self.create_child_element(verknuepfteNode, "phi"), linked_file.rotation_euler.x, linked_file.rotation_euler.y, linked_file.rotation_euler.z)
            fill_node_xyz(self.create_child_element(verknuepfteNode, "sk"), linked_file.scale.y, linked_file.scale.x, linked_file.scale.z, default = 1)

        # Get path names
        filepath = os.path.join(
            os.path.realpath(os.path.expanduser(self.config.fileDirectory)),
            ls3file.filename)

        lsbwriter = None
        if self.config.writeLsb and any(len(subset.vertexdata) > 0 or len(subset.facedata) > 0 for subset in ls3file.subsets):
            (basename, ext) = os.path.splitext(filepath)
            lsbpath = basename + ".lsb"
        
            lsb_fp = open(lsbpath, 'wb')
            from . import lsb
            lsbwriter = lsb.LsbWriter(lsb_fp)
            info('Exporting LSB file {}', lsbpath)

            lsbNode = self.create_element("lsb")
            lsbNode.setAttribute("Dateiname", os.path.basename(lsbpath))
            landschaftNode.insertBefore(lsbNode, subset_nodes[0])

        for index, subset in enumerate(ls3file.subsets):
            if self.config.optimizeMesh:
                new_vidx = zusicommon.optimize_mesh(subset.vertexdata, self.config.maxCoordDelta, self.config.maxUVDelta, self.config.maxNormalAngle)
                num_deleted_vertices = sum(v is None for v in subset.vertexdata)
                if len(subset.vertexdata) - num_deleted_vertices > 65536:
                    raise OverflowError("Subset {} has {} vertices after optimization, max. 65536 supported by Zusi".format(subset.identifier, len(subset.vertexdata) - num_deleted_vertices))
                subset.facedata = array.array('H', [new_vidx[x] for x in subset.facedata])
                info("Mesh optimization for subset {}: {} of {} vertices deleted", subset.identifier, num_deleted_vertices, len(subset.vertexdata))
            else:
                if len(subset.vertexdata) > 65536:
                    raise OverflowError("Subset {} has {} vertices, max. 65536 supported by Zusi".format(subset.identifier, len(subset.vertexdata)))
                if lsbwriter:
                    # LSB writer needs its face data as unsigned short.
                    subset.facedata = array.array('H', list(subset.facedata))

            if lsbwriter:
                lsbwriter.add_subset_data(subset_nodes[index], subset.vertexdata, subset.facedata)

        if lsbwriter:
            lsb_fp.close()

        # Write XML document to file
        info('Exporting LS3 file {}', filepath)
        with open(filepath, 'wb') as fp:
            fp.write(b"\xef\xbb\xbf")
            fp.write(self.xmldoc.toprettyxml(indent = "  ", encoding = "UTF-8", newl = os.linesep))

        expensepath = filepath + ".expense.xml"
        need_expense_xml = ls3file.is_main_file and any(author.effort for author in sce.zusi_authors)
        if need_expense_xml:
            info('Writing .expense.xml file {}', expensepath)
            expensedoc = dom.getDOMImplementation().createDocument(None, "Zusi", None)
            infoNode = self.create_child_element(expensedoc.documentElement, "Info")
            infoNode.setAttribute("DateiTyp", "expense")
            infoNode.setAttribute("Version", "A.1")
            infoNode.setAttribute("MinVersion", "A.0")
            fill_author_info(infoNode, sce.zusi_authors, write_effort=True)
            expenseNode = self.create_child_element(expensedoc.documentElement, "expense")
            with open(expensepath, 'wb') as fp:
                fp.write(b"\xef\xbb\xbf")
                fp.write(expensedoc.toprettyxml(indent = "  ", encoding = "UTF-8", newl = os.linesep))
        else:
            try:
                os.remove(expensepath)
            except FileNotFoundError:
                pass

        info("Bounding radius: {} m", int(ceil(ls3file.boundingr)))

    def export_ls3(self):
        debug("Exported subset IDs:")
        debug("{}", str(self.exported_subsets))
        ls3files = self.get_files()

        # ls3files forms a tree, traverse it in postorder so that each file has all information (bounding radius)
        # about its linked files.
        work_list = [ls3files[0]]
        write_list = []

        while len(work_list):
            cur_file = work_list.pop()
            for ob in sorted(cur_file.objects, key=lambda ob: ob.name):
                self.write_object_data(ob, cur_file)

            write_list.insert(0, cur_file)
            work_list.extend([f for f in cur_file.linked_files if f.must_export])

        for ls3file in write_list:
            self.write_ls3_file(ls3file)
