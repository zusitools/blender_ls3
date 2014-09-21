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
import array
import os

# Forces a value into a range
forcerange = lambda x, minval, maxval : min(max(x, minval), maxval)

# Calculates the angle between two 3-dimensional vertices
# angle = arccos(u X v / (|u| * |v|))
# where X denotes the scalar product
def vertexangle_3(v1, v2):
    denominator = vertexlength_3(v1[0], v1[1], v1[2]) * vertexlength_3(v2[0], v2[1], v2[2])
    if denominator == 0.0:
        return 0
    else:
        return acos(forcerange((v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / denominator, -1.0, 1.0))

# Computes the square of the length (Euclidean norm) of the vertex v
def vertexlength_squared_3(x, y, z):
    return x*x + y*y + z*z
def vertexlength_squared_2(x, y):
    return x*x + y*y

# Computes the length (Euclidean norm) of the vertex v
def vertexlength_3(x, y, z):
    return sqrt(vertexlength_squared_3(x, y, z))

# Calculates the square of the distance between two vertices
def vertexdist_squared_3(v1, v2):
    return vertexlength_squared_3(v2[0]-v1[0], v2[1]-v1[1], v2[2]-v1[2])
def vertexdist_squared_2(v1, v2):
    return vertexlength_squared_2(v2[0]-v1[0], v2[1]-v1[1])

# Returns a vector that points in the same direction as (x,y,z) and has length 1
def normalize_vector_3(x, y, z):
    v_len = vertexlength_3(x, y, z)
    if v_len != 0:
        return (x / v_len, y / v_len, z / v_len)
    else:
        return (x, y, z)

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

# Merges the two vertices at their center (location, normal, and UV coordinates), keeping the vertex index of the first vertex
def merge_vertices(v1, v2):
    # If the two normal vectors are (almost) equal, take one of the vectors instead of
    # computing the angle bisector.
    if (abs(v2[3] - v1[3]) < 0.00001 and abs(v2[4] - v1[4]) < 0.00001 and abs(v2[5] - v1[5]) < 0.00001):
        n = (v1[3], v1[4], v1[5])
    else:
        # Compute the angle bisector of the two normal vertices:
        # n = n1 / |n1| + n2 / |n2|
        n1 = normalize_vector_3(v1[3], v1[4], v1[5])
        n2 = normalize_vector_3(v2[3], v2[4], v2[5])
        n = normalize_vector_3(n1[0] + n2[0], n1[1] + n2[1], n1[2] + n2[2])

    return ((v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2, (v1[2] + v2[2]) / 2,
        n[0], n[1], n[2],
        (v1[6] + v2[6]) / 2, (v1[7] + v2[7]) / 2,
        (v1[8] + v2[8]) / 2, (v1[9] + v2[9]) / 2,
        v1[10])

# Merges vertices which are close to each other.
# Modifies the supplied list vertexdata. The length of the list will stay the same,
# but some entries may be set to None. (This is to save the overhead of removing
# items from the list.)
# Returns an array that contains the association of old to new vertex indices,
# where the vertex indices are counted from 0 and excluding deleted vertices
# (whose entry in the vertexdata array is None).
def optimize_mesh(vertexdata, maxCoordDelta, maxUVDelta, maxNormalAngle):
    maxCoordDeltaSquared = maxCoordDelta ** 2
    maxUVDeltaSquared = maxUVDelta ** 2

    # Order vertices by x coordinate
    vertexdata.sort(key = lambda vdata : vdata[0])

    # Stores the new index of vertices that have been merged with another vertex
    merged = { }

    vertex_count = len(vertexdata)

    # Look at all pairs of vertices whose x coordinates
    # differ by no more than the permitted vertex distance
    for vertex1_index, vertex1 in enumerate(vertexdata):
        if vertex1 is None:
            continue
        vertex2_index = vertex1_index + 1
        for vertex2_index in range(vertex1_index + 1, vertex_count):
            vertex2 = vertexdata[vertex2_index]
            if vertex2 is None:
                continue
            if vertex2[0] - vertex1[0] > maxCoordDelta:
                break

            # Check if the two vertices can be merged
            if (not (vertex1[11] or vertex2[11]) # no-merge flag
                    # Early-abort checks without having to compute actual vertex distances
                    # Explicitly write out two checks instead of using the abs() function
                    # for performance reasons.
                    and vertex2[1] - vertex1[1] < maxCoordDelta and vertex1[1] - vertex2[1] < maxCoordDelta
                    and vertex2[2] - vertex1[2] < maxCoordDelta and vertex1[2] - vertex2[2] < maxCoordDelta
                    and vertex2[6] - vertex1[6] < maxUVDelta and vertex1[6] - vertex2[6] < maxUVDelta
                    and vertex2[7] - vertex1[7] < maxUVDelta and vertex1[7] - vertex2[7] < maxUVDelta
                    # The actual tests
                    and vertexdist_squared_2(vertex1[6:8], vertex2[6:8]) <= maxUVDeltaSquared
                    and vertexdist_squared_3(vertex1[0:3], vertex2[0:3]) <= maxCoordDeltaSquared
                    and vertexangle_3(vertex1[3:6], vertex2[3:6]) <= maxNormalAngle
                    and vertexdist_squared_2(vertex1[8:10], vertex2[8:10]) <= maxUVDeltaSquared):
                vertexdata[vertex1_index] = merge_vertices(vertex1, vertex2)
                vertexdata[vertex2_index] = None
                merged[vertex2[10]] = vertex1[10]

    # Build a dictionary with old -> new vertex indices. The old vertex index is saved in vertex[10].
    num_deleted_vertices = 0
    new_vidx = array.array('i', (0,) * vertex_count)
    for idx, vertex in enumerate(vertexdata):
        if vertex is None:
            num_deleted_vertices += 1
        else:
            new_vidx[vertex[10]] = idx - num_deleted_vertices

    # Add information about merged vertices
    for old_index, new_index in merged.items():
        new_vidx[old_index] = new_vidx[new_index]

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
