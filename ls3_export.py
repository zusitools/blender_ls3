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
from math import ceil, pi
from mathutils import *

# Converts a color value (of type Color) and an alpha value (value in [0..1])
# to a hex string "0AABBGGRR"
rgba_to_hex_string = lambda color, alpha : "0{:02X}{:02X}{:02X}{:02X}".format(*[round(x * 255) for x in [alpha, color.b, color.g, color.r]])

# The default settings for the exporter
default_export_settings = {
    "exportSelected" : "0",
    "exportAnimations" : False,
    "optimizeMesh" : True,
    "maxCoordDelta" : 0.001,
    "maxUVDelta" : 0.02,
    "maxNormalAngle" : 10 / 360 * 2 * pi,
}

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

# Returns a list of all descendants of the given object.
def get_children_recursive(ob):
    result = set(ob.children)
    for child in ob.children:
        result |= get_children_recursive(child)
    return result

def get_animation(ob):
    """Returns the action controlling the animation of the specified object,
    or None if the object's animation is not controlled by an action."""
    if ob.animation_data is not None and ob.animation_data.action is not None:
        return ob.animation_data.action
    if len(ob.constraints) > 0 and ob.parent is not None:
        # Find animated parent
        return get_animation(ob.parent)
    return None

def get_ani_description(ani_id):
    for animation_type in zusiprops.animation_types:
        if animation_type[0] == ani_id:
            return animation_type[1]
    return ""

def get_aninrs(animations, animated_linked_files, animated_subsets):
    """Returns the animation numbers for a list of animations. The animation number corresponds to the
    1-indexed number of the subset/linked file that has the animation."""
    return [aninr for aninr, linked in animated_linked_files if get_animation(linked.root_obj) in animations] \
        + [aninr for aninr, subset in animated_subsets if get_animation(subset.animated_obj) in animations]

def has_location_animation(action):
    return action is not None and any([fcurve.data_path == "location" for fcurve in action.fcurves])

def has_rotation_animation(action):
    return action is not None and any([fcurve.data_path.startswith("rotation") for fcurve in action.fcurves])

def is_root_subset(sub, ls3file):
    return ls3file.root_obj in sub.objects

# Returns a set of all animations of objects in this file and linked files.
def get_animations_recursive(ls3file, include_root = False):
    result = set()
    for ob in ls3file.objects:
        if ob == ls3file.root_obj and not include_root:
            continue
        animation = get_animation(ob)
        if animation is not None:
            result.add(animation)
    for linked_file in ls3file.linked_files:
        result |= get_animations_recursive(linked_file, True)
    return result

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
#     material: The Blender material of this subset.
#     objects: The objects to include in this subset.
#     animated_obj: The object that defines this subset's animation, or None.
class Ls3Subset:
    def __init__(self):
        self.material = None
        self.objects = []
        self.animated_obj = None
        self.boundingr = 0

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

        try:
            from . import zusiconfig
            self.use_lsb = zusiconfig.use_lsb
        except:
            self.use_lsb = False

        # Initialize map of Blender Z bias values (float) to integer values
        # e.g. if values (-0.1, -0.05, 0, 0.1) appear in the scene, they will be
        # mapped to (-2, -1, 0, 1).
        zbiases_pos = sorted([mat.offset_z for mat in bpy.data.materials if mat.offset_z > 0])
        zbiases_neg = sorted([mat.offset_z for mat in bpy.data.materials if mat.offset_z < 0], reverse = True)

        self.z_bias_map = { 0.0 : 0 }
        self.z_bias_map.update(dict((value, idx + 1) for idx, value in enumerate(zbiases_pos)))
        self.z_bias_map.update(dict((value, -(idx + 1)) for idx, value in enumerate(zbiases_neg)))

    # Convert a Blender path to a path where Zusi can find the specified file.
    # Returns
    #  - only the file name: if the file resides in the same directory as the .ls3 file
    #  - a path relative to the Zusi data directory: if "path" is in a sub-directory of the Zusi data directory
    #  - an absolute path: otherwise
    # The path separator will always be a backslash, regardless of the operating system
    def relpath(self, path):
        path = os.path.realpath(bpy.path.abspath(path))
        (dirname, filename) = os.path.split(path)

        if dirname + os.sep == self.config.fileDirectory:
            return filename
        else:
            # Check whether "path" is in a subdirectory of the Zusi data path
            # Source: http://stackoverflow.com/questions/3812849/how-to-check-whether-a-directory-is-a-sub-directory-of-another-directory
            datadir = os.path.realpath(zusicommon.get_zusi_data_path())
            commonprefix = os.path.commonprefix([path, datadir])

            if commonprefix == datadir:
                return os.path.relpath(path, datadir).replace(os.sep, "\\")
            else:
                return path.replace(os.sep, "\\")


    # Returns whether the specified object and its children must be placed in their own file
    # in order to be animated correctly.
    def must_start_new_file(self, ob):
        # Objects with children start a new file.
        return self.config.exportAnimations and len(ob.children) > 0

    def is_animated(self, ob):
        return self.config.exportAnimations and (
             ob.animation_data is not None and ob.animation_data.action is not None \
             or (len(ob.constraints) > 0 and get_animation(ob) is not None))

    # Returns a list of the active texture slots of the given material.
    def get_active_texture_slots(self, material):
        if material:
            # If no variants are defined, the visibility of the texture slot is taken into account.
            variants_defined = len(self.config.context.scene.zusi_variants) > 0

            # Create a list of image textures
            image_texture_slots = [material.texture_slots[texture_slot]
                for texture_slot in material.texture_slots.keys()
                    if material.texture_slots[texture_slot].texture.type == "IMAGE"
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
        material = subset.material
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

        self.write_subset_mesh(subsetNode, subset, ls3file)
        landschaftNode.appendChild(subsetNode)

    # Writes the meshes of the subset's objects to the specified subset node.
    # Only the faces having the specified material will be written.
    def write_subset_mesh(self, subsetNode, subset, ls3file):
        vertexdata = []
        facedata = []
        material = subset.material
        active_texture_slots = self.get_active_texture_slots(material)
        active_uvmaps = [slot.uv_layer for slot in active_texture_slots]
        
        for ob in subset.objects:
            # Apply modifiers and transform the mesh so that the vertex coordinates
            # are global coordinates. Also recalculate the vertex normals.
            mesh = ob.to_mesh(self.config.context.scene, True, "PREVIEW")

            # Apply the object's transformation only for subsets which are not root subsets of their file
            # (for the root subsets, the transformation will be written into the link in the parent file).
            # For animated subsets, apply only the scale part (the translation and rotation part will be
            # written as part of the animation).
            if self.config.exportAnimations:
                if not is_root_subset(subset, ls3file):
                    if ob == subset.animated_obj:
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
                # Ignore everything when animated export is enabled and just apply the global transformation.
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

            # Write vertices, faces and UV coordinates.
            # Access faces via the tessfaces API which provides only triangles and quads.
            # A vertex that appears in two faces with different normals or different UV coordinates will
            # have to be exported as two Zusi vertices. Therefore, all vertices are exported once per face,
            # and mesh optimization will later re-merge vertices that have the same location, normal, and
            # UV coordinates.
            for face_index, face in enumerate(mesh.tessfaces):
                vertexindex = len(vertexdata)

                # Check if the face has the right material.
                if material is not None and ob.data.materials[face.material_index] != material:
                    continue

                # Write the first triangle of the face
                # Optionally reverse order of faces to flip normals
                if must_flip_normals:
                    facedata.append([vertexindex + 2, vertexindex + 1, vertexindex])
                else:
                    facedata.append([vertexindex, vertexindex + 1, vertexindex + 2])

                # If the face is a quad, write the second triangle too.
                if len(face.vertices) == 4:
                    if must_flip_normals:
                        facedata.append([vertexindex, vertexindex + 3, vertexindex + 2])
                    else:
                        facedata.append([vertexindex + 2, vertexindex + 3, vertexindex])

                # Compile a list of all vertices to mark as "don't merge".
                # Those are the vertices that form a sharp edge in the current face.
                face_no_merge_vertex_pairs = set(face.edge_keys).intersection(no_merge_vertex_pairs)
                face_no_merge_vertices = [pair[0] for pair in face_no_merge_vertex_pairs] + [pair[1] for pair in face_no_merge_vertex_pairs]

                # Write vertex coordinates (location, normal, and UV coordinates)
                for vertex_no, vertex_index in enumerate(face.vertices):
                    v = mesh.vertices[vertex_index]
                    uvdata1 = [0.0, 1.0]
                    uvdata2 = [0.0, 1.0]

                    for texindex in range(0, 2):
                        if texindex >= len(active_uvmaps):
                            continue

                        # Find UV layer with matching name (use active UV layer if no name
                        # is given.
                        uvlayer = None
                        if active_uvmaps[texindex] == "":
                            uvlayer = mesh.tessface_uv_textures.active
                        else:
                            uvlayers = [uvlayer for uvlayer in mesh.tessface_uv_textures
                                if uvlayer.name == active_uvmaps[texindex]]
                            if len(uvlayers):
                                uvlayer = uvlayers[0]

                        if uvlayer is None:
                            continue

                        uv_raw = uvlayer.data[face_index].uv_raw
                        uvdata = [uv_raw[2 * vertex_no], uv_raw[2 * vertex_no + 1]]
                        if texindex == 0:
                            uvdata1 = uvdata
                        else:
                            uvdata2 = uvdata

                    # Since the vertices are exported per-face, get the vertex normal from the face normal,
                    # except when the face is set to "smooth"
                    if face.use_smooth:
                        normal = [v.normal[1], -v.normal[0], -v.normal[2]]
                    else:
                        normal = [face.normal[1], -face.normal[0], -face.normal[2]]

                    if must_flip_normals:
                        normal = list(map(lambda x : -x, normal))

                    subset.boundingr = max(subset.boundingr, v.co.length)

                    # The coordinates are transformed into the Zusi coordinate system.
                    # The vertex index is appended for reordering vertices
                    vertexdata.append([
                        -v.co[1], v.co[0], v.co[2],
                        normal[0], normal[1], normal[2],
                        uvdata1[0], 1 - uvdata1[1],
                        uvdata2[0], 1 - uvdata2[1],
                        len(vertexdata),
                        vertex_index in face_no_merge_vertices
                    ])

            # Remove the generated preview mesh
            bpy.data.meshes.remove(mesh)

        # Optimize mesh
        if self.config.optimizeMesh:
            oldvertexcount = len(vertexdata)
            new_vidx = zusicommon.optimize_mesh(vertexdata, self.config.maxCoordDelta, self.config.maxUVDelta, self.config.maxNormalAngle)
            facedata = [[new_vidx[x] for x in entry[0:3]] for entry in facedata]
            print("Mesh optimization: %d vertices deleted" % (oldvertexcount - len(vertexdata)))

        if self.lsbwriter is not None:
            self.lsbwriter.add_subset_data(subsetNode, vertexdata, facedata)
        else:
            self.add_subset_data(subsetNode, vertexdata, facedata)

    # Writes <Vertex> and <Face> nodes to the given subset node
    def add_subset_data(self, subsetNode, vertexdata, facedata):
        for entry in vertexdata:
            vertexNode = self.xmldoc.createElement("Vertex")
            vertexNode.setAttribute("U", str(entry[6]))
            vertexNode.setAttribute("V", str(entry[7]))
            vertexNode.setAttribute("U2", str(entry[8]))
            vertexNode.setAttribute("V2", str(entry[9]))

            posNode = self.xmldoc.createElement("p")
            fill_node_xyz(posNode, *entry[0:3])

            normalNode = self.xmldoc.createElement("n")
            fill_node_xyz(normalNode, *entry[3:6])

            vertexNode.appendChild(posNode)
            vertexNode.appendChild(normalNode)
            subsetNode.appendChild(vertexNode)

        for entry in facedata:
            faceNode = self.xmldoc.createElement("Face")
            faceNode.setAttribute("i", ";".join(map(str, entry)))
            subsetNode.appendChild(faceNode)

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
        animation = get_animation(ob)
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
                    translation_length = max(translation_length, loc.length)

            if write_rotation:
                # Make rotation Euler compatible with the previous frame to prevent axis flipping.
                if previous_rotation is not None:
                    rot_euler = rot.to_matrix().to_euler('XYZ', previous_rotation)
                else:
                    rot_euler = rot.to_matrix().to_euler('XYZ')
                previous_rotation = rot_euler
                rotation = rot_euler.to_quaternion()

                rotationNode = (None if rotation == Vector((0.0, 0.0, 0.0, 0.0))
                    else self.xmldoc.createElement("q"))
                if rotationNode is not None:
                    if rotation.x != 0.0:
                        rotationNode.setAttribute("Y", str(rotation.x))
                    if rotation.y != 0.0:
                        rotationNode.setAttribute("X", str(rotation.y))
                    if rotation.z != 0.0:
                        rotationNode.setAttribute("Z", str(rotation.z))
                    if rotation.w != 0.0:
                        rotationNode.setAttribute("W", str(rotation.w))
                    aniPunktNode.appendChild(rotationNode)
        self.config.context.scene.frame_set(original_current_frame)
        return translation_length

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
        result = [main_file]

        while len(work_list):
            cur_file = work_list.pop()

            # If there is an object which needs its own file, we "split" this object and its descendants
            # into a separate file.
            splitobj = None
            for ob in cur_file.objects:
                if ob != cur_file.root_obj and self.must_start_new_file(ob):
                    splitobj = ob
                    break

            if splitobj is not None:
                # Place this object and all its children into a new file.
                new_file = Ls3File()
                new_file.filename = basename + "_" + ob.name + ext
                new_file.root_obj = ob
                new_file.objects = set([ob])
                new_file.objects |= get_children_recursive(ob)
                new_file.is_main_file = False

                cur_file.objects -= new_file.objects
                cur_file.linked_files.append(new_file)
                work_list.append(new_file)
                result.append(new_file)
                work_list.append(cur_file) # needs more work, splitobj might not have been the only splitting object!

        for ls3file in result:
            ls3file.subsets = self.get_subsets(ls3file)
        return result

    # Build list of subsets from a file's objects. The subsets are ordered by name.
    def get_subsets(self, ls3file):
        # Dictionary that maps a subset name to a Ls3Subset object.
        subset_dict = dict()

        # List of subsets that will be visible in the exported file
        # (only for exportSelected == "2")
        visible_subsets = set()
        
        # Build list of subsets according to material and subset name settings.
        for ob in ls3file.objects:
            # If export setting is "export only selected objects", filter out unselected objects
            # from the beginning.
            if ob.type == 'MESH' and (ob.name in self.config.selectedObjects or (self.config.exportSelected != "1")):

                # If the object specifies a subset name, this name will be prepended to the material name
                # and separated with a $ sign.
                subset_basename = ""
                if ob.zusi_subset_name != "":
                    subset_basename = ob.zusi_subset_name + "$"

                # Animated objects get their own subsets.
                if self.is_animated(ob):
                    subset_basename += ob.name + "$$"

                # Build list of materials used (i.e. assigned to any face) in this object
                used_materials = []

                if len(ob.data.materials) > 0:
                    used_material_indices = set([poly.material_index for poly in ob.data.polygons])
                    used_materials = [ob.data.materials[i] for i in used_material_indices]
                else:
                    used_materials = [None]

                # Add this object to every subset this object will be a part of.
                for mat in used_materials:
                    subset_name = subset_basename + ("no_material" if mat is None else mat.name)

                    # Create new subset object and write the material.
                    if subset_name not in subset_dict:
                        new_subset = Ls3Subset()
                        new_subset.material = mat
                        new_subset.animated_obj = ob if self.is_animated(ob) else None
                        subset_dict[subset_name] = new_subset

                    # A selected object that is not visible in the exported variant can still
                    # influcence the list of exported subsets when exportSelected is "2"
                    if ob.name in self.config.selectedObjects:
                        visible_subsets.add(subset_name)

                    # Append visible object to second entry of tuple
                    if zusicommon.is_object_visible(ob, self.config.variantIDs):
                        subset_dict[subset_name].objects.append(ob)

        # Sort subsets by name and filter out subsets that won't be visible due to variant export settings
        # (when exportSelected mode is "2")
        subsets = [subset_dict[name] for name in sorted(subset_dict.keys())
            if self.config.exportSelected != "2" or name in visible_subsets]

        return subsets

    def write_ls3(self, ls3file):
        sce = self.config.context.scene

        if self.use_lsb:
            from . import lsb
            self.lsbwriter = lsb.LsbWriter()
        else:
            self.lsbwriter = None

        # Create a new XML document
        self.xmldoc = dom.getDOMImplementation().createDocument(None, "Zusi", None)

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
            verknuepfteNode = self.xmldoc.createElement("Verknuepfte")
            verknuepfteNode.setAttribute("BoundingR", str(int(ceil(linked_file.boundingr))))
            dateiNode = self.xmldoc.createElement("Datei")
            dateiNode.setAttribute("Dateiname", linked_file.filename)
            verknuepfteNode.appendChild(dateiNode)
            landschaftNode.appendChild(verknuepfteNode)

            translation = linked_file.root_obj.matrix_local.to_translation()
            rotation = linked_file.root_obj.matrix_local.to_euler()
            scale = linked_file.root_obj.matrix_local.to_scale()
            max_scale_factor = max(scale.x, scale.y, scale.z)

            # Include location and rotation in the link information if they are
            # not animated.
            write_translation = not has_location_animation(get_animation(linked_file.root_obj))
            if write_translation and translation != Vector((0.0, 0.0, 0.0)):
                pNode = self.xmldoc.createElement("p")
                fill_node_xyz(pNode, -translation.y, translation.x, translation.z)
                verknuepfteNode.appendChild(pNode)
                ls3file.boundingr = max(ls3file.boundingr,
                    max_scale_factor * linked_file.boundingr + translation.length)
            elif write_translation:
                ls3file.boundingr = max(ls3file.boundingr,
                    max_scale_factor * linked_file.boundingr)

            write_rotation = not has_rotation_animation(get_animation(linked_file.root_obj))
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
        animations = get_animations_recursive(ls3file) if self.config.exportAnimations else []
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
        animated_subsets = [(idx + 1, sub)
            for (idx, sub) in enumerate(ls3file.subsets)
            if sub.animated_obj is not None and not is_root_subset(sub, ls3file)]
        animated_linked_files = [(idx + len(animated_subsets) + 1, linked)
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
                    aninrs = get_aninrs(animations_by_name[name], animated_linked_files, animated_subsets)

                    animationNode = self.xmldoc.createElement("Animation")
                    animationNode.setAttribute("AniID", ani_type)
                    animationNode.setAttribute("AniBeschreibung", name)
                    landschaftNode.appendChild(animationNode)

                    # Write <AniNrs> nodes.
                    aninrs = get_aninrs(animations_by_name[name], animated_linked_files, animated_subsets)
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
                aninrs = get_aninrs(animations, animated_linked_files, animated_subsets) 
                for aninr in aninrs:
                    aniNrsNode = self.xmldoc.createElement("AniNrs")
                    aniNrsNode.setAttribute("AniNr", str(aninr))
                    animationNode.appendChild(aniNrsNode)

        # Write animation definitions for subsets and links in this file.

        # Write mesh subset animations.
        for aninr, sub in animated_subsets:
            meshAnimationNode = self.xmldoc.createElement("MeshAnimation")
            meshAnimationNode.setAttribute("AniNr", str(aninr))
            meshAnimationNode.setAttribute("AniIndex", str(ls3file.subsets.index(sub)))
            meshAnimationNode.setAttribute("AniGeschw", str(get_animation(subset.animated_obj).zusi_animation_speed))
            landschaftNode.appendChild(meshAnimationNode)
            translation_length = self.write_animation(sub.animated_obj, meshAnimationNode,
                write_translation = sub.animated_obj != ls3file.root_obj,
                write_rotation = sub.animated_obj != ls3file.root_obj)
            ls3file.boundingr = max(ls3file.boundingr, translation_length + subset.boundingr)

        # Write linked animations.
        for aninr, linked_file in animated_linked_files:
            verknAnimationNode = self.xmldoc.createElement("VerknAnimation")
            verknAnimationNode.setAttribute("AniNr", str(aninr))
            verknAnimationNode.setAttribute("AniIndex", str(ls3file.linked_files.index(linked_file)))
            verknAnimationNode.setAttribute("AniGeschw", str(get_animation(linked_file.root_obj).zusi_animation_speed))
            landschaftNode.appendChild(verknAnimationNode)
            self.write_animation(linked_file.root_obj, verknAnimationNode,
                write_translation = has_location_animation(get_animation(linked_file.root_obj)),
                write_rotation = has_rotation_animation(get_animation(linked_file.root_obj)))

        # Get path names
        filepath = os.path.join(
            os.path.realpath(os.path.expanduser(self.config.fileDirectory)),
            ls3file.filename)

        if self.lsbwriter is not None:
            (basename, ext) = os.path.splitext(filepath)
            lsbpath = basename + ".lsb"
        
            fp = open(lsbpath, 'wb')
            print('Exporting %s' % lsbpath)
            self.lsbwriter.write_to_file(fp)

            lsbNode = self.xmldoc.createElement("lsb")
            lsbNode.setAttribute("Dateiname", os.path.basename(lsbpath))
            landschaftNode.appendChild(lsbNode)

        # Write XML document to file
        print('Exporting %s' % filepath)
        with open(filepath, 'wb') as fp:
            fp.write(self.xmldoc.toprettyxml(indent = "  ", encoding = "UTF-8", newl = os.linesep))

        print("Bounding radius: %d m" % int(ceil(ls3file.boundingr)))

    def export_ls3(self):
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
