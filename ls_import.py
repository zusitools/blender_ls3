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
import bmesh
import struct
import mathutils
import xml.dom.minidom as dom
from . import zusicommon
from math import pi, radians

IMPORT_LINKED_NO = "0"
IMPORT_LINKED_AS_EMPTYS = "1"
IMPORT_LINKED_EMBED = "2"

# Converts value "BBGGRR" into a Color object
color_to_rgba = lambda color : mathutils.Color(((color & 0xFF) / 255.0, ((color >> 8) & 0xFF) / 255.0, ((color >> 16) & 0xFF) / 255.0))

def skipLine(fp, count = 1):
    for i in range(0, count):
        fp.readline()

def skipUntil(fp, terminator):
    while fp.readline() != terminator + "\n":
        pass

def read3floats(fp):
    return (float(fp.readline().replace(",", ".")), float(fp.readline().replace(",", ".")), float(fp.readline().replace(",", ".")))

zusi_rot_to_blender = lambda rot: (rot[0], -rot[1], rot[2])

class LsImporterSettings:
    def __init__(self,
                context,
                filePath,
                fileName,
                fileDirectory,
                loadLinkedMode,
                location = [0.0, 0.0, 0.0], # in Blender coords
                rotation = [0.0, 0.0, 0.0], # in Blender coords
                parent = None,
                parent_is_ls3 = True,
                ):
        self.context = context
        self.filePath = filePath
        self.fileName = fileName
        self.fileDirectory = fileDirectory
        self.loadLinkedMode = loadLinkedMode
        self.location = location
        self.rotation = rotation
        self.parent = parent
        self.parent_is_ls3 = parent_is_ls3

class LsImporter:
    def __init__(self, config):
        self.config = config

        # Currently edited object
        self.currentobject = None

        # Currently edited mesh
        self.currentmesh = None

        # Path to Zusi data dir
        self.datapath = zusicommon.get_zusi2_data_path()

    def resolveFilePath(self, filePath):
        """Tries to locate a file by its path, interpreting the path as relative to the Zusi base path"""

        # Normalize path separator
        for ch in ['\\',  '/']:
            filePath = filePath.replace(ch, os.sep)

        return os.path.realpath(self.datapath) + os.sep + filePath

    def readElement(self, fp):
        """Reads one element from the file and adds it to the current mesh."""
        elementType = int(fp.readline())

        if elementType == 0:
            # Light source
            skipLine(fp, 10)
        else:
            numVertices = elementType

            if numVertices >= 3:
                skipLine(fp)
            
                verts = [self.currentbmesh.verts.new(read3floats(fp)) for i in range(0, numVertices)]
                face = self.currentbmesh.faces.new(verts)

                diffuse_color = int(fp.readline())
                night_color = int(fp.readline())
                blink_duration = float(fp.readline().replace(",", "."))
                skipLine(fp)
                mesh_type = int(fp.readline())
                skipLine(fp, 2)

                face.material_index = self.get_material(diffuse_color, night_color)
            else:
                print("Warning: Number of vertices is %d" % elementType)
                skipLine(fp, 1 + 3 * numVertices + 7)

    def get_material(self, diffuse_color, night_color):
        """Gets a material with the given diffuse and night color, creating one if it does not exist yet, and adds it to the current mesh's materials"""

        diffuse_color_rgb = color_to_rgba(diffuse_color)
        matname = "R" + str(int(diffuse_color_rgb[0] * 255)) + " G" + str(int(diffuse_color_rgb[1] * 255)) + " B" + str(int(diffuse_color_rgb[2] * 255)) + " (" + str(diffuse_color) + ")"

        matindex = bpy.data.materials.find(matname)
        if matindex == -1:
            mat = bpy.data.materials.new(matname)
            mat.diffuse_color = diffuse_color_rgb
            mat.diffuse_intensity = 1
            
            mat.zusi_use_emit = True
            mat.zusi_emit_color = color_to_rgba(night_color)

        matindex = self.currentmesh.materials.find(matname)
        if matindex == -1:
            self.currentmesh.materials.append(bpy.data.materials.get(matname))
            matindex = self.currentmesh.materials.find(matname)
        
        return matindex

    def import_ls(self):
        (shortName, ext) = os.path.splitext(self.config.fileName)
        print("Opening LS file " + self.config.filePath)

        with open(self.config.filePath, "r") as fp:
            print("File read successfully")

            # Skip header
            skipLine(fp)
            numElements = int(fp.readline())

            # Create new mesh
            self.currentmesh = bpy.data.meshes.new(self.config.fileName)

            # Create new object
            self.currentobject = bpy.data.objects.new(self.config.fileName, self.currentmesh)
            self.currentobject.parent = self.config.parent
            self.currentobject.location = self.config.location
            self.currentobject.rotation_euler = self.config.rotation
            if self.config.parent_is_ls3:
                # Coordinate system conversion
                self.currentobject.rotation_euler.z -= radians(90)
            bpy.context.scene.objects.link(self.currentobject)

            # Linked files
            line = fp.readline()
            while line != "#\n":
                path = self.resolveFilePath(line.strip())
                (directory, filename) = os.path.split(path)

                loc = read3floats(fp)
                rot = read3floats(fp)
                
                if self.config.loadLinkedMode == IMPORT_LINKED_EMBED:
                    if os.path.exists(path):
                        settings = LsImporterSettings(
                            self.config.context,
                            path,
                            filename,
                            directory,
                            self.config.loadLinkedMode,
                            loc,
                            zusi_rot_to_blender(rot),
                            self.currentobject,
                            parent_is_ls3 = False
                        )

                        importer = LsImporter(settings)
                        importer.import_ls()
                    else:
                        print("Warning: Linked file %s not found" % path)
                elif self.config.loadLinkedMode == IMPORT_LINKED_AS_EMPTYS:
                    empty = bpy.data.objects.new("{}_{}".format(self.config.fileName, filename), None)
                    empty.location = loc
                    empty.rotation_euler = zusi_rot_to_blender(rot)
                    empty.parent = self.currentobject

                    empty.zusi_is_linked_file = True
                    empty.zusi_link_file_name_realpath = path

                    self.config.context.scene.objects.link(empty)

                line = fp.readline()

            self.currentbmesh = bmesh.new()
            self.currentbmesh.from_mesh(self.currentmesh)

            for i in range(0, numElements):
                self.readElement(fp)

            self.currentbmesh.to_mesh(self.currentmesh)

            print("Done")
