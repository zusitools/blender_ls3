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
from math import ceil, sqrt, pi, pow
from mathutils import *

# Converts a color value (of type Color) and an alpha value (value in [0..1])
# to a hex string "0AABBGGRR"
rgba_to_hex_string = lambda color, alpha : "0{:02X}{:02X}{:02X}{:02X}".format(*[round(x * 255) for x in [alpha, color.b, color.g, color.r]])

# The default settings for the exporter
default_export_settings = {
    "exportSelected" : "0",
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

# Stores all the things that later go into one LS3 file.
#     file_name: The file name (without path) of this file.
#     subsets: The subsets in this file.
#     linked_files: The files linked to this file
#     animation: The animation of this file in the parent file.
class Ls3File:
    def __init__(self):
        self.is_main_file = False
        self.filename = ""
        self.subsets = []
        self.linked_files = []
        self.animation = None

# Stores information about one subset of a LS3 file.
#     material: The Blender material of this subset.
#     objects: The objects to include in this subset.
class Ls3Subset:
    def __init__(self):
        self.material = None
        self.objects = []

# Container for the exporter settings
class Ls3ExporterSettings:
    def __init__(self,
                context,
                filePath,
                fileName,
                fileDirectory,
                exportSelected,
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
            use_lsb = zusiconfig.use_lsb
        except:
            use_lsb = False
        
        if use_lsb:
            from . import lsb
            self.lsbwriter = lsb.LsbWriter()
        else:
            self.lsbwriter = None

        # Initialize map of Blender Z bias values (float) to integer values
        # e.g. if values (-0.1, -0.05, 0, 0.1) appear in the scene, they will be
        # mapped to (-2, -1, 0, 1).
        zbiases_pos = sorted([mat.offset_z for mat in bpy.data.materials if mat.offset_z > 0])
        zbiases_neg = sorted([mat.offset_z for mat in bpy.data.materials if mat.offset_z < 0], reverse = True)

        self.z_bias_map = { 0.0 : 0 }
        self.z_bias_map.update(dict((value, idx + 1) for idx, value in enumerate(zbiases_pos)))
        self.z_bias_map.update(dict((value, -(idx + 1)) for idx, value in enumerate(zbiases_neg)))

        self.boundingr = 0

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

    # Adds a new subset node to the specified <Landschaft> node.
    # A list of objects to be incorporated into that subset is given, as well as the material to be written.
    # Only the faces of the supplied objects having that particular material will be written.
    def write_subset(self, objects, material, landschaftNode):
        subsetNode = self.xmldoc.createElement("SubSet")
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

        self.write_subset_mesh(subsetNode, objects, material)
        landschaftNode.appendChild(subsetNode)

    # Writes the meshes of the specified objects to the specified subset node.
    # Only the faces having the specified material will be written.
    def write_subset_mesh(self, subsetNode, objects, material):
        vertexdata = []
        facedata = []
        active_texture_slots = self.get_active_texture_slots(material)
        active_uvmaps = [slot.uv_layer for slot in active_texture_slots]
        
        for ob in objects:
            # Apply modifiers and transform the mesh so that the vertex coordinates
            # are global coordinates. Also recalculate the vertex normals.
            mesh = ob.to_mesh(self.config.context.scene, True, "PREVIEW")
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

                    self.boundingr = max(self.boundingr, sqrt(pow(v.co[0], 2) + pow(v.co[1], 2) + pow(v.co[2], 2)))

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
        # Set ambient, diffuse, and emit color
        subsetNode.setAttribute("C", rgba_to_hex_string(material.diffuse_color * material.diffuse_intensity, material.alpha))
        if material.zusi_use_ambient:
            subsetNode.setAttribute("CA", rgba_to_hex_string(material.zusi_ambient_color, material.zusi_ambient_alpha))
        if material.zusi_use_emit:
            subsetNode.setAttribute("E", rgba_to_hex_string(material.zusi_emit_color, material.zusi_emit_alpha))

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

    # Build list of subsets from the scene's objects. Each entry in the list
    # contains a tuple: the list objects to export into that subset and the material of the faces to export.
    # The subsets are ordered by name.
    def get_subsets(self):
        # Dictionary that maps subset names to a tuple of a material and a list of objects in that subset
        subset_dict = dict()

        # List of subsets that will be visible in the exported file
        # (only for exportSelected == "2")
        visible_subsets = set()
        
        for ob in self.config.context.scene.objects:
            # If export setting is "export only selected objects", filter out unselected objects
            # from the beginning.
            if ob.type == 'MESH' and (ob.name in self.config.selectedObjects or (self.config.exportSelected != "1")):

                # If the object specifies a subset name, this name will be prepended to the material name
                # and separated with a $ sign.
                subset_basename = ""
                if ob.zusi_subset_name != "":
                    subset_basename = ob.zusi_subset_name + "$"

                # Build list of materials used (i.e. assigned to any face) in this object
                used_materials = []

                if len(ob.data.materials) > 0:
                    used_material_indices = set([poly.material_index for poly in ob.data.polygons])
                    used_materials = [ob.data.materials[i] for i in used_material_indices]
                else:
                    used_materials = [None]

                # Add this object to every subset this object will be a part of.
                for mat in used_materials:
                    if mat == None:
                        subset_name = "no_material"
                    else:
                        subset_name = subset_basename + mat.name

                    # Write material to first entry of tuple
                    if subset_name not in subset_dict:
                        subset_dict[subset_name] = (mat, [])

                    # A selected object that is not visible in the exported variant can still
                    # influcence the list of exported subsets when exportSelected is "2"
                    if ob.name in self.config.selectedObjects:
                        visible_subsets.add(subset_name)

                    # Append visible object to second entry of tuple
                    if zusicommon.is_object_visible(ob, self.config.variantIDs):
                        subset_dict[subset_name][1].append(ob)

        # Sort subsets by name and filter out subsets that won't be visible due to variant export settings
        # (when exportSelected mode is "2")
        subsets = [subset_dict[name] for name in sorted(subset_dict.keys())
            if self.config.exportSelected != "2" or name in visible_subsets]

        return subsets

    def write_ls3(self, ls3file):
        sce = self.config.context.scene

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

        # Write the landscape itself
        landschaftNode = self.xmldoc.createElement("Landschaft")
        self.xmldoc.documentElement.appendChild(landschaftNode)
        for idx, subset in enumerate(ls3file.subsets):
            self.write_subset(subset[1], subset[0], landschaftNode)

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
        fp = open(filepath, 'w')
        print('Exporting %s' % filepath)
        fp.write(self.xmldoc.documentElement.toprettyxml())

        print("Bounding radius: %d m" % int(ceil(self.boundingr)))

    def export_ls3(self):
        ls3file = Ls3File()
        ls3file.subsets = self.get_subsets()
        ls3file.filename = self.config.fileName;
        ls3file.is_main_file = True
        self.write_ls3(ls3file)
