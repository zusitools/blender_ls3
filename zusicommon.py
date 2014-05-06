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

from math import sqrt, acos
import os

# Forces a value into a range
forcerange = lambda x, minval, maxval : min(max(x, minval), maxval)

# Calculates the angle between two 3-dimensional vertices
# angle = arccos(u X v / (|u| * |v|))
# where X denotes the scalar product
def vertexangle(v1, v2):
    denominator = vertexlength(v1) * vertexlength(v2)
    if denominator == 0.0:
        return 0
    else:
        return acos(forcerange((v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / denominator, -1.0, 1.0))

# Computes the length (Euclidean norm) of the vertex v
vertexlength = lambda v : sqrt(sum([a**2 for a in v]))

# Calculates the distance between two vertices
vertexdist = lambda v1, v2 : vertexlength([v2[i] - v1[i] for i in range(0, min([len(v1), len(v2)]))])

# Returns a vector that points in the same direction as v and has length 1
def normalize_vector(v):
    v_len = vertexlength(v)
    if v_len != 0:
        return [a / v_len for a in v]
    else:
        return v

# Converts "True"/"False" into the equivalent boolean value
str2bool = lambda s : {"True" : True, "False" : False}[s]

# Determines whether the given object is visible according to its variant settings
# and the list of variants to export
def is_object_visible(object, variantIDs):
    if len(variantIDs) == 0 or object.zusi_variants_visibility_mode == "None":
        return True

    # The value to return when a visibility setting is found
    visibility = str2bool(object.zusi_variants_visibility_mode)
    visibility_settings = [vis.variant_id for vis in object.zusi_variants_visibility]
    intersect = set(variantIDs).intersection(visibility_settings)

    return (len(intersect) == 0) != visibility

# Determines whether two vertices can be merged by looking at the corresponding vertexdata entries
def can_merge_vertices(vertex1, vertex2, maxCoordDelta, maxUVDelta, maxNormalAngle):
    return (not (vertex1[11] or vertex2[11]) # no-merge flag
        and vertexdist(vertex1[6:8], vertex2[6:8]) <= maxUVDelta
        and vertexdist(vertex1[8:10], vertex2[8:10]) <= maxUVDelta
        and vertexdist(vertex1[0:3], vertex2[0:3]) <= maxCoordDelta
        and vertexangle(vertex1[3:6], vertex2[3:6]) <= maxNormalAngle)

# Merges the two vertices at their center (location, normal, and UV coordinates), keeping the vertex index of the first vertex
def merge_vertices(v1, v2):
    # Compute the angle bisector of the two normal vertices:
    # n = n1 / |n1| + n2 / |n2|
    n1 = normalize_vector([v1[3], v1[4], v1[5]])
    n2 = normalize_vector([v2[3], v2[4], v2[5]])
    n = normalize_vector([n1[0] + n2[0], n1[1] + n2[1], n1[2] + n2[2]])

    return ((v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2, (v1[2] + v2[2]) / 2,
        n[0], n[1], n[2],
        (v1[6] + v2[6]) / 2, (v1[7] + v2[7]) / 2,
        (v1[8] + v2[8]) / 2, (v1[9] + v2[9]) / 2,
        v1[10])

# Merges vertices which are close to each other.
# Returns a dictionary that contains the association of old to new vertex indices
def optimize_mesh(vertexdata, maxCoordDelta, maxUVDelta, maxNormalAngle):
    # Order vertices by x coordinate
    vertexdata.sort(key = lambda vdata : vdata[0])

    # Stores the new index of vertices that have been merged with another vertex
    merged = { }

    # Look at all pairs of vertices whose x coordinates
    # differ by no more than the permitted vertex distance
    for vertex1_index, vertex1 in enumerate(vertexdata):
        vertex2_index = vertex1_index + 1
        while vertex2_index < len(vertexdata) and vertexdata[vertex2_index][0] - vertex1[0] <= maxCoordDelta:
            vertex2 = vertexdata[vertex2_index]

            if can_merge_vertices(vertex1, vertex2, maxCoordDelta, maxUVDelta, maxNormalAngle):
                vertexdata[vertex1_index] = merge_vertices(vertex1, vertex2)
                vertexdata.remove(vertex2)
                merged[vertex2[10]] = vertex1_index
            else:
                # If we merged two vertices, the vertex index does not have to be incremented since we just deleted one vertex
                vertex2_index += 1

    # Build a dictionary with old -> new vertex indices
    # Add information about merged vertices
    new_vidx = dict((vertex[10], idx) for idx, vertex in enumerate(vertexdata))
    new_vidx.update(merged)

    # Return updated face list with new vertex indices
    return new_vidx

# Retrieve the path name of the Zusi data directory
def get_zusi_data_path():
    # Base path for path names relative to the Zusi data directory.
    # Change default value to your liking. It has to contain a trailing (back)slash
    try:
        from . import zusiconfig
        basepath = zusiconfig.datapath
    except ImportError:
        basepath = ""

    # Read basepath from registry. Do not look at this code, it's ugly!
    try:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\\Zusi3")
        except WindowsError:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\\Wow6432Node\\Zusi3")

        # We have to enumerate all key-value pairs in the open key
        try:
            index = 0
            while True:
                # The loop will be ended by a WindowsError being thrown when there
                # are no more key-value pairs
                value = winreg.EnumValue(key, index)
                if value[0] in ["DatenDirDemo", "DatenDir"]:
                    basepath = value[1]
                    break
                index += 1
        except WindowsError:
            pass

    except ImportError:
        # we're not on Windows
        pass
    except WindowsError:
        pass

    return basepath

# Retrieve the default author information from the registry (Windows) or the config file (Linux)
def get_default_author_info():
    default_author = { 'name' : "", 'id' : 0, 'email' : "" }
    
    try:
        from . import zusiconfig
        if zusiconfig.default_author:
            default_author = zusiconfig.default_author
    except ImportError:
        pass

    # Read author information from registry.
    try:
        import winreg
        # Try all possible key names until we manage to open a key
        for keyname in ["Software\\Zusi3\\Einstellungen", "Software\\Wow6432Node\\Zusi3\\Einstellungen",
                "Software\\Zusi3\\EinstellungenDemo", "Software\\Wow6432Node\\Zusi3\\EinstellungenDemo"]:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, keyname)
                break
            except WindowsError:
                pass

        # We have to enumerate all key-value pairs in the open key
        try:
            index = 0
            while True:
                # The loop will be ended by a WindowsError being thrown when there
                # are no more key-value pairs
                value = winreg.EnumValue(key, index)
                if value[0] == "AutorName":
                    default_author['name'] = value[1]
                if value[0] == "AutorID":
                    default_author['id'] = int(value[1])
                if value[0] == "AutorEMail":
                    default_author['email'] = value[1]
                index += 1
        except WindowsError:
            pass

    except ImportError:
        # we're not on Windows
        pass
    except WindowsError:
        pass

    return default_author

# Tries to locate a file by its path:
# 1) interpreting the path as an absolute path
# 2) interpreting the path as relative to the LS3 file's path
# 3) interpreting the path as relative to the Zusi base path
def resolve_file_path(file_path, current_dir, datapath):
    # Normalize path separator
    for ch in ['\\',  '/']:
        file_path = file_path.replace(ch, os.sep)

    if os.path.exists(file_path):
        return file_path

    relpath_ls3 = os.path.realpath(current_dir) + os.sep + file_path
    if os.path.exists(relpath_ls3):
        return relpath_ls3

    relpath_base = os.path.realpath(datapath) + os.sep + file_path
    return relpath_base
