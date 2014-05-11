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

import os
import bpy
import struct
import mathutils
import xml.dom.minidom as dom
from . import zusicommon
from math import pi

# Converts a hex string "0AABBGGRR" into a tuple of a Color object and an alpha value
hex_string_to_rgba = lambda str : (mathutils.Color((int(str[7:9], 16) / 255, int(str[5:7], 16) / 255, int(str[3:5], 16) / 255)), int(str[1:3], 16) / 255)

# Loads the data from a node's X, Y, and Z attributes into the given vector.
def fill_xyz_vector(node, vector):
    if node.getAttribute("X") != "":
        vector[0] = float(node.getAttribute("X"))
    if node.getAttribute("Y") != "":
        vector[1] = float(node.getAttribute("Y"))
    if node.getAttribute("Z") != "":
        vector[2] = float(node.getAttribute("Z"))

# Loads the data from a node's U and V attributes into the given vector.
# If suffix is specified, it is appended to the attribute name (e.g. suffix=2 → U2, V2)
def fill_uv_vector(node, vector, suffix = ""):
    if node.getAttribute("U" + suffix) != "":
        vector[0] = float(node.getAttribute("U" + suffix))
    if node.getAttribute("V" + suffix) != "":
        vector[1] = float(node.getAttribute("V" + suffix))

class Ls3ImporterSettings:
    def __init__(self,
                context,
                filePath,
                fileName,
                fileDirectory,
                loadAuthorInformation = True,
                loadLinked = True,
                location = [0.0, 0.0, 0.0],
                rotation = [0.0, 0.0, 0.0],
                scale = [1.0, 1.0, 1.0],
                lod_bit = 15
                ):
        self.context = context
        self.filePath = filePath
        self.fileName = fileName
        self.fileDirectory = fileDirectory
        self.loadAuthorInformation = loadAuthorInformation
        self.loadLinked = loadLinked
        self.location = location
        self.rotation = rotation
        self.scale = scale
        self.lod_bit = lod_bit

class Ls3Importer:
    def __init__(self, config):
        self.config = config

        # LSB reader
        try:
            from . import zusiconfig
            use_lsb = zusiconfig.use_lsb
        except:
            use_lsb = False
        
        if use_lsb:
            from . import lsb
            self.lsbreader = lsb.LsbReader()
        else:
            self.lsbreader = None

        # No. of current subset
        self.subsetno = 0

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

        # Path to Zusi data dir
        self.datapath = zusicommon.get_zusi_data_path()

    def visitNode(self, node):
        name = "visit" + node.nodeName + "Node"

        # Call the method "visit<node_name>Node"; if it does not exist, traverse the DOM tree recursively.
        # Normally we would just try to call it and catch an AttributeError, but this makes it really hard to
        # debug if an AttributeError is thrown *inside* the called function
        if name in dir(self):
            getattr(self, name)(node)
        else:
            for child in node.childNodes:
                self.visitNode(child)

    #
    # Visits a <SubSet> node.
    #
    def visitSubSetNode(self, node):
        self.subsetno += 1
        self.currentvertices = []
        self.currentfaces = []

        # Create new mesh
        self.currentmesh = bpy.data.meshes.new(self.config.fileName + "." + str(self.subsetno))

        # Create new object
        self.currentobject = bpy.data.objects.new(self.config.fileName + "." + str(self.subsetno), self.currentmesh)
        self.currentobject.location = self.config.location
        self.currentobject.rotation_euler = self.config.rotation
        self.currentobject.scale = self.config.scale
        bpy.context.scene.objects.link(self.currentobject)

        # Assign material to object
        mat = bpy.data.materials.new(self.config.fileName + "." + str(self.subsetno))
        self.currentmesh.materials.append(mat)

        # Set ambient/diffuse colors of mesh
        ambient_color = node.getAttribute("CA")
        diffuse_color = node.getAttribute("C")
        night_color = node.getAttribute("E")

        if diffuse_color != "":
            (mat.diffuse_color, mat.alpha) = hex_string_to_rgba(diffuse_color)
            mat.diffuse_intensity = 1

        if ambient_color != "":
            mat.zusi_use_ambient = True
            (mat.zusi_ambient_color, mat.zusi_ambient_alpha) = hex_string_to_rgba(ambient_color)
        else:
            mat.zusi_use_ambient = False

        if night_color != "":
            mat.zusi_use_emit = True
            (mat.zusi_emit_color, ignored) = hex_string_to_rgba(night_color)
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
        if node.getAttribute("TypGF") != "":
            mat.zusi_gf_type = node.getAttribute("TypGF")
        if node.getAttribute("Zwangshelligkeit") != "":
            mat.zusi_force_brightness = float(node.getAttribute("Zwangshelligkeit"))
        if node.getAttribute("zZoom") != "":
            mat.zusi_signal_magnification = float(node.getAttribute("zZoom"))

        # Visit child nodes (such as texture and vertices/faces)
        for child in node.childNodes:
            self.visitNode(child)

        # Read LSB file
        if self.lsbreader is not None and self.lsbreader.lsbfile is not None:
            (self.currentvertices, self.currentfaces) = self.lsbreader.read_subset_data(node)

        # Add vertex index and "no merge" flag at the end of the vertex tuple (for mesh optimization)
        self.currentvertices = [list(v) + [idx, False] for idx, v in enumerate(self.currentvertices)]

        # Separate UV data into array as vertices will be merged later
        # Convert coordinates into the Blender coordinate system
        uvdata = [(v[6], 1 - v[7], v[8], 1 - v[9]) for v in self.currentvertices]

        oldlen = len(self.currentvertices)
        # Join vertices that have the same coordinates and normal angles
        new_vidx = zusicommon.optimize_mesh(self.currentvertices, 0.001, 2, 2 * pi)
        print("Optimization: Removed " + str(oldlen - len(self.currentvertices)) + " vertices")

        # Fill the mesh with verts, edges, faces
        # Can't use mesh.from_pydata because it creates ngons, not tessfaces
        self.currentmesh.vertices.add(len(self.currentvertices))
        for idx, v in enumerate(self.currentvertices):
            # (x,y,z) coordinates are calculated as (y, -x, z) from Zusi coordinates to fit the Blender coordinate system.
            self.currentmesh.vertices[idx].co = [v[1], -v[0], v[2]]
            self.currentmesh.vertices[idx].normal = self.currentvertices[idx][3:6]

        self.currentmesh.tessfaces.add(len(self.currentfaces))
        for idx, f in enumerate(self.currentfaces):
            self.currentmesh.tessfaces[idx].vertices = list(map(lambda x : new_vidx[x], self.currentfaces[idx]))

        self.currentmesh.update(calc_edges = True)

    # Visits a <RenderFlags> node
    def visitRenderFlagsNode(self, node):
        if node.getAttribute("TexVoreinstellung") != "":
            self.currentmesh.materials[0].zusi_texture_preset = node.getAttribute("TexVoreinstellung")

    # Visits an <Info> node
    def visitInfoNode(self, node):
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
        if self.config.loadAuthorInformation:
            author = bpy.context.scene.zusi_authors.add()
            if node.getAttribute("AutorID") != "":
                author.id = int(node.getAttribute("AutorID"))
            if node.getAttribute("AutorAufwand") != "":
                author.effort = float(node.getAttribute("AutorAufwand"))
            author.name = node.getAttribute("AutorName")
            author.email = node.getAttribute("AutorEmail")
            author.remarks = node.getAttribute("AutorBeschreibung")

    #
    # Visits a <Verknuepfte> node.
    #
    def visitVerknuepfteNode(self, node):
        if not self.config.loadLinked:
            return

        if node.getAttribute("LODbit") != "" and (self.config.lod_bit & int(node.getAttribute("LODbit"))) == 0:
            return

        try:
            dateinode = [x for x in node.childNodes if x.nodeName == "Datei"][0] #may raise IndexError
            dateiname = zusicommon.resolve_file_path(dateinode.getAttribute("Dateiname"),
                self.config.fileDirectory, self.datapath)
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

            # Transform location into Zusi coordinates
            loc = [loc[1], -loc[0], loc[2]]

            (directory, filename) = os.path.split(dateiname)

            settings = Ls3ImporterSettings(
                self.config.context,
                dateiname,
                filename,
                directory,
                self.config.loadAuthorInformation,
                self.config.loadLinked,
                [loc[x] + self.config.location[x] for x in [0,1,2]],
                [rot[x] + self.config.rotation[x] for x in [0,1,2]],
                [scale[x] * self.config.scale[x] for x in [0,1,2]],
                self.config.lod_bit
            )

            importer = Ls3Importer(settings)
            importer.import_ls3()
        except(IndexError):
            pass

    #
    # Visits a <Landschaft> node.
    #
    # The lsb file has to be known before any subset, therefore explicitly look for the <lsb> node
    def visitLandschaftNode(self, node):
        if self.lsbreader is not None:
            try:
                lsbnode = [x for x in node.childNodes if x.nodeName == "lsb"][0] #may raise IndexError
                lsbname = zusicommon.resolve_file_path(lsbnode.getAttribute("Dateiname"),
                    self.config.fileDirectory, self.datapath)
                self.lsbreader.set_lsb_file(lsbname)
            except(IndexError):
                pass

        for child in node.childNodes:
            self.visitNode(child)

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
        self.currentfaces.append(tuple(map(int, node.getAttribute("i").split(";")))[::-1])

    #
    # Visits a <Textur> node.
    #
    def visitTexturNode(self, node):
        try:
            dateinode = [x for x in node.childNodes if x.nodeName == "Datei"][0] # may raise IndexError

            # Add texture to current object
            mat = self.currentmesh.materials[0]

            img = bpy.data.images.load(self.resolveFilePath(dateinode.getAttribute("Dateiname"))) # may raise RuntimeError
            tex = bpy.data.textures.new(self.config.fileName + "." + str(self.subsetno),  type='IMAGE')
            tex.image = img

            texslot = mat.texture_slots.add()
            texslot.texture = tex
            texslot.texture_coords = 'UV'
            texslot.blend_type = 'COLOR'

        except(IndexError,  RuntimeError):
            pass

    def import_ls3(self):
        self.subsetno = 0
        (shortName, ext) = os.path.splitext(self.config.fileName)
        print( "Opening LS3 file " + self.config.filePath)

        # Open the file as bytes, else a Unicode BOM at the beginning of the file could confuse the XML parser.
        fp = open(self.config.filePath, "rb")
        with dom.parse(fp) as xml:
            print("File read successfully")
            self.visitNode(xml.firstChild);
            print("Done")
