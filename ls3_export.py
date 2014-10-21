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
import xml.dom.minidom as dom
from . import zusicommon, zusiprops
from math import ceil, pi, sqrt
from mathutils import *

# Converts a color value (of type Color) and an alpha value (value in [0..1])
# to a hex string "0AABBGGRR"
rgba_to_hex_string = lambda color, alpha : "0{:02X}{:02X}{:02X}{:02X}".format(*[round(x * 255) for x in [alpha, color.b, color.g, color.r]])

# Returns the length of the projection of the specified vector projected onto the XY plane.
vector_xy_length = lambda vec : sqrt(vec.x * vec.x + vec.y * vec.y)

# The default settings for the exporter
default_export_settings = {
    "exportSelected" : "0",
    "exportAnimations" : False,
    "optimizeMesh" : True,
    "maxCoordDelta" : 0.001,
    "maxUVDelta" : 0.02,
    "maxNormalAngle" : 10 / 360 * 2 * pi,
}

EXPORT_ALL_OBJECTS = "0"
EXPORT_SELECTED_OBJECTS = "1"
EXPORT_SUBSETS_OF_SELECTED_OBJECTS = "2"
EXPORT_SELECTED_MATERIALS = "3"

SUBSET_XML_PLACEHOLDER = "$$ZUSI_SUBSET_PLACEHOLDER_{}$$"

def debug(msg, *args, **kwargs):
    pass
    # print(msg.format(*args, **kwargs))

def info(msg, *args, **kwargs):
    print(msg.format(*args, **kwargs))

# Returns the value with the given key in the default_export_settings dictionary in zusiconfig.py
# or the default value specified above if an error occurs.
def get_exporter_setting(key):
    try:
        from . import zusiconfig
        return zusiconfig.default_export_settings[key]
    except:
        return default_export_settings[key]

def fill_node_xyz(node, x, y, z):
    node.setAttribute("X", str(x))
    node.setAttribute("Y", str(y))
    node.setAttribute("Z", str(z))

def normalize_color(color):
    """Returns a normalized version (RGB components between 0.0 and 1.0) of a color."""
    return Color((
        min(1.0, max(0.0, color.r)),
        min(1.0, max(0.0, color.g)),
        min(1.0, max(0.0, color.b))
    ))

def get_used_materials_for_object(ob):
    """Returns a set of all materials used (i.e. assigned to any face) in the given object."""
    if ob.data and (len(ob.data.materials) > 0):
        used_material_indices = set([poly.material_index for poly in ob.data.polygons])
        return set([ob.data.materials[i] for i in used_material_indices if ob.data.materials[i].name != 'Unsichtbar'])
    else:
        return set([None])

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

def has_location_animation(action):
    return action is not None and any([fcurve.data_path == "location" for fcurve in action.fcurves])

def has_rotation_animation(action):
    return action is not None and any([fcurve.data_path.startswith("rotation") for fcurve in action.fcurves])

def is_root_subset(subset, ls3file):
    return ls3file.root_obj in subset.objects

def is_lt_name(a, b):
    """Returns a.name < b.name, taking into account None values (which are smaller than all other values)."""
    if b is None:
        return False
    if a is None:
        return True
    else:
        return a.name < b.name

# Stores all the things that later go into one LS3 file.
#     file_name: The file name (without path) of this file.
#     subsets: The subsets in this file.
#     linked_files: The files linked to this file
#     animation: The animation of this file in the parent file.
#     boundingr: The bounding radius of this file in meters.
#     objects: The objects that will be exported into this file.
#     root_obj: The object that caused this file to be created (e.g.
#         because it has an animation).
class Ls3File:
    def __init__(self):
        self.is_main_file = False
        self.filename = ""
        self.subsets = []
        self.linked_files = []
        self.animation = None
        self.boundingr = 0
        self.objects = set()
        self.root_obj = None

# Stores information about one subset of a LS3 file.
#     identifier: The internal identifier of the subset. 
#     objects: The objects to include in this subset.
#     boundingr: The bounding radius of this subset.
class Ls3Subset:
    def __init__(self, identifier):
        self.identifier = identifier
        self.objects = []
        self.boundingr = 0

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
        self.variantIDs = variantIDs
        self.selectedObjects = selectedObjects

class Ls3Exporter:
    def __init__(self, config):
        self.config = config

        # The XML document node
        self.xmldoc = None

        # The vertex and face data for each subset to export
        self.subset_data = []

        try:
            from . import zusiconfig
            self.use_lsb = zusiconfig.use_lsb
        except:
            self.use_lsb = False

        # Initialize map of Blender Z bias values (float) to integer values
        # e.g. if values (-0.1, -0.05, 0, 0.1) appear in the scene, they will be
        # mapped to (-2, -1, 0, 1).
        zbiases_pos = sorted(set([mat.offset_z for mat in bpy.data.materials if mat.offset_z > 0]))
        zbiases_neg = sorted(set([mat.offset_z for mat in bpy.data.materials if mat.offset_z < 0]), reverse = True)

        self.z_bias_map = { 0.0 : 0 }
        self.z_bias_map.update(dict((value, idx + 1) for idx, value in enumerate(zbiases_pos)))
        self.z_bias_map.update(dict((value, -(idx + 1)) for idx, value in enumerate(zbiases_neg)))

        self.get_animations()
        self.exported_subset_identifiers = self.get_exported_subsets()

    # Convert a Blender path to a path where Zusi can find the specified file.
    # Returns
    #  - only the file name: if the file resides in the same directory as the .ls3 file
    #  - a path relative to the Zusi data directory: if the file resides on the same drive as the Zusi data directory,
    #  - the path, otherwise.
    # The path separator will always be a backslash, regardless of the operating system
    def relpath(self, path):
        path = os.path.realpath(bpy.path.abspath(path))
        (dirname, filename) = os.path.split(path)

        if dirname + os.sep == self.config.fileDirectory:
            return filename
        else:
            datadir = os.path.realpath(zusicommon.get_zusi_data_path())

            try:
                return os.path.relpath(path, datadir).replace(os.sep, "\\")
            except ValueError:
                # path and datadir are not on the same drive
                return path.replace(os.sep, "\\")

    def must_start_new_file(self, ob):
        """Returns whether the specified object and its children must be placed in their own file
        in order to be animated correctly."""
        # Animated objects with an animated child start a new file.
        return self.config.exportAnimations and self.is_animated(ob) and any([self.is_animated(ch) for ch in ob.children])

    def is_animated(self, ob):
        """Returns whether the object ob has an animation of its own (this is not the case if the object
        is animated through its parent."""
        return self.config.exportAnimations and self.animations[ob] is not None and \
            ((ob.animation_data is not None and ob.animation_data.action is not None) or len(ob.constraints) > 0)

    def get_aninrs(self, animations, animated_linked_files, animated_subsets):
        """Returns the animation numbers for a list of animations. The animation number corresponds to the
        1-indexed number of the subset/linked file that has the animation."""
        return [aninr for aninr, subset in animated_subsets if self.animations[subset.identifier.animated_obj] in animations] \
            + [aninr for aninr, linked in animated_linked_files if self.animations[linked.root_obj] in animations] \

    # Returns a list of the active texture slots of the given material.
    def get_active_texture_slots(self, material):
        if material:
            # If no variants are defined, the visibility of the texture slot is taken into account.
            variants_defined = len(self.config.context.scene.zusi_variants) > 0

            # Create a list of image textures
            image_texture_slots = [material.texture_slots[texture_slot]
                for texture_slot in material.texture_slots.keys()
                if material.texture_slots[texture_slot].texture
                    and material.texture_slots[texture_slot].texture.type == "IMAGE"
                    and (variants_defined or material.texture_slots[texture_slot].use)]

            # Refine the list, including only textures that have a file source and are active in the given variant
            return [texture_slot for texture_slot in image_texture_slots
                    if getattr(texture_slot.texture.image, "source", "") == "FILE" and zusicommon.is_object_visible(texture_slot.texture, self.config.variantIDs)]
        return []

    # Adds a new subset node to the specified <Landschaft> node. The subset is given by a Ls3Subset object
    # containing the objects and the material to export.
    # Only the faces of the supplied objects having that particular material will be written.
    def write_subset(self, landschaftNode, subset, ls3file):
        subsetNode = self.xmldoc.createElement("SubSet")
        material = subset.identifier.material
        try:
            if material.zusi_landscape_type != bpy.types.Material.zusi_landscape_type[1]["default"]:
                subsetNode.setAttribute("TypLs3", material.zusi_landscape_type)
            if material.zusi_gf_type != bpy.types.Material.zusi_gf_type[1]["default"]:
                subsetNode.setAttribute("TypGF", material.zusi_gf_type)
            if material.zusi_force_brightness:
                subsetNode.setAttribute("Zwangshelligkeit", material.zusi_force_brightness)
            if material.zusi_signal_magnification:
                subsetNode.setAttribute("zZoom", material.zusi_signal_magnification)
            if material.offset_z:
                subsetNode.setAttribute("zBias", str(self.z_bias_map[material.offset_z]))

            self.write_subset_material(subsetNode, material)
        except (IndexError, AttributeError):
            pass

        info("Exporting subset {}", str(subset.identifier))
        self.write_subset_mesh(subsetNode, subset, ls3file)
        landschaftNode.appendChild(subsetNode)

    # Writes the meshes of the subset's objects to the specified subset node.
    # Only the faces having the specified material will be written.
    def write_subset_mesh(self, subsetNode, subset, ls3file):
        vertexdata = []
        maxvertexindex = 0 # Current highest index in vertexdata, equal to len(vertexdata)
        facedata = []
        material = subset.identifier.material
        active_texture_slots = self.get_active_texture_slots(material)
        active_uvmaps = [slot.uv_layer for slot in active_texture_slots]
        active_uvmaps_count = len(active_uvmaps)
        max_v_len_squared = 0 # Square of the length of the longest vertex (projected onto the XY plane)
        
        for ob in subset.objects:
            debug("Exporting object {}", ob.name)

            # Apply modifiers and transform the mesh so that the vertex coordinates
            # are global coordinates. Also recalculate the vertex normals.
            mesh = ob.to_mesh(self.config.context.scene, True, "PREVIEW")

            # Apply the object's transformation only for if the object does not define the root subsets of its file
            # (else the transformation will be written into the link in the parent file).
            # For animated subsets, apply only the scale part (the translation and rotation part will be
            # written as part of the animation).
            if self.config.exportAnimations:
                if ob != ls3file.root_obj:
                    if ob == subset.identifier.animated_obj:
                        # TODO: Warn if scaling is animated (Zusi does not support this and the export result
                        # will depend on the current frame.
                        scale = ob.matrix_local.to_scale()
                        scale1 = Matrix.Scale(scale.x, 4, Vector((1.0, 0.0, 0.0)))
                        scale2 = Matrix.Scale(scale.y, 4, Vector((0.0, 1.0, 0.0)))
                        scale3 = Matrix.Scale(scale.z, 4, Vector((0.0, 0.0, 1.0)))
                        mesh.transform(scale1 * scale2 * scale3)
                    else:
                        mesh.transform(ob.matrix_local)
            else:
                # Ignore everything when animated export is disabled and just apply the global transformation.
                mesh.transform(ob.matrix_world)

            mesh.calc_normals()

            # If the object is mirrored/negatively scaled, the normals will come out the wrong way
            # when applying the transformation. Workaround from:
            # http://projects.blender.org/tracker/index.php?func=detail&aid=18834&group_id=9&atid=264
            ma = ob.matrix_world.to_3x3() # gets the rotation part
            must_flip_normals = Vector.dot(ma[2], Vector.cross(ma[0], ma[1])) >= 0.00001

            # List vertex indices of edges that are marked as "sharp edges",
            # which means we won't merge them later during mesh optimization.
            # The order of the vertices in face.edge_keys does not seem to be consistent,
            # so we include both (v0,v1) and (v1,v0) in the set.
            no_merge_vertex_pairs = set([(e.vertices[0], e.vertices[1]) for e in mesh.edges if e.use_edge_sharp]).union(
                set([(e.vertices[1], e.vertices[0]) for e in mesh.edges if e.use_edge_sharp]))

            # For x in {0, 1}, get the UV layers from which the UV coordinates for texture x shall
            # be taken. Can be None.
            uvlayers = [None for texindex in range(0, 2)]
            for texindex in range(0, 2):
                if texindex >= active_uvmaps_count:
                    break

                # Find UV layer with the same name as the UV map.
                # Use active UV layer if the current UV map has no name (which is the default)
                if active_uvmaps[texindex] != "":
                    for uvlayer in mesh.tessface_uv_textures:
                        if uvlayer.name == active_uvmaps[texindex]:
                            uvlayers[texindex] = uvlayer
                            break
                else:
                    uvlayers[texindex] = mesh.tessface_uv_textures.active

            # Write vertices, faces and UV coordinates.
            # Access faces via the tessfaces API which provides only triangles and quads.
            # A vertex that appears in two faces with different normals or different UV coordinates will
            # have to be exported as two Zusi vertices. Therefore, all vertices are exported once per face,
            # and mesh optimization will later re-merge vertices that have the same location, normal, and
            # UV coordinates.
            for face_index, face in enumerate(mesh.tessfaces):
                # Check if the face has the right material.
                if material is not None and ob.data.materials[face.material_index] != material:
                    continue

                # Write the first triangle of the face
                # Optionally reverse order of faces to flip normals
                if must_flip_normals:
                    facedata.append((maxvertexindex + 2, maxvertexindex + 1, maxvertexindex))
                else:
                    facedata.append((maxvertexindex, maxvertexindex + 1, maxvertexindex + 2))

                # If the face is a quad, write the second triangle too.
                if len(face.vertices) == 4:
                    if must_flip_normals:
                        facedata.append((maxvertexindex, maxvertexindex + 3, maxvertexindex + 2))
                    else:
                        facedata.append((maxvertexindex + 2, maxvertexindex + 3, maxvertexindex))

                # Compile a list of all vertices to mark as "don't merge".
                # Those are the vertices that form a sharp edge in the current face.
                face_no_merge_vertex_pairs = set(face.edge_keys).intersection(no_merge_vertex_pairs)
                face_no_merge_vertices = [pair[0] for pair in face_no_merge_vertex_pairs] + [pair[1] for pair in face_no_merge_vertex_pairs]

                # Write vertex coordinates (location, normal, and UV coordinates)
                for vertex_no, vertex_index in enumerate(face.vertices):
                    v = mesh.vertices[vertex_index]
                    uvdata1 = (0.0, 1.0)
                    uvdata2 = (0.0, 1.0)

                    for texindex in range(0, 2):
                        if texindex >= active_uvmaps_count:
                            continue

                        uvlayer = uvlayers[texindex]
                        if uvlayer is None:
                            continue

                        uv_raw = uvlayer.data[face_index].uv_raw
                        uvdata = (uv_raw[2 * vertex_no], uv_raw[2 * vertex_no + 1])
                        if texindex == 0:
                            uvdata1 = uvdata
                        else:
                            uvdata2 = uvdata

                    # Since the vertices are exported per-face, get the vertex normal from the face normal,
                    # except when the face is set to "smooth"
                    if face.use_smooth:
                        normal = (v.normal[1], -v.normal[0], -v.normal[2])
                    else:
                        normal = (face.normal[1], -face.normal[0], -face.normal[2])

                    if must_flip_normals:
                        normal = list(map(lambda x : -x, normal))

                    # Calculate square of vertex length (projected onto the XY plane)
                    # for the bounding radius.
                    v_len_squared = v.co.x * v.co.x + v.co.y * v.co.y
                    if v_len_squared > max_v_len_squared:
                        max_v_len_squared = v_len_squared

                    # The coordinates are transformed into the Zusi coordinate system.
                    # The vertex index is appended for reordering vertices
                    vertexdata.append((
                        -v.co[1], v.co[0], v.co[2],
                        normal[0], normal[1], normal[2],
                        uvdata1[0], 1 - uvdata1[1],
                        uvdata2[0], 1 - uvdata2[1],
                        maxvertexindex,
                        vertex_index in face_no_merge_vertices
                    ))
                    maxvertexindex += 1

            # Remove the generated preview mesh
            bpy.data.meshes.remove(mesh)

        subset.boundingr = sqrt(max_v_len_squared)

        # Optimize mesh
        if self.config.optimizeMesh:
            new_vidx = zusicommon.optimize_mesh(vertexdata, self.config.maxCoordDelta, self.config.maxUVDelta, self.config.maxNormalAngle)
            facedata = [(new_vidx[entry[0]], new_vidx[entry[1]], new_vidx[entry[2]]) for entry in facedata]
            num_deleted_vertices = sum(v is None for v in vertexdata)
            info("Mesh optimization: {} of {} vertices deleted", num_deleted_vertices, len(vertexdata))

        if self.lsbwriter is not None:
            self.lsbwriter.add_subset_data(subsetNode, vertexdata, facedata)
        else:
            # Generating all <Vertex> and <Face> nodes via the xmldoc functions is slooooow.
            # Insert a placeholder text node instead and replace that with the manually generated
            # XML string for the <Vertex> and <Face> nodes. Yes, this is ugly.
            placeholder_node = self.xmldoc.createTextNode(SUBSET_XML_PLACEHOLDER.format(len(self.subset_data)))
            subsetNode.appendChild(placeholder_node)
            self.subset_data.append((vertexdata, facedata))

    # Returns a string containing the <Vertex> and <Face> nodes for the given vertex and face data.
    def get_subset_xml(self, vertexdata, facedata):
        return (os.linesep + "      ").join([
            '<Vertex U="' + str(entry[6]) + '" V="' + str(entry[7])
            + '" U2="' + str(entry[8]) + '" V2="' + str(entry[9]) + '">'
            + '<p X="' + str(entry[0]) + '" Y="' + str(entry[1]) + '" Z="' + str(entry[2]) + '"/>'
            + '<n X="' + str(entry[3]) + '" Y="' + str(entry[4]) + '" Z="' + str(entry[5]) + '"/>'
            + '</Vertex>'
            for entry in vertexdata if entry is not None
        ] + [
            '<Face i="' + ";".join(map(str, entry)) + '"/>'
            for entry in facedata
        ])

    def write_subset_material(self, subsetNode, material):
        # Set ambient, diffuse, and emit color.
        # Zusi's lighting model works as follows:
        # An object will always have its night color (day and night).
        # By day the diffuse and ambient color are added to the night color.
        # It follows from this that an object can only get darker at night, not lighter.

        diffuse_color = material.diffuse_color * material.diffuse_intensity
        ambient_color = material.zusi_ambient_color if material.zusi_use_ambient else Color((1, 1, 1))

        # Adjust emit color to be always darker than the diffuse and ambient color.
        emit_color = material.zusi_emit_color if material.zusi_use_emit else Color((0, 0, 0))
        emit_color = Color((
            min(emit_color.r, diffuse_color.r, ambient_color.r),
            min(emit_color.g, diffuse_color.g, ambient_color.g),
            min(emit_color.b, diffuse_color.b, ambient_color.b),
        ))

        # Subtract emit color from the diffuse and ambient color.
        if material.zusi_use_emit:
            diffuse_color -= emit_color
            ambient_color -= emit_color

        # Add overexposure to the diffuse color.
        if material.zusi_allow_overexposure:
            diffuse_color = normalize_color(diffuse_color + material.zusi_overexposure_addition)
            ambient_color = normalize_color(ambient_color + material.zusi_overexposure_addition_ambient)

        subsetNode.setAttribute("C", rgba_to_hex_string(diffuse_color, material.alpha))
        if material.zusi_use_ambient:
            subsetNode.setAttribute("CA", rgba_to_hex_string(ambient_color,
                material.zusi_ambient_alpha))
        if material.zusi_use_emit:
            # Emit alpha is ignored in Zusi.
            subsetNode.setAttribute("E", rgba_to_hex_string(emit_color, 0))

        renderFlagsNode = self.xmldoc.createElement("RenderFlags")
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
                texflagsNode = self.xmldoc.createElement(node_name)
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
                renderFlagsNode.appendChild(texflagsNode)
        
        subsetNode.appendChild(renderFlagsNode)

        # Write textures
        for texture_slot in self.get_active_texture_slots(material):
            texture_node = self.xmldoc.createElement("Textur")
            datei_node = self.xmldoc.createElement("Datei")
            datei_node.setAttribute("Dateiname", self.relpath(texture_slot.texture.image.filepath))
            texture_node.appendChild(datei_node)
            subsetNode.appendChild(texture_node)

    def write_animation(self, ob, animation_node, write_translation = True, write_rotation = True):
        """Writes an animation into an animation node (<MeshAnimation> or <VerknAnimation>) and
        returns the length of the longest translation vector of the animation
        (or 0 if write_translation is False)."""
        animation = self.animations[ob]
        translation_length = 0

        # Get frame numbers of the 0.0 and 1.0 frames.
        frame0 = self.config.context.scene.frame_start
        frame1 = self.config.context.scene.frame_end

        # Get frame numbers of keyframes.
        keyframe_nos = set([round(keyframe.co.x) for fcurve in animation.fcurves for keyframe in fcurve.keyframe_points])

        # Write keyframes.
        original_current_frame = self.config.context.scene.frame_current
        previous_rotation = None
        for keyframe_no in sorted(keyframe_nos):
            aniPunktNode = self.xmldoc.createElement("AniPunkt")
            aniPunktNode.setAttribute("AniZeit", str(float(keyframe_no - frame0) / (frame1 - frame0)))
            animation_node.appendChild(aniPunktNode)
            self.config.context.scene.frame_set(keyframe_no)
            loc, rot, scale = ob.matrix_local.decompose()

            if write_translation:
                translationNode = (None if loc == Vector((0.0, 0.0, 0.0))
                    else self.xmldoc.createElement("p"))
                if translationNode is not None:
                    fill_node_xyz(translationNode, -loc.y, loc.x, loc.z)
                    aniPunktNode.appendChild(translationNode)
                    translation_length = max(translation_length, vector_xy_length(loc))

            if write_rotation:
                # Make rotation Euler compatible with the previous frame to prevent axis flipping.
                if previous_rotation is not None:
                    rot_euler = rot.to_matrix().to_euler('YXZ', previous_rotation)
                else:
                    rot_euler = rot.to_matrix().to_euler('YXZ')
                previous_rotation = rot_euler

                # Convert rotation into Zusi's coordinate system.
                rot_euler_swapped = Euler((-rot_euler.y, rot_euler.x, rot_euler.z))
                rotation = rot_euler_swapped.to_quaternion()

                rotationNode = (None if rotation == Vector((0.0, 0.0, 0.0, 0.0))
                    else self.xmldoc.createElement("q"))
                if rotationNode is not None:
                    if rotation.x != 0.0:
                        rotationNode.setAttribute("X", str(rotation.x))
                    if rotation.y != 0.0:
                        rotationNode.setAttribute("Y", str(rotation.y))
                    if rotation.z != 0.0:
                        rotationNode.setAttribute("Z", str(rotation.z))
                    if rotation.w != 0.0:
                        rotationNode.setAttribute("W", str(rotation.w))
                    aniPunktNode.appendChild(rotationNode)
        self.config.context.scene.frame_set(original_current_frame)
        return translation_length

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

    # Returns a set of all animations of objects in this file and linked files.
    def get_animations_for_file(self, ls3file, include_root = False):
        result = set()
        for ob in ls3file.objects:
            if ob == ls3file.root_obj and not include_root:
                continue
            animation = self.animations[ob]
            if animation is not None:
                result.add(animation)
        for linked_file in ls3file.linked_files:
            result |= self.get_animations_for_file(linked_file, True)
        return result

    # Build list of files from the scene's objects. The main file will always be the first item in the list.
    def get_files(self):
        split_file_name = self.config.fileName.split(os.extsep, 1)
        if len(split_file_name) > 1:
            basename, ext = split_file_name[0], (os.extsep + split_file_name[1])
        else:
            basename, ext = split_file_name[0], ""
        main_file = Ls3File()
        main_file.filename = self.config.fileName
        main_file.objects = set(self.config.context.scene.objects.values())
        main_file.is_main_file = True
        work_list = [main_file]

        # The resulting files are indexed by their root object. The main file is the only file without a root object.
        result = { None : main_file }

        while len(work_list):
            cur_file = work_list.pop()

            # If there is an object which needs its own file, we "split" this object and its descendants
            # into a separate file.
            splitobj = None
            for ob in sorted(cur_file.objects, key = lambda ob: ob.name):
                if ob != cur_file.root_obj and self.must_start_new_file(ob):
                    splitobj = ob
                    break

            if splitobj is not None:
                # Place this object and all its children into a new file.
                new_file = Ls3File()
                new_file.filename = basename + "_" + splitobj.name + ext
                new_file.root_obj = splitobj
                new_file.objects = set([splitobj])
                new_file.objects |= get_children_recursive(splitobj)
                new_file.is_main_file = False

                cur_file.objects -= new_file.objects
                work_list.append(new_file)
                result[splitobj] = new_file
                work_list.append(cur_file) # TODO: needs more work, splitobj might not have been the only splitting object!

        # Get subsets and create linked file relation according to parent relation.
        for root_obj, ls3file in result.items():
            ls3file.subsets = self.get_subsets(ls3file)
            if ls3file.root_obj is not None and (len(ls3file.subsets) > 0 or len(ls3file.linked_files) > 0):
                parent_root = ls3file.root_obj.parent
                while parent_root is not None and parent_root not in result:
                    parent_root = parent_root.parent
                result[parent_root].linked_files.append(ls3file)

        debug("Files:")
        for root_obj, ls3file in result.items():
            debug(root_obj.name if root_obj is not None else "None")
            for sub in ls3file.subsets:
                debug("   {} - {}", str(sub.identifier), str(sub.objects))

        # Main file is the first item in the list.
        return [result[None]] + [ls3file for ls3file in result.values() if ls3file.root_obj is not None]

    def get_exported_subsets(self):
        """Builds a list of exported subset identifiers for every object in the scene. The export settings
        (e.g. "export only selected objects") are taken into account."""

        result = {}
        # A set of all subset identifiers that will be exported. It is only filled when
        # self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS.
        all_exported_identifiers = set()

        for ob in self.config.context.scene.objects:
            # For "export subsets of selected objects" mode, only treat selected objects in the first phase.
            if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS and ob.name not in self.config.selectedObjects:
                continue

            # If export setting is "export only selected objects", filter out unselected objects
            # from the beginning. Also, non-mesh objects are not exported.
            if (ob.type != 'MESH' or
                    (self.config.exportSelected == EXPORT_SELECTED_OBJECTS and
                            ob.name not in self.config.selectedObjects)):
                result[ob] = []
                continue

            result[ob] = [SubsetIdentifier(ob.zusi_subset_name, mat,
                    ob if self.is_animated(ob) else None)
                    for mat in get_used_materials_for_object(ob)
                    if self.config.exportSelected != EXPORT_SELECTED_MATERIALS or (mat is not None and mat.name in self.config.selectedObjects)]
            if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS:
                all_exported_identifiers |= set(result[ob])
            # Selected objects that are not visible in the current variants can still influence
            # the exported subsets.
            if not zusicommon.is_object_visible(ob, self.config.variantIDs):
                result[ob] = []

        # For "export subsets of selected objects" mode, we need a second pass
        # for all unselected objects which might have a subset in common with
        # a selected object.
        if self.config.exportSelected == EXPORT_SUBSETS_OF_SELECTED_OBJECTS:
            for ob in self.config.context.scene.objects:
                if ob.type != 'MESH' or not zusicommon.is_object_visible(ob, self.config.variantIDs):
                    result[ob] = []
                    continue
                if ob.name in self.config.selectedObjects:
                    continue
                result[ob] = []
                for mat in get_used_materials_for_object(ob):
                    identifier = SubsetIdentifier(ob.zusi_subset_name, mat,
                        ob if self.is_animated(ob) else None)
                    if identifier in all_exported_identifiers:
                        result[ob].append(identifier)
 
        return result

    # Build list of subsets from a file's objects. The subsets are ordered by name.
    def get_subsets(self, ls3file):
        subset_dict = dict()

        # Build list of subsets according to material and subset name settings.
        for ob in ls3file.objects:
            for subset_identifier in self.exported_subset_identifiers[ob]:
                # XXX
                if subset_identifier.animated_obj is None:
                    p = ob.parent
                    while p is not None:
                        if self.is_animated(p):
                            subset_identifier.animated_obj = p
                            break
                        p = p.parent
                if subset_identifier not in subset_dict:
                    subset_dict[subset_identifier] = Ls3Subset(subset_identifier)
                subset_dict[subset_identifier].objects.append(ob)
 
        # Sort subsets by name and filter out empty subsets and subsets that won't be visible due
        # to variant export settings (when exportSelected mode is "2").
        return [subset_dict[name] for name in sorted(subset_dict.keys())]

    def write_ls3(self, ls3file):
        sce = self.config.context.scene

        if self.use_lsb:
            from . import lsb
            self.lsbwriter = lsb.LsbWriter()
        else:
            self.lsbwriter = None

        # Create a new XML document
        self.xmldoc = dom.getDOMImplementation().createDocument(None, "Zusi", None)

        self.subset_data = []

        # Write file info
        infoNode = self.xmldoc.createElement("Info")
        infoNode.setAttribute("DateiTyp", "Landschaft")
        infoNode.setAttribute("Version", "A.1")
        infoNode.setAttribute("MinVersion", "A.1")

        if sce.zusi_object_id != bpy.types.Scene.zusi_object_id[1]["default"]:
            infoNode.setAttribute("ObjektID", sce.zusi_object_id)
        if sce.zusi_license != bpy.types.Scene.zusi_license[1]["default"]:
            infoNode.setAttribute("Lizenz", sce.zusi_license)
        if sce.zusi_description != bpy.types.Scene.zusi_description[1]["default"]:
            infoNode.setAttribute("Beschreibung", sce.zusi_description)
        # TODO: Einsatz ab/bis
        self.xmldoc.documentElement.appendChild(infoNode)

        for author in sce.zusi_authors:
            autorEintragNode = self.xmldoc.createElement("AutorEintrag")

            if author.id != 0:
                autorEintragNode.setAttribute("AutorID", str(author.id))
            if author.name != zusiprops.ZusiAuthor.name[1]["default"]:
                autorEintragNode.setAttribute("AutorName", author.name)
            if author.email != zusiprops.ZusiAuthor.email[1]["default"]:
                autorEintragNode.setAttribute("AutorEmail", author.email)
            if ls3file.is_main_file and author.effort != zusiprops.ZusiAuthor.effort[1]["default"]:
                autorEintragNode.setAttribute("AutorAufwand", str(author.effort))
            if author.remarks != zusiprops.ZusiAuthor.remarks[1]["default"]:
                autorEintragNode.setAttribute("AutorBeschreibung", author.remarks)

            infoNode.appendChild(autorEintragNode)

        # Write the Landschaft node.
        landschaftNode = self.xmldoc.createElement("Landschaft")
        self.xmldoc.documentElement.appendChild(landschaftNode)

        # Write linked files.
        for linked_file in ls3file.linked_files:
            translation = linked_file.root_obj.matrix_local.to_translation()
            rotation = linked_file.root_obj.matrix_local.to_euler('YXZ')
            scale = linked_file.root_obj.matrix_local.to_scale()
            max_scale_factor = max(scale.x, scale.y, scale.z)
            scaled_boundingr = linked_file.boundingr * max_scale_factor

            verknuepfteNode = self.xmldoc.createElement("Verknuepfte")
            verknuepfteNode.setAttribute("BoundingR", str(int(ceil(scaled_boundingr))))
            dateiNode = self.xmldoc.createElement("Datei")
            dateiNode.setAttribute("Dateiname", linked_file.filename)
            verknuepfteNode.appendChild(dateiNode)
            landschaftNode.appendChild(verknuepfteNode)

            # Include location and rotation in the link information if they are
            # not animated.
            write_translation = not has_location_animation(self.animations[linked_file.root_obj])
            if write_translation:
                if translation != Vector((0.0, 0.0, 0.0)):
                    pNode = self.xmldoc.createElement("p")
                    fill_node_xyz(pNode, -translation.y, translation.x, translation.z)
                    verknuepfteNode.appendChild(pNode)
                ls3file.boundingr = max(ls3file.boundingr,
                    max_scale_factor * scaled_boundingr + vector_xy_length(translation))

            write_rotation = not has_rotation_animation(self.animations[linked_file.root_obj])
            if write_rotation and rotation != Vector((0.0, 0.0, 0.0)):
                phiNode = self.xmldoc.createElement("phi")
                fill_node_xyz(phiNode, -rotation.y, rotation.x, rotation.z)
                verknuepfteNode.appendChild(phiNode)

            # Always include scale in the link information because this cannot be animated.
            if scale != Vector((1.0, 1.0, 1.0)):
                skNode = self.xmldoc.createElement("sk")
                fill_node_xyz(skNode, scale.y, scale.x, scale.z)
                verknuepfteNode.appendChild(skNode)

        # Write subsets.
        for subset in ls3file.subsets:
            self.write_subset(landschaftNode, subset, ls3file)
            ls3file.boundingr = max(ls3file.boundingr, subset.boundingr)

        # Get animations and their animation numbers.
        animations = self.get_animations_for_file(ls3file) if self.config.exportAnimations else []
        animations_by_type = dict()
        for animation in animations:
            ani_type = animation.zusi_animation_type
            if ani_type not in animations_by_type:
                animations_by_type[ani_type] = [animation]
            else:
                animations_by_type[ani_type].append(animation)

        # Collect mesh animations and linked animations as tuples (ani no., subset/linked file).
        # The root subset of a file is not animated via a subset animation, but rather via a
        # linked animation in the parent file.
        animated_subsets = [(idx + 1, subset)
            for (idx, subset) in enumerate(ls3file.subsets)
            if subset.identifier.animated_obj is not None and not is_root_subset(subset, ls3file)]
        animated_linked_files = [(len(ls3file.subsets) + idx + 1, linked)
            for (idx, linked) in enumerate(ls3file.linked_files)
            if self.is_animated(linked_file.root_obj)]

        # Write animation declarations for this file and any linked file.
        for ani_type in sorted(animations_by_type.keys()):
            animations = animations_by_type[ani_type]

            # For animation type 0, the animation name is relevant. A separate <Animation> node is written for
            # each animation name. For all other animation types, only one <Animation> node is written for
            # all animations of this type, using a generic name.
            if ani_type == "0":
                # For each animation name, collect the actions that participate in this animation.
                animations_by_name = dict()
                for animation in animations:
                    if len(animation.zusi_animation_names) == 0:
                        name = get_ani_description(ani_type)
                        if name not in animations_by_name:
                            animations_by_name[name] = set()
                        animations_by_name[name].add(animation)
                    else:
                        for name_wrapper in animation.zusi_animation_names:
                            name = name_wrapper.name
                            if name not in animations_by_name:
                                animations_by_name[name] = set()
                            animations_by_name[name].add(animation)

                # Write the animations ordered by name.
                for name in sorted(animations_by_name.keys()):
                    aninrs = self.get_aninrs(animations_by_name[name], animated_linked_files, animated_subsets)

                    animationNode = self.xmldoc.createElement("Animation")
                    animationNode.setAttribute("AniID", ani_type)
                    animationNode.setAttribute("AniBeschreibung", name)
                    landschaftNode.appendChild(animationNode)

                    # Write <AniNrs> nodes.
                    aninrs = self.get_aninrs(animations_by_name[name], animated_linked_files, animated_subsets)
                    for aninr in aninrs:
                        aniNrsNode = self.xmldoc.createElement("AniNrs")
                        aniNrsNode.setAttribute("AniNr", str(aninr))
                        animationNode.appendChild(aniNrsNode)

            else:
                animationNode = self.xmldoc.createElement("Animation")
                animationNode.setAttribute("AniID", ani_type)
                animationNode.setAttribute("AniBeschreibung", get_ani_description(ani_type))
                landschaftNode.appendChild(animationNode)

                # Write <AniNrs> nodes.
                aninrs = self.get_aninrs(animations, animated_linked_files, animated_subsets)
                for aninr in aninrs:
                    aniNrsNode = self.xmldoc.createElement("AniNrs")
                    aniNrsNode.setAttribute("AniNr", str(aninr))
                    animationNode.appendChild(aniNrsNode)

        # Write animation definitions for subsets and links in this file.

        # Write mesh subset animations.
        for aninr, subset in animated_subsets:
            meshAnimationNode = self.xmldoc.createElement("MeshAnimation")
            meshAnimationNode.setAttribute("AniNr", str(aninr))
            meshAnimationNode.setAttribute("AniIndex", str(ls3file.subsets.index(subset)))
            meshAnimationNode.setAttribute("AniGeschw", str(self.animations[subset.identifier.animated_obj].zusi_animation_speed))
            landschaftNode.appendChild(meshAnimationNode)
            translation_length = self.write_animation(subset.identifier.animated_obj, meshAnimationNode,
                write_translation = subset.identifier.animated_obj != ls3file.root_obj,
                write_rotation = subset.identifier.animated_obj != ls3file.root_obj)
            ls3file.boundingr = max(ls3file.boundingr, translation_length + subset.boundingr)

        # Write linked animations.
        for aninr, linked_file in animated_linked_files:
            verknAnimationNode = self.xmldoc.createElement("VerknAnimation")
            verknAnimationNode.setAttribute("AniNr", str(aninr))
            verknAnimationNode.setAttribute("AniIndex", str(ls3file.linked_files.index(linked_file)))
            verknAnimationNode.setAttribute("AniGeschw", str(self.animations[linked_file.root_obj].zusi_animation_speed))
            landschaftNode.appendChild(verknAnimationNode)
            translation_length = self.write_animation(linked_file.root_obj, verknAnimationNode,
                write_translation = has_location_animation(self.animations[linked_file.root_obj]),
                write_rotation = has_rotation_animation(self.animations[linked_file.root_obj]))
            ls3file.boundingr = max(ls3file.boundingr, translation_length + linked_file.boundingr)

        # Get path names
        filepath = os.path.join(
            os.path.realpath(os.path.expanduser(self.config.fileDirectory)),
            ls3file.filename)

        if self.lsbwriter is not None:
            (basename, ext) = os.path.splitext(filepath)
            lsbpath = basename + ".lsb"
        
            fp = open(lsbpath, 'wb')
            info('Exporting LSB file {}', lsbpath)
            self.lsbwriter.write_to_file(fp)

            lsbNode = self.xmldoc.createElement("lsb")
            lsbNode.setAttribute("Dateiname", os.path.basename(lsbpath))
            landschaftNode.appendChild(lsbNode)

        # Write XML document to file
        info('Exporting LS3 file {}', filepath)
        with open(filepath, 'wb') as fp:
            prettyxml = self.xmldoc.toprettyxml(indent = "  ", encoding = "UTF-8", newl = os.linesep)
            if self.lsbwriter is None:
                for index, (vertexdata, facedata) in enumerate(self.subset_data):
                    prettyxml = prettyxml.replace(
                            bytearray(SUBSET_XML_PLACEHOLDER.format(index), 'utf-8'),
                            bytearray(self.get_subset_xml(vertexdata, facedata), 'utf-8'))
            fp.write(prettyxml)

        info("Bounding radius: {} m", int(ceil(ls3file.boundingr)))

    def export_ls3(self):
        debug("Exported subset IDs:")
        debug(self.exported_subset_identifiers)
        ls3files = self.get_files()

        # ls3files forms a tree, traverse it in postorder so that each file has all information (bounding radius)
        # about its linked files.
        work_list = [ls3files[0]]
        write_list = []

        while len(work_list):
            cur_file = work_list.pop()
            write_list.insert(0, cur_file)
            work_list.extend(cur_file.linked_files)

        for ls3file in write_list:
            self.write_ls3(ls3file)
