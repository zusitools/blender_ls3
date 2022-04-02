# coding=utf-8

import bpy
import os
import shutil
import sys
import tempfile
import unittest
import mathutils
import xml.etree.ElementTree as ET
from unittest.mock import patch
from math import radians
from copy import copy

sys.path.append(os.getcwd())
from mocks import MockFS

ZUSI3_DATAPATH = r"Z:\Zusi3\Daten" if sys.platform.startswith("win") else "/mnt/zusi3/daten"
ZUSI3_DATAPATH_OFFICIAL = r"Z:\Zusi3\DatenOffiziell" if sys.platform.startswith("win") else "/mnt/Zusi3/DatenOffiziell"
ZUSI2_DATAPATH = r"Z:\Zusi2\Daten" if sys.platform.startswith("win") else "/mnt/zusi2/daten"
ZUSI3_EXPORTPATH = r"Z:\Zusi3\Daten\ExportTest" if sys.platform.startswith("win") else "/mnt/zusi3/daten/ExportTest"
NON_ZUSI_PATH = r"Z:\NichtZusi" if sys.platform.startswith("win") else "/mnt/nichtzusi"

# Windows Registry mocks
try:
  # Python needs winreg.OpenKey for import mechanisms, so we must
  # exercise care to only mock the invocations we are interested in.
  import winreg
  realOpenKey = winreg.OpenKey
  realEnumValue = winreg.EnumValue
except ImportError:
  pass # not on Windows

class MockZusi3RegistryKey:
  pass

class MockZusi2RegistryKey:
  pass

def mockOpenKeyImpl(root, keyname):
  if root == winreg.HKEY_LOCAL_MACHINE and keyname == "Software\\Zusi3":
    return MockZusi3RegistryKey()
  elif root == winreg.HKEY_CURRENT_USER and keyname == "Software\\Zusi":
    return MockZusi2RegistryKey()
  else:
    return realOpenKey(root, keyname)

def mockEnumValueImpl(key, index):
  if isinstance(key, MockZusi3RegistryKey):
    if index == 0:
      return ('DatenDir', ZUSI3_DATAPATH)
    else:
      raise WindowsError()
  elif isinstance(key, MockZusi2RegistryKey):
    if index == 0:
      return ('ZusiDir', ZUSI2_DATAPATH)
    else:
      raise WindowsError()
  else:
    return realEnumValue(key, index)

class TestLs3Export(unittest.TestCase):
  def setUp(self):
    # Check that we are testing the right file
    io_scene_ls3_module_file = sys.modules["io_scene_ls3"].__file__
    expected_module_file = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), os.pardir, '__init__.py')
    assert os.path.samefile(io_scene_ls3_module_file, expected_module_file), \
        "Expected to test {}, but got {}".format(expected_module_file, io_scene_ls3_module_file)

    bpy.ops.wm.read_homefile()
    self._mock_fs = MockFS()
    self._mock_fs.start()

    self._openkey_patch = patch('winreg.OpenKey', side_effect=mockOpenKeyImpl)
    self._enumvalue_patch = patch('winreg.EnumValue', side_effect=mockEnumValueImpl)
    if sys.platform.startswith("win"):
      self._openkey_patch.start()
      self._enumvalue_patch.start()

    # TODO This requires that you have a zusiconfig.py file set up
    sys.modules["io_scene_ls3.zusiconfig"].datapath = ZUSI3_DATAPATH
    sys.modules["io_scene_ls3.zusiconfig"].datapath_official = ZUSI3_DATAPATH_OFFICIAL
    sys.modules["io_scene_ls3.zusiconfig"].z2datapath = ZUSI2_DATAPATH
    sys.modules["io_scene_ls3.zusiconfig"].default_export_settings = {
        "exportAnimations" : False,
        "optimizeMesh" : False,
        "exportSelected" : '0',
        "writeLsb" : False,
    }

  def tearDown(self):
    self._mock_fs.stop()

    if sys.platform.startswith("win"):
      self._openkey_patch.stop()
      self._enumvalue_patch.stop()

  def open(self, filename):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(os.getcwd(), "blends", filename + ".blend"))

  def clear_scene(self):
    for ob in bpy.context.scene.objects:
      bpy.data.objects.remove(ob)
    bpy.context.view_layer.update()

  def export(self, exportargs={}, noclose=False):
    context = bpy.context.copy()
    if 'selected_objects' in exportargs:
        context['selected_objects'] = [ob for ob in bpy.data.objects if ob.name in exportargs["selected_objects"]]
        del exportargs["selected_objects"]
    else:
        context['selected_objects'] = []

    if "ext" in exportargs:
      filename = "export" + exportargs["ext"]
      del exportargs["ext"]
    else:
      filename = "export.ls3"

    variants = []
    if "variants" in exportargs:
      for variant_id in exportargs["variants"]:
        variants.append({"variant_id": variant_id, "export": True,
            "name":"foobar", "template_list_controls": "foobar"})
      del exportargs["variants"]

    exportpath = os.path.join(ZUSI3_EXPORTPATH, filename)

    args = copy(sys.modules["io_scene_ls3.zusiconfig"].default_export_settings)
    args.update(exportargs)

    bpy.ops.export_scene.ls3(context,
      filepath=exportpath, filename=filename, directory=ZUSI3_EXPORTPATH, variant_export_setting=variants,
      **args)

    return exportpath

  def export_and_parse(self, exportargs={}):
    exported_file_name = self.export(exportargs)
    #with open(exported_file_name, 'rb') as f:
    #  print(f.read().decode('utf-8'))
    tree = ET.parse(exported_file_name)
    return tree.getroot()

  def export_and_parse_multiple(self, additional_suffixes, exportargs={}):
    if "exportAnimations" not in exportargs:
      exportargs["exportAnimations"] = True
    mainfile_name = self.export(exportargs)

    (path, name) = os.path.split(mainfile_name)
    (basename, ext) = os.path.splitext(name)

    mainfile_tree = ET.parse(mainfile_name)
    mainfile_root = mainfile_tree.getroot()

    result = {"" : mainfile_root}

    for suffix in additional_suffixes:
      (path, name) = os.path.split(mainfile_name)
      split_file_name = name.split(os.extsep, 1)
      if len(split_file_name) > 1:
        basename, ext = split_file_name[0], os.extsep + split_file_name[1]
      else:
        basename, ext = split_file_name[0], ""

      additional_filename = os.path.join(path, basename + "_" + suffix + ext)
      additional_tree = ET.parse(additional_filename)
      additional_root = additional_tree.getroot()
      result[suffix] = additional_root

    return basename, ext, result

  def assertXYZW(self, node, expected_x, expected_y, expected_z, expected_w):
    self.assertXYZ(node, expected_x, expected_y, expected_z)
    if expected_w != 0.0 or "W" in node.attrib:
      self.assertAlmostEqual(expected_w, float(node.attrib["W"]), places = 5)

  def assertXYZ(self, node, expected_x, expected_y, expected_z, msg = None, places = 5):
    if expected_x != 0.0 or "X" in node.attrib:
      self.assertAlmostEqual(expected_x, float(node.attrib["X"]), places = places, msg = msg)
    if expected_y != 0.0 or "Y" in node.attrib:
      self.assertAlmostEqual(expected_y, float(node.attrib["Y"]), places = places, msg = msg)
    if expected_z != 0.0 or "Z" in node.attrib:
      self.assertAlmostEqual(expected_z, float(node.attrib["Z"]), places = places, msg = msg)

  def assertVertexCoordsEqual(self, expected_coords, vertices):
    self.assertEqual(len(expected_coords), len(vertices))

    p_nodes = [v.find("p") for v in vertices]
    coords = [
        (round(float(p.attrib["X"]), 5), round(float(p.attrib["Y"]), 5), round(float(p.attrib["Z"]), 5))
        for p in p_nodes]
    self.assertEqual(set(expected_coords), set(coords))

  def assertKeyframes(self, node, keyframe_times):
    keyframes = node.findall("AniPunkt")
    self.assertEqual(len(keyframe_times), len(keyframes))
    for idx, keyframe_time in enumerate(keyframe_times):
      self.assertAlmostEqual(keyframe_time, float(keyframes[idx].attrib["AniZeit"]))

  def assertAniNrs(self, animation_node, ani_nrs):
    aninrs_nodes = animation_node.findall("./AniNrs")
    self.assertEqual(set(ani_nrs), set([int(node.attrib["AniNr"]) for node in aninrs_nodes]))

  # ---
  # TESTS START HERE
  # ---

  # ---
  # File structure tests
  # ---

  def test_export_empty(self):
    self.clear_scene()
    root = self.export_and_parse()

    # <Zusi> node (root)
    self.assertEqual("Zusi", root.tag)
    self.assertEqual({}, root.attrib)
    self.assertEqual(2, len(root))

    # <Info> node
    self.assertEqual("Info", root[0].tag)
    self.assertEqual(3, len(root[0].attrib))
    self.assertEqual("Landschaft", root[0].attrib["DateiTyp"])
    self.assertEqual("A.1", root[0].attrib["MinVersion"])
    self.assertEqual("A.1", root[0].attrib["Version"])
    self.assertEqual(0, len(root[0]))

    # <Landschaft> node
    self.assertEqual("Landschaft", root[1].tag)
    self.assertEqual({}, root[1].attrib)
    self.assertEqual(0, len(root[1]))

  def test_xml_declaration_and_bom(self):
    mainfile_name = self.export()
    utf8bom = b'\xef\xbb\xbf'
    self.assertEqual(utf8bom, open(mainfile_name, 'rb').read()[:len(utf8bom)])
    xmldecl = b'<?xml version="1.0" encoding="UTF-8"?>'
    self.assertEqual(xmldecl, open(mainfile_name, 'rb').read()[len(utf8bom):len(utf8bom)+len(xmldecl)])

  def test_line_endings(self):
    self.clear_scene()
    xmldecl = b'<?xml version="1.0" encoding="UTF-8"?>'

    oldlinesep = os.linesep
    try:
      os.linesep = '\n'
      mainfile_name = self.export()
      contents = open(mainfile_name, 'rb').read()
      self.assertNotIn(b'\r', contents)
      lines = contents.decode().split('\n')
      self.assertEqual(6, len(lines))

      os.linesep = '\r\n'
      mainfile_name = self.export()
      contents = open(mainfile_name, 'rb').read()
      lines = contents.decode().split('\r\n')
      self.assertEqual(6, len(lines))
    finally:
      os.linesep = oldlinesep

  def test_indentation(self):
    self.open("cube")
    content = open(self.export(), 'rb').read().decode('utf-8')
    indent = os.linesep + 6 * " "

    idx = content.find("<Vertex")
    while idx != -1:
      self.assertGreaterEqual(idx, len(indent))
      self.assertEqual(content[idx - len(indent):idx + len("<Vertex")], indent + "<Vertex")
      idx = content.find("<Vertex", idx + 1)

    idx = content.find("<Face")
    while idx != -1:
      self.assertGreaterEqual(idx, len(indent))
      self.assertEqual(content[idx - len(indent):idx + len("<Face")], indent + "<Face")
      idx = content.find("<Face", idx + 1)

  def test_author_info_licenses(self):
    self.open("author_info_licenses")
    root = self.export_and_parse()

    licenses = set([(a.attrib["AutorName"], a.attrib["AutorLizenz"] if "AutorLizenz" in a.attrib else "0")
        for a in root.findall("./Info/AutorEintrag")])
    self.assertEqual(set([("Author 1", "0"), ("Author 2", "5")]), licenses)

  def test_author_info_expense_xml(self):
    self.open("author_info_expense_xml")
    root = self.export_and_parse()

    for a in root.findall("./Info/AutorEintrag"):
        self.assertNotIn("AutorAufwand", a.attrib)

    expensepath = os.path.join(ZUSI3_EXPORTPATH, "export.ls3.expense.xml")
    self.assertTrue(os.path.exists(expensepath))

    expenseroot = ET.parse(expensepath).getroot()
    eintraege = expenseroot.findall("./Info/AutorEintrag")
    self.assertEqual(3, len(eintraege))

    self.assertEqual("Author 1", eintraege[0].attrib["AutorName"])
    self.assertEqual(42, int(eintraege[0].attrib["AutorID"]))
    self.assertEqual("Test 1", eintraege[0].attrib["AutorBeschreibung"])
    self.assertNotIn("AutorAufwand", eintraege[0].attrib)

    self.assertEqual("Author 2", eintraege[1].attrib["AutorName"])
    self.assertNotIn("AutorID", eintraege[1].attrib)
    self.assertEqual("Test 2", eintraege[1].attrib["AutorBeschreibung"])
    self.assertEqual(3, float(eintraege[1].attrib["AutorAufwand"]))

    self.assertEqual("Author 3", eintraege[2].attrib["AutorName"])
    self.assertEqual(9000, int(eintraege[2].attrib["AutorID"]))
    self.assertEqual("Test 3", eintraege[2].attrib["AutorBeschreibung"])
    self.assertEqual(6, float(eintraege[2].attrib["AutorAufwand"]))

    node = expenseroot.find("./expense")
    self.assertIsNotNone(node)
    self.assertEqual(0, len(node.attrib))
    self.assertEqual(0, len(node))

    # Test that .expense.xml is deleted if no expense information is available.
    for i in range(3):
        bpy.context.scene.zusi_authors[i].effort = 0
    self.export_and_parse()
    self.assertFalse(os.path.exists(expensepath))

  def test_lsb_node_pos(self):
    root = self.export_and_parse({ "writeLsb": True })

    landschaft_node = root.find("./Landschaft")
    lsb_node = root.find("./Landschaft/lsb")
    subset_node = root.find("./Landschaft/SubSet")

    children = list(landschaft_node)
    self.assertEqual(children.index(subset_node) - 1, children.index(lsb_node))

  def test_no_lsb_on_empty(self):
    self.clear_scene()
    root = self.export_and_parse({ "writeLsb": True })

    self.assertFalse(os.path.exists(os.path.join(ZUSI3_EXPORTPATH, "export.lsb")))
    self.assertEqual([], root.findall("./Landschaft/lsb"))

  # ---
  # Mesh and texture export tests
  # ---

  def test_export_simple_cube(self):
    self.open("simple_cube")
    root = self.export_and_parse()

    # <Landschaft> node contains one subset
    landschaft_node = root.find("./Landschaft")
    self.assertEqual(1, len(landschaft_node))
    self.assertEqual("SubSet", landschaft_node[0].tag)

    vertex_nodes = [n for n in landschaft_node[0] if n.tag == "Vertex"]
    face_nodes = [n for n in landschaft_node[0] if n.tag == "Face"]

    self.assertEqual(36, len(vertex_nodes))
    self.assertEqual(12, len(face_nodes))

    for vertex_node in vertex_nodes:
      self.assertAlmostEqual(0, float(vertex_node.attrib["U"]), 5)
      self.assertAlmostEqual(0, float(vertex_node.attrib["V"]), 5)
      self.assertAlmostEqual(0, float(vertex_node.attrib["U2"]), 5)
      self.assertAlmostEqual(0, float(vertex_node.attrib["V2"]), 5)

  def test_export_edit_mode(self):
    self.open("edit_mode")
    bpy.ops.object.editmode_toggle()
    bpy.ops.transform.translate(value=(1, 0, 0))
    root = self.export_and_parse()

    p_nodes = root.findall("./Landschaft/SubSet/Vertex/p")
    self.assertEqual(36, len(p_nodes))
    for v in p_nodes:
        self.assertAlmostEqual(1, abs(float(v.attrib["X"])), places=5)
        self.assertAlmostEqual(1, abs(float(v.attrib["Y"])), places=5)
        self.assertAlmostEqual(1, abs(float(v.attrib["Z"])), places=5)

  @unittest.skip("very slow")
  def test_too_many_vertices(self):
    self.open("toomanyvertices")
    with self.assertRaises(RuntimeError) as ctx:
        self.export_and_parse()
    self.assertTrue("OverflowError" in ctx.exception.args[0])

    with self.assertRaises(RuntimeError) as ctx:
        self.export_and_parse({
          "optimizeMesh" : True,
          "maxCoordDelta" : 0.1,
          "maxUVDelta" : 1.0,
          "maxNormalAngle" : 1,
        })
    self.assertTrue("OverflowError" in ctx.exception.args[0])

  def test_scaled_object(self):
    self.open("scale")
    root = self.export_and_parse()
    vertex_pos_nodes = root.findall("./Landschaft/SubSet/Vertex/p")
    self.assertEqual(36, len(vertex_pos_nodes))
    for v in vertex_pos_nodes:
        self.assertAlmostEqual(6, abs(float(v.attrib["X"])) + abs(float(v.attrib["Y"])) + abs(float(v.attrib["Z"])), places = 5)

  def test_split_normals(self):
    self.open("split_normals")
    root = self.export_and_parse()
    normals = root.findall("./Landschaft/SubSet/Vertex/n")

    # Normals point either in X or Z direction, although both faces are
    # set to smooth and no Edge Split modifier is set. Auto Smooth creates
    # the correct split normals
    for n in normals:
        if float(n.attrib["X"]) < 0.001:
            self.assertXYZ(n, 0, 0, 1)
        else:
            self.assertXYZ(n, 1, 0, 0)

  def test_custom_split_normals(self):
    self.open("custom_split_normals")
    root = self.export_and_parse()
    normals = root.findall("./Landschaft/SubSet/Vertex/n")
    self.assertNotEqual(0, len(normals))
    for n in normals:
      self.assertXYZ(n, 0, 1, 0, places = 4) # normals are less accurate

  def test_rail_normals(self):
    self.open("rail_normals")
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 0.1,
      "maxUVDelta" : 1.0,
      "maxNormalAngle" : 1,
    })
    subset_node = root.find("./Landschaft/SubSet")
    vertex_nodes = [n for n in subset_node if n.tag == "Vertex"]
    self.assertEqual(8, len(vertex_nodes)) # should have been optimized
    for n in vertex_nodes:
      n_node = n.find("./n")
      self.assertXYZ(n_node, 0, 0, 1)

  def test_normal_constraints(self):
    self.open("normal_constraints")
    root = self.export_and_parse()
    subsets = root.findall("./Landschaft/SubSet")
    xy = subsets[0]
    xz = subsets[1]
    yz = subsets[2]

    # The names of the axes refer to the Blender axes.
    # In Zusi, the X and Y axes are swapped.
    for idx, (subset, normal) in enumerate([(xy, (0, 1, 0)), (xz, (0, 0, -1)), (yz, (0, 0, 1))]):
      for n in subset.findall("./Vertex/n"):
        self.assertAlmostEqual(normal[0], float(n.attrib["X"]), 5, f"subset {idx}: expected {normal}, got {n.attrib}")
        self.assertAlmostEqual(normal[1], float(n.attrib["Y"]), 5, f"subset {idx}: expected {normal}, got {n.attrib}")
        self.assertAlmostEqual(normal[2], float(n.attrib["Z"]), 5, f"subset {idx}: expected {normal}, got {n.attrib}")

  def test_texture_export(self):
    self.open("texture_blender28")
    root = self.export_and_parse()

    subset_nodes = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subset_nodes))
    subset_node = subset_nodes[0]

    textur_nodes = subset_node.findall("./Textur")
    self.assertEqual(1, len(textur_nodes))

    datei_node = textur_nodes[0].find("./Datei")
    self.assertEqual("texture.dds", datei_node.attrib["Dateiname"][-len("texture.dds"):])

    # Check for correct UV coordinates.
    vertex_nodes = [n for n in subset_node if n.tag == "Vertex"]
    self.assertEqual(36, len(vertex_nodes))
    for vertex_node in vertex_nodes:
      self.assertIn(round(float(vertex_node.attrib["U"]), 2), [.25, .75])
      self.assertIn(round(float(vertex_node.attrib["V"]), 2), [.25, .75])
      self.assertAlmostEqual(0, float(vertex_node.attrib["U2"]), 5)
      self.assertAlmostEqual(0, float(vertex_node.attrib["V2"]), 5)

  def test_multitexturing(self):
    self.open("multitexturing")
    root = self.export_and_parse()

    subset_nodes = root.findall("./Landschaft/SubSet")
    self.assertEqual(2, len(subset_nodes))
    subset_node_1 = subset_nodes[0]

    # Check that two textures are given.
    textur_nodes = subset_node_1.findall("./Textur")
    self.assertEqual(2, len(textur_nodes))

    # First texture must be the intransparent one, second texture the transparent one.
    datei1_node = textur_nodes[0].find("./Datei")
    self.assertEqual("texture.dds", datei1_node.attrib["Dateiname"][-len("texture.dds"):])

    datei2_node = textur_nodes[1].find("./Datei")
    self.assertEqual("texture_alpha.dds", datei2_node.attrib["Dateiname"][-len("texture_alpha.dds"):])

    # Check for correct UV coordinates.
    vertex_nodes = [n for n in subset_node_1 if n.tag == "Vertex"]
    face_nodes = [n for n in subset_node_1 if n.tag == "Face"]

    self.assertEqual(36, len(vertex_nodes))
    self.assertEqual(12, len(face_nodes))

    for vertex_node in vertex_nodes:
      u1 = float(vertex_node.attrib["U"])
      u2 = float(vertex_node.attrib["U2"])
      v1 = float(vertex_node.attrib["V"])
      v2 = float(vertex_node.attrib["V2"])

      self.assertIn(round(u1, 1), [0, 1])
      self.assertIn(round(v1, 1), [0, 1])
      self.assertIn(round(u2, 2), [.25, .75])
      self.assertIn(round(v2, 2), [.25, .75])

  def test_multitexturing_same_texture(self):
    """Tests that UV coordinates are exported correctly when the same texture is used multiple times with different UV maps"""
    self.open("multitexturing_sametexture")
    root = self.export_and_parse()

    vertex_nodes = root.findall("./Landschaft/SubSet/Vertex")
    self.assertEqual(36, len(vertex_nodes))

    for vertex_node in vertex_nodes:
      u1 = float(vertex_node.attrib["U"])
      u2 = float(vertex_node.attrib["U2"])
      v1 = float(vertex_node.attrib["V"])
      v2 = float(vertex_node.attrib["V2"])

      self.assertIn(round(u1, 1), [0, 1])
      self.assertIn(round(v1, 1), [0, 1])
      self.assertIn(round(u2, 2), [.25, .75])
      self.assertIn(round(v2, 2), [.25, .75])

  @unittest.skip("not implemented yet")
  def test_meters_per_texture(self):
    self.open("meters_per_texture")
    root = self.export_and_parse()

    subset = root.find("./Landschaft/SubSet")
    self.assertEqual(25.5, float(subset.attrib["MeterProTex"]))
    self.assertEqual(35, float(subset.attrib["MeterProTex2"]))

  def test_no_material(self):
    self.open("no_material")
    root = self.export_and_parse()
    subset = root.find("./Landschaft/SubSet")
    renderflags = subset.find("./RenderFlags")
    self.assertEqual("1", renderflags.attrib["TexVoreinstellung"])

  def test_material_linked_to_object(self):
    self.open("material_linked_to_object")
    root = self.export_and_parse()
    self.assertEqual(2, len(root.findall("./Landschaft/SubSet")))

  def test_night_color(self):
    self.open("nightcolor")
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(4, len(subsets))

    # Subset 1 has no night color, Cd (diffuse) is white.
    self.assertEqual("FFFFFFFF", subsets[0].attrib["Cd"])
    self.assertNotIn("Ce", subsets[0].attrib)

    # Subset 2 has a night color of black and a day color of white.
    # It will be black at night and white by day.
    self.assertEqual("FFFFFFFF", subsets[1].attrib["Cd"])
    self.assertNotIn("Ce", subsets[1].attrib)

    # Subset 3 has a night color of white and a day color of gray.
    # This does not work in Zusi's lighting model (night color must be darker),
    # so we adjust the night color accordingly (to be gray, too).
    self.assertEqual("FF000000", subsets[2].attrib["Cd"])
    self.assertEqual("00808080", subsets[2].attrib["Ce"])

    # Subset 4 allows overexposure and therefore has a (theoretical)
    # day color of RGB(510, 510, 510).
    self.assertEqual("FFFFFFFF", subsets[3].attrib["Cd"])
    self.assertEqual("00FFFFFF", subsets[3].attrib["Ce"])

  def test_night_switch_threshold(self):
    self.open("night_switch_threshold")
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(3, len(subsets))

    self.assertAlmostEqual(0.3, float(subsets[0].attrib["Nachtumschaltung"]), places = 5)
    self.assertNotIn("Nachtumschaltung", subsets[1].attrib)
    self.assertAlmostEqual(0.8, float(subsets[2].attrib["Nachtumschaltung"]), places = 5)

  def test_day_mode_preset(self):
    self.open("day_mode_preset")
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(3, len(subsets))

    self.assertEqual("7", subsets[0].attrib["NachtEinstellung"])
    self.assertNotIn("NachtEinstellung", subsets[1].attrib)
    self.assertNotIn("NachtEinstellung", subsets[2].attrib)

  def test_color_order(self):
    self.open("color_order")
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))

    # Test that the color order is ARGB, not 0ABGR (as in older Zusi versions)
    self.assertEqual("FF224466", subsets[0].attrib["Cd"])
    self.assertEqual("FF88AACC", subsets[0].attrib["Ca"])

  def test_ambient_color(self):
    self.open("ambientcolor")
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(4, len(subsets))

    # Subset 1 has a diffuse color of white and an ambient color of gray.
    self.assertEqual("FFFFFFFF", subsets[0].attrib["Cd"])
    self.assertEqual("FF808080", subsets[0].attrib["Ca"])
    self.assertNotIn("E", subsets[0].attrib)

    # Subset 2 has a diffuse color of white and an ambient/night color of gray.
    self.assertEqual("FF808080", subsets[1].attrib["Cd"])
    self.assertEqual("FF000000", subsets[1].attrib["Ca"])
    self.assertEqual("00808080", subsets[1].attrib["Ce"])

    # Subset 3 has a night color that is lighter than the ambient color.
    # It will be reduced to be darker than both diffuse and ambient color.
    self.assertEqual("FF808080", subsets[2].attrib["Cd"])
    self.assertEqual("FF000000", subsets[2].attrib["Ca"])
    self.assertEqual("00808080", subsets[2].attrib["Ce"])

    # Subset 4 has a night color of gray, an ambient color of white
    # and a gray ambient overexposure.
    self.assertEqual("FF808080", subsets[3].attrib["Cd"])
    self.assertEqual("FFFFFFFF", subsets[3].attrib["Ca"])
    self.assertEqual("00808080", subsets[3].attrib["Ce"])

  def test_zbias(self):
    self.open("zbias")
    mainfile = self.export_and_parse()
    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual('-2', subsets[0].attrib["zBias"])
    self.assertNotIn("zBias", subsets[1].attrib)
    self.assertEqual('1', subsets[2].attrib["zBias"])
    self.assertEqual('1', subsets[3].attrib["zBias"])

  def test_second_pass(self):
    self.open("second_drawing_pass")
    root = self.export_and_parse()
    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, int(subsets[0].attrib.get("DoppeltRendern", 0)))
    self.assertEqual(0, int(subsets[1].attrib.get("DoppeltRendern", 0)))
    self.assertEqual(0, int(subsets[2].attrib.get("DoppeltRendern", 0)))

  @unittest.skipUnless(sys.platform.startswith("win"), "only makes sense on Windows")
  def test_path_relative_to_zusi_dir(self):
        # Test that a path outside the Zusi data dir (but on the same drive)
        # is exported as a relative path instead of an absolute one.
        self.open('relpath_windows')
        mainfile = self.export_and_parse()
        textur_datei_nodes = mainfile.findall('./Landschaft/SubSet/Textur/Datei')
        self.assertEqual(1, len(textur_datei_nodes))
        self.assertEqual('..\\Objektbau\\textur.png', textur_datei_nodes[0].attrib['Dateiname'])

  def test_relative_path_properties(self):
        self.open('relpath_properties')
        files = bpy.data.objects['Empty'].zusi_anchor_point_files

        # Get properties
        self.assertEqual(r"zusi2:Loks\Dieselloks\203\203.fst", files[0].name)
        self.assertEqual(os.path.join(ZUSI2_DATAPATH, "Loks", "Dieselloks", "203", "203.fst"), files[0].name_realpath)

        self.assertEqual(r"zusi3:Routes\Deutschland\32U_0004_0057\000442_005692_Freienohl\Freienohl_1985.ls3",
            files[1].name)
        self.assertEqual(os.path.join(ZUSI3_DATAPATH_OFFICIAL, "Routes", "Deutschland", "32U_0004_0057", "000442_005692_Freienohl", "Freienohl_1985.ls3"),
            files[1].name_realpath)

        self.assertEqual("/tmp/foo.bar", files[2].name)
        self.assertEqual("/tmp/foo.bar", files[2].name_realpath)

        # Set properties
        files[0].name_realpath = os.path.join(ZUSI2_DATAPATH, "Loks", "Elektroloks", "101", "101.fzg")
        self.assertEqual(r"zusi2:Loks\Elektroloks\101\101.fzg", files[0].name)

        files[1].name_realpath = os.path.join(ZUSI3_DATAPATH, "Loks", "Elektroloks", "101", "101.fzg")
        self.assertEqual(r"zusi3:Loks\Elektroloks\101\101.fzg", files[1].name)

        files[2].name_realpath = os.path.join(ZUSI3_DATAPATH_OFFICIAL, "Loks", "Elektroloks", "102", "102.fzg")
        self.assertEqual(r"zusi3:Loks\Elektroloks\102\102.fzg", files[2].name)

        files[3].name_realpath = os.path.join(NON_ZUSI_PATH, "KeineDaten", "Irgendwas.fzg")
        self.assertEqual(files[3].name_realpath, files[3].name)

        # Export
        mainfile = self.export_and_parse()
        datei_nodes = mainfile.findall('./Landschaft/Ankerpunkt/Datei')
        self.assertEqual(4, len(datei_nodes))

        if sys.platform.startswith("win"):
          self.assertEqual(r"..\..\Zusi2\Daten\Loks\Elektroloks\101\101.fzg", datei_nodes[0].attrib["Dateiname"])
          self.assertEqual(r"Loks\Elektroloks\101\101.fzg", datei_nodes[1].attrib["Dateiname"])
          self.assertEqual(r"Loks\Elektroloks\102\102.fzg", datei_nodes[2].attrib["Dateiname"])
          self.assertEqual(r"..\..\NichtZusi\KeineDaten\Irgendwas.fzg", datei_nodes[3].attrib["Dateiname"])
        else:
          self.assertEqual(r"..\..\zusi2\daten\Loks\Elektroloks\101\101.fzg", datei_nodes[0].attrib["Dateiname"])
          self.assertEqual(r"Loks\Elektroloks\101\101.fzg", datei_nodes[1].attrib["Dateiname"])
          self.assertEqual(r"Loks\Elektroloks\102\102.fzg", datei_nodes[2].attrib["Dateiname"])
          self.assertEqual(r"..\..\nichtzusi\KeineDaten\Irgendwas.fzg", datei_nodes[3].attrib["Dateiname"])

  # ---
  # Variants tests
  # ---

  def test_variants(self):
    self.open("variants")
    root = self.export_and_parse()

  # ---
  # Mesh optimization tests
  # ---

  def test_mesh_optimization_vertex_dist(self):
    self.open("mesh_optimization_vertex_dist")

    # Max. coord delta 1.0
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 1.0,
      "maxUVDelta" : 9999,
      "maxNormalAngle" : 9999
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertVertexCoordsEqual([(1, 0, -1), (-1, 0, -1), (0, 0, 1)], vertices)

    # Max. coord delta 0.1
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 0.1,
      "maxUVDelta" : 9999,
      "maxNormalAngle" : 9999
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertVertexCoordsEqual([(1, 0, -1), (-1, 0, -1), (-0.4, 0, 1), (0.4, 0, 1)], vertices)

  def test_mesh_optimization_normal_angle(self):
    self.open("mesh_optimization_smooth_cube")

    # Unoptimized
    root = self.export_and_parse({
      "optimizeMesh" : False,
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertEqual(36, len(vertices))

    # Optimized
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 9999,
      "maxUVDelta" : 9999,
      "maxNormalAngle" : 0.1
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertEqual(8, len(vertices))

  def test_mesh_optimization_uv(self):
    self.open("mesh_optimization_uv")

    # Max. UV delta 0.0 - only merge vertices with exactly the same UV coordinates
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 9999,
      "maxUVDelta" : 0.0,
      "maxNormalAngle" : 9999
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertEqual(8, len(vertices))

    # Max. UV delta 0.2
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 9999,
      "maxUVDelta" : 0.2,
      "maxNormalAngle" : 9999
    })

    vertices = root.findall("./Landschaft/SubSet/Vertex")
    self.assertEqual(6, len(vertices))

  def test_mesh_optimization_normal0(self):
    """Tests mesh optimization when the normal of a vertex is 0. Such vertices should not be merged."""
    self.open("mesh_optimization_normal0")
    root = self.export_and_parse({
      "optimizeMesh" : True,
      "maxCoordDelta" : 0.001,
      "maxUVDelta" : 0.001,
      "maxNormalAngle" : 0.17,
    })
    subset = root.find("./Landschaft/SubSet")
    vertices = [v for v in subset if v.tag == "Vertex"]
    for idx, f in enumerate(subset.findall("./Face")):
      # Check that all normal vectors of the face point in the same direction.
      face_vertices = [vertices[i] for i in map(int, f.attrib["i"].split(";"))]
      face_normals = [v.find("n") for v in face_vertices]
      for to_compare in face_normals[1:]:
        self.assertXYZ(face_normals[0],
            float(to_compare.attrib["X"]), float(to_compare.attrib["Y"]), float(to_compare.attrib["Z"]),
            msg = "Face {}, vertices {}".format(idx, f.attrib["i"]))

  # ---
  # Animation tests - Basic
  # ---

  # Tests that the animation export restores the current frame number.
  def test_animation_restore_frame_no(self):
    self.open("animation_multiple_actions")
    bpy.context.scene.frame_set(5)
    self.assertEqual(5, bpy.context.scene.frame_current)
    self.export()
    self.assertEqual(5, bpy.context.scene.frame_current)

  # ---
  # Animation tests - File structure
  # ---

  # RadRotation (Empty, animated via keyframes)
  # +- Kuppelstange (Mesh, animated via Limit constraint)
  # => A separate file with the suffix "_RadRotation" is created.
  def test_animation_structure_child_with_constraint(self):
    self.open("animation_child_with_constraint")
    basename, ext, files = self.export_and_parse_multiple(["RadRotation"])

    # Test for correct linked file #1.
    verkn_nodes = files[""].findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verkn_nodes))

    datei_node = verkn_nodes[0].find("./Datei")
    self.assertEqual(basename + "_RadRotation" + ext, datei_node.attrib["Dateiname"])

    # Test for <Animation> node.
    animation_nodes = files[""].findall("./Landschaft/Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertEqual("2", animation_nodes[0].attrib["AniID"])
    self.assertEqual("Geschwindigkeit (angetrieben, gebremst)", animation_nodes[0].attrib["AniBeschreibung"])

    # Test for <VerknAnimation> node.
    verkn_animation_nodes = files[""].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    # Test linked file #1.
    # Test for <MeshAnimation> node in linked file #1.
    mesh_animation_nodes = files["RadRotation"].findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

    # No further linked file #2.
    self.assertEqual([], files["RadRotation"].findall("./Landschaft/Verknuepfte"))

  # RadRotation (Empty, animated via keyframes)
  # +- Kuppelstange (Mesh, non-animated)
  # => everything exported into one file.
  def test_animation_structure_nonanimated_child(self):
    self.open("animation_nonanimated_child")
    mainfile = self.export_and_parse({"exportAnimations" : True})

    verknuepfte_nodes = mainfile.findall("./Landschaft/Verknuepfte")
    self.assertEqual(0, len(verknuepfte_nodes))

    verkn_animation_nodes = mainfile.findall("./Landschaft/VerknAnimation")
    self.assertEqual(0, len(verkn_animation_nodes))

    mesh_animation_nodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

  # Unterarm (Mesh, animated via keyframes)
  # +- Oberarm (Mesh, animated via keyframes)
  #    +- Schleifstueck (Mesh, animated via constraint)
  def test_animation_structure_multiple_actions(self):
    self.open("animation_multiple_actions")
    basename, ext, files = self.export_and_parse_multiple(["Unterarm", "Oberarm"])

    # Test animation of linked file "Unterarm" in main file.
    animation_nodes = files[""].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertAniNrs(animation_nodes[0], [0])

    self.assertEqual([], files[""].findall(".//MeshAnimation"))
    verkn_animation_nodes = files[""].findall(".//VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniIndex"])

    # Test animation of linked file "Oberarm" in file "Unterarm"
    animation_nodes = files["Unterarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertAniNrs(animation_nodes[0], [0])

    self.assertEqual([], files["Unterarm"].findall(".//MeshAnimation"))
    verkn_animation_nodes = files["Unterarm"].findall(".//VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniIndex"])

    # Test animation of subset "Schleifstueck" in file "Oberarm"
    animation_nodes = files["Oberarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertAniNrs(animation_nodes[0], [0])

    self.assertEqual([], files["Oberarm"].findall(".//VerknAnimation"))
    mesh_animation_nodes = files["Oberarm"].findall(".//MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))
    self.assertEqual("0", mesh_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("1", mesh_animation_nodes[0].attrib["AniIndex"])

  # No animation is exported => no additional files are created
  def test_dont_export_animation(self):
    self.open("animation_multiple_actions")
    mainfile = self.export_and_parse({"exportAnimations" : False})
    self.assertEqual([], mainfile.findall(".//Verknuepfte"))
    self.assertEqual([], mainfile.findall(".//VerknAnimation"))
    self.assertEqual([], mainfile.findall(".//MeshAnimation"))
    self.assertEqual([], mainfile.findall(".//Animation"))
    self.assertEqual(1, len(mainfile.findall("./Landschaft/SubSet")))

  def test_animation_subfiles_keep_lod_suffix(self):
    self.open("animation_multiple_actions")
    mainfile_name = self.export({"ext" : ".lod1.ls3", "exportAnimations" : True})

    path, name = os.path.split(mainfile_name)
    basename, ext = name.split(os.extsep, 1)

    self.assertTrue(os.path.exists(os.path.join(path, basename + "_Unterarm.lod1.ls3")))
    self.assertTrue(os.path.exists(os.path.join(path, basename + "_Oberarm.lod1.ls3")))

  def test_animation_subfiles_without_extension(self):
    self.open("animation_multiple_actions")
    mainfile_name = self.export({"ext" : "", "exportAnimations" : True})
    self.assertTrue(os.path.exists(mainfile_name + "_Unterarm"))
    self.assertTrue(os.path.exists(mainfile_name + "_Oberarm"))

  def test_animation_names(self):
    self.open("animation_names")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    animation_nodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(3, len(animation_nodes))

    self.assertEqual("Hp0-Hp1", animation_nodes[0].attrib["AniBeschreibung"])
    self.assertAniNrs(animation_nodes[0], [0])

    self.assertEqual("Hp0-Hp2", animation_nodes[1].attrib["AniBeschreibung"])
    self.assertAniNrs(animation_nodes[1], [0, 1])

    self.assertEqual("Stromabnehmer A", animation_nodes[2].attrib["AniBeschreibung"])
    self.assertAniNrs(animation_nodes[2], [2])

  def test_animation_names_id_0(self):
    self.open("animation_names_id0")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    animation_nodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertNotEqual("", animation_nodes[0].attrib["AniBeschreibung"])
    self.assertAniNrs(animation_nodes[0], [0])


  def test_animation_index_linked_file(self):
    self.open("animation_index_linked_file")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    animation_nodes = mainfile.findall("./Landschaft/Animation")
    dateinamen = [n.attrib["Dateiname"] for n in mainfile.findall("./Landschaft/Verknuepfte/Datei")]
    self.assertIn("Empty1", dateinamen[0])
    self.assertIn("test.ls3", dateinamen[1])
    verkn_animation_node = mainfile.find("./Landschaft/VerknAnimation")
    self.assertEqual(0, int(verkn_animation_node.attrib["AniIndex"]))

  # ---
  # Animation tests - Mesh and animation data
  # ---

  def test_animation_child_with_constraint(self):
    self.open("animation_child_with_constraint")
    basename, ext, files = self.export_and_parse_multiple(["RadRotation"])

    # The position of linked file #1 is not animated, therefore it is included
    # in the link and not in the animation.
    verknuepfte_node = files[""].find("./Landschaft/Verknuepfte")
    self.assertXYZ(verknuepfte_node.find("./p"), 0, 1, 0)
    self.assertEqual(0, len(verknuepfte_node.find('sk').attrib))

    # Check for <AniNrs> node in <Animation> node.
    animation_node = files[""].find("./Landschaft/Animation")
    self.assertAniNrs(animation_node, [0])

    # Check for correct <VerknAnimation> node.
    verkn_animation_node = files[""].find("./Landschaft/VerknAnimation")
    self.assertEqual("0", verkn_animation_node.attrib["AniNr"])

    # Check for keyframes.
    self.assertKeyframes(verkn_animation_node, [0, 0.25, 0.5, 0.75, 1.0])
    q_nodes = verkn_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertXYZW(q_nodes[0], 0, 0, 0, 1)
    self.assertXYZW(q_nodes[1], 0, 0.707107, 0, 0.707107)
    self.assertXYZW(q_nodes[2], 0, 1, 0, 0)
    self.assertXYZW(q_nodes[3], 0, 0.707107, 0, -0.707107)
    self.assertXYZW(q_nodes[4], 0, 0, 0, -1)

    for p_node in verkn_animation_node.findall("./AniPunkt/p"):
        self.assertXYZ(p_node, 0, 0, 0)

    # Check linked file #1.
    # Check for correct <VerknAnimation> node.
    mesh_animation_node = files["RadRotation"].find("./Landschaft/MeshAnimation")
    self.assertEqual("0", mesh_animation_node.attrib["AniNr"])

    # Check for keyframes.
    self.assertKeyframes(mesh_animation_node, [0.0, 0.25, 0.5, 0.75, 1.0])

    p_nodes = mesh_animation_node.findall("./AniPunkt/p")
    self.assertEqual(5, len(p_nodes))
    for i in range(0, 5):
      self.assertXYZ(p_nodes[i], 0, 0, 0.8, msg = "p node " + str(i))

    q_nodes = mesh_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertXYZW(q_nodes[0], 0, 0, 0, 1)
    self.assertXYZW(q_nodes[1], 0, -0.707107, 0, 0.707107)
    self.assertXYZW(q_nodes[2], 0, -1, 0, 0)
    self.assertXYZW(q_nodes[3], 0, -0.707107, 0, -0.707107)
    self.assertXYZW(q_nodes[4], 0, 0, 0, -1)

    # Check subset.
    # There should be 4 vertices, all of which have the Y coordinate 0 (because
    # the translation is applied in the parent file's Verknuepfte node) and
    # Z coordinates between -0.1 and 0.1 (the object's scale is applied!)
    vertices = files["RadRotation"].findall("./Landschaft/SubSet/Vertex/p")
    self.assertEqual(6, len(vertices))
    for i in range(0, len(vertices)):
      self.assertAlmostEqual(0.0, float(vertices[i].attrib["Y"]),
        places = 5, msg = "Y coordinate of vertex " + str(i))
      self.assertLess(abs(float(vertices[i].attrib["Z"])), 0.1,
        msg = "Z coordinate of vertex " + str(i))

  def test_subset_animation_rotation(self):
    self.open("animation4")
    mainfile = self.export_and_parse({"exportAnimations":True})

    self.assertEqual([], mainfile.findall("./Landschaft/Verknuepfte"))
    self.assertEqual([], mainfile.findall("./Landschaft/VerknAnimation"))

    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual(2, len(subsets))

    animationNodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animationNodes))
    self.assertAniNrs(animationNodes[0], [0])

    meshAnimationNodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(meshAnimationNodes))
    self.assertEqual("0", meshAnimationNodes[0].attrib["AniNr"])

    self.assertKeyframes(meshAnimationNodes[0], [0.0, 0.25, 0.5, 0.75, 1.0])
    p_nodes = meshAnimationNodes[0].findall("./AniPunkt/p")
    for p_node in p_nodes:
        self.assertXYZ(p_node, 0, 0, 0)

    q_nodes = meshAnimationNodes[0].findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertXYZW(q_nodes[0], 0, 0, 0, 1)
    self.assertXYZW(q_nodes[1], 0, 0, 0.707107, 0.707107)
    self.assertXYZW(q_nodes[2], 0, 0, 1, 0)
    self.assertXYZW(q_nodes[3], 0, 0, 0.707107, -0.707107)
    self.assertXYZW(q_nodes[4], 0, 0, 0, -1)

  def test_subset_animation_rotation_with_offset(self):
    self.open("animation5")
    mainfile = self.export_and_parse({"exportAnimations":True})

    self.assertEqual([], mainfile.findall("./Landschaft/Verknuepfte"))
    self.assertEqual([], mainfile.findall("./Landschaft/VerknAnimation"))

    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))

    animationNodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animationNodes))
    self.assertAniNrs(animationNodes[0], [0])

    meshAnimationNodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(meshAnimationNodes))
    self.assertEqual("0", meshAnimationNodes[0].attrib["AniNr"])

    self.assertKeyframes(meshAnimationNodes[0], [0.0, 0.25, 0.5, 0.75, 1.0])

    p_nodes = meshAnimationNodes[0].findall("./AniPunkt/p")
    self.assertEqual(5, len(p_nodes))
    for i in range(0, 5):
      self.assertXYZ(p_nodes[i], -3, 2, 4, msg = "p node " + str(i))

    q_nodes = meshAnimationNodes[0].findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertXYZW(q_nodes[0], 0, 0, 0, 1)
    self.assertXYZW(q_nodes[1], 0, 0, 0.707107, 0.707107)
    self.assertXYZW(q_nodes[2], 0, 0, 1, 0)
    self.assertXYZW(q_nodes[3], 0, 0, 0.707107, -0.707107)
    self.assertXYZW(q_nodes[4], 0, 0, 0, -1)

  # Cube (animated via keyframe)
  # +- Empty (animated via constraint)
  # => only one file is created
  def test_animated_nonmesh_child(self):
    self.open("animation_animated_nonmesh_children")
    root = self.export_and_parse({"exportAnimations" : True})

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))

    verknuepfte = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(0, len(verknuepfte))

  def test_animation_animated_child_of_scaled_object(self):
    self.open("animation_animated_child_of_scaled_object")
    files = self.export_and_parse_multiple(["Cube"])[2]

    # Check that the <Verknuepfte> node has correct scaling.
    verknuepfte_node = files[""].find("./Landschaft/Verknuepfte")
    sk_node = verknuepfte_node.find("./sk")
    self.assertXYZ(sk_node, 0.5, 0.5, 0.5)

    # Check that the animated subset in the linked file has its scaling
    # applied (relative to the parent subset) and the root subset has not
    # (the scale is contained in the <Verknuepfte> node).
    mesh_animation_node = files["Cube"].find("./Landschaft/MeshAnimation")
    animated_subset_index = int(mesh_animation_node.attrib["AniIndex"])

    subsets = files["Cube"].findall("./Landschaft/SubSet")
    animated_subset = subsets[animated_subset_index]
    nonanimated_subset = subsets[(animated_subset_index + 1) % 2]

    vertices = animated_subset.findall("./Vertex/p")
    self.assertEqual(36, len(vertices))
    for vertex in vertices:
      self.assertAlmostEqual(0.5, abs(float(vertex.attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.5, abs(float(vertex.attrib["Z"])), places = 5)

    vertices = nonanimated_subset.findall("./Vertex/p")
    self.assertEqual(36, len(vertices))
    for vertex in vertices:
      self.assertAlmostEqual(1.0, abs(float(vertex.attrib["Y"])), places = 5)
      self.assertAlmostEqual(1.0, abs(float(vertex.attrib["Z"])), places = 5)

  def test_animation_animated_child_of_scaled_object_without_animation(self):
    self.open("animation_animated_child_of_scaled_object")
    mainfile = self.export_and_parse()

    subsets = mainfile.findall("./Landschaft/SubSet")

    vertices = subsets[0].findall("./Vertex/p")
    self.assertEqual(36, len(vertices))
    for vertex in vertices:
      # X coordinate between 2.5 and 3.5.
      self.assertLess(abs(float(vertex.attrib["X"]) - 3), 1.01)
      self.assertAlmostEqual(0.5, abs(float(vertex.attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.5, abs(float(vertex.attrib["Z"])), places = 5)

    vertices = subsets[1].findall("./Vertex/p")
    self.assertEqual(36, len(vertices))
    for vertex in vertices:
      # X coordinate between 5.75 and 6.25
      self.assertLess(abs(float(vertex.attrib["X"]) - 6), 0.51)
      self.assertAlmostEqual(0.25, abs(float(vertex.attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.25, abs(float(vertex.attrib["Z"])), places = 5)

  # Tests that keyframes that lie outside the start...end frame range defined in the scene
  # are exported
  def test_animation_range_extends_scene_range(self):
    self.open("animation_keyframes_outside_scene_range")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    mesh_animation_node = mainfile.find("./Landschaft/MeshAnimation")
    self.assertKeyframes(mesh_animation_node, [0, 1, 2])

  def test_frame_start_equals_frame_end(self):
    self.open("frame_start_equals_frame_end")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    mesh_animation_node = mainfile.find("./Landschaft/MeshAnimation")
    self.assertKeyframes(mesh_animation_node, [0])

  def test_animation_speed(self):
    self.open("animation_speed")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    animation1 = mainfile.find("./Landschaft/MeshAnimation")
    self.assertEqual(1.5, float(animation1.attrib["AniGeschw"]))
    animation2 = mainfile.find("./Landschaft/VerknAnimation")
    self.assertEqual(0.0, float(animation2.attrib["AniGeschw"]))

  def test_animation_wheel_diameter(self):
    self.open("animation_speed")
    action = bpy.data.actions[0]
    action.zusi_animation_speed = 0
    self.assertEqual(0, action.zusi_animation_speed)
    self.assertAlmostEqual(0, action.zusi_animation_wheel_diameter, places = 6)

    action.zusi_animation_wheel_diameter = 0.9 # see example in documentation
    self.assertAlmostEqual(0.3536776, action.zusi_animation_speed, places = 6)

    action.zusi_animation_wheel_diameter = 0 # see example in documentation
    self.assertAlmostEqual(0, action.zusi_animation_speed, places = 6)

    action.zusi_animation_speed = 1.2
    self.assertAlmostEqual(0.2652582, action.zusi_animation_wheel_diameter, places = 6)

  def test_animation_duration(self):
    self.open("animation_speed")
    action = bpy.data.actions[0]
    action.zusi_animation_speed = 0
    self.assertEqual(0, action.zusi_animation_speed)
    self.assertAlmostEqual(0, action.zusi_animation_duration, places = 6)

    action.zusi_animation_duration = 4
    self.assertAlmostEqual(0.25, action.zusi_animation_speed, places = 6)

    action.zusi_animation_speed = 0.1
    self.assertAlmostEqual(10, action.zusi_animation_duration, places = 6)

    action.zusi_animation_duration = 0
    self.assertAlmostEqual(0, action.zusi_animation_speed, places = 6)


  # Tests that an object with constraints that is not a child of an animated object
  # is exported as animated.
  def test_animation_with_constraints_only(self):
    self.open("animation_object_animated_only_by_constraints")
    mainfile = self.export_and_parse({"exportAnimations" : True})

    # The subset "Treibstange" should be animated and have the animation
    # type of the "Raddrehung" empty.
    animation_node = mainfile.find("./Landschaft/Animation")
    self.assertEqual("5", animation_node.attrib["AniID"])
    ani_nrs_nodes = animation_node.findall("AniNrs")
    self.assertEqual(2, len(ani_nrs_nodes))
    self.assertNotEqual(None, animation_node.find("./AniNrs[@AniNr='0']"))

    mesh_animation_nodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))
    self.assertEqual("0", mesh_animation_nodes[0].attrib["AniNr"])

  def test_animation_rotation_axes(self):
    self.open("animation9")
    mainfile = self.export_and_parse({"exportAnimations" : True})

    mesh_animation_nodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(3, len(mesh_animation_nodes))

    ani_frames = [node.findall("./AniPunkt") for node in mesh_animation_nodes]

    self.assertXYZW(ani_frames[0][0].find("q"), 0, 0, 0, 1)
    self.assertXYZW(ani_frames[0][1].find("q"), 0, .707107, 0, .707107)
    self.assertXYZW(ani_frames[1][0].find("q"), 0, 0, 0, 1)
    self.assertXYZW(ani_frames[1][1].find("q"), -.707107, 0, 0, .707107)
    self.assertXYZW(ani_frames[2][0].find("q"), 0, 0, 0, 1)
    self.assertXYZW(ani_frames[2][1].find("q"), 0, 0, .707107, .707107)

  def test_animation_rotation_axes_linked(self):
    self.open("animation_linked_rotation")
    files = self.export_and_parse_multiple(["RotY"])[2]

    verkn_animation_nodes = files[""].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    ani_frames = verkn_animation_nodes[0].findall("./AniPunkt")
    self.assertXYZW(ani_frames[0].find("q"), 0, -0.258819, 0, 0.965925)
    self.assertXYZW(ani_frames[1].find("q"), -0.707106, 0, 0, 0.707107)

    mesh_animation_nodes = files["RotY"].findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

    ani_frames = mesh_animation_nodes[0].findall("./AniPunkt")
    self.assertXYZW(ani_frames[0].find("q"), 0.408218, 0.2345697, -0.109381, 0.875426)
    self.assertXYZW(ani_frames[1].find("q"), 0.365998, -0.4531538, 0.2113099, 0.784885)

  def test_animation_parenting_scale(self):
    self.open("animation_parenting_scale")
    mainfile = self.export_and_parse({"exportAnimations" : True})

    # There are two Cubes with the same material; one is the parent of the other.
    # The child cube has a scale of 0.5, but is not animated. The cubes should
    # be exported into one subset and the scale should be correctly applied.
    linkedfiles = mainfile.findall("./Landschaft/Verknuepfte")
    self.assertEqual([], linkedfiles)
    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))
    for p_node in subsets[0].findall("./Vertex/p"):
      self.assertAlmostEqual(1, abs(float(p_node.attrib["Z"])))

  def test_nonanimated_parenting_scale(self):
    self.open("parenting_scale")
    root = self.export_and_parse({"exportAnimations" : True})

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))

    vertex_nodes = [n for n in subsets[0] if n.tag == "Vertex"]
    self.assertEqual(72, len(vertex_nodes))

    vertices = set()
    for vertex_node in vertex_nodes:
      p_node = vertex_node.find("./p")
      (x, y, z) = [round(float(p_node.attrib[c]), 1) for c in "XYZ"]
      vertices.add((x, y, z))
    vertices = sorted(list(vertices))

    expected_vertices = []
    for x in [1.0, 2.0, 3.0, 4.0]:
      expected_vertices.append((x, -.5, -.5))
      expected_vertices.append((x, -.5,  .5))
      expected_vertices.append((x,  .5, -.5))
      expected_vertices.append((x,  .5,  .5))

    self.assertListEqual(expected_vertices, vertices)

  def test_animation_authorinfo(self):
    self.open("animation_authorinfo")
    files = self.export_and_parse_multiple(["Parent"])[2]

    author = files[""].findall("./Info/AutorEintrag")
    self.assertEqual(1, len(author))
    self.assertEqual("Fritz Fleissig", author[0].attrib["AutorName"])
    self.assertEqual("Everything", author[0].attrib["AutorBeschreibung"])
    self.assertNotIn("AutorAufwand", author[0].attrib)

    expensepath = os.path.join(ZUSI3_EXPORTPATH, "export.ls3.expense.xml")
    expenseroot = ET.parse(expensepath).getroot()
    author = expenseroot.findall("./Info/AutorEintrag")
    self.assertEqual(1, len(author))
    self.assertEqual("Fritz Fleissig", author[0].attrib["AutorName"])
    self.assertEqual("Everything", author[0].attrib["AutorBeschreibung"])
    self.assertEqual(5, float(author[0].attrib["AutorAufwand"]))

    author = files["Parent"].findall("./Info/AutorEintrag")
    self.assertEqual(1, len(author))
    self.assertEqual("Fritz Fleissig", author[0].attrib["AutorName"])
    self.assertEqual("Everything", author[0].attrib["AutorBeschreibung"])
    self.assertNotIn("AutorAufwand", author[0].attrib)

    expensepath = os.path.join(ZUSI3_EXPORTPATH, "export_Parent.ls3.expense.xml")
    self.assertFalse(os.path.exists(expensepath))

  def test_animation_spaces_in_object_name(self):
    self.open("animation_spaces_in_object_name")
    try:
      files = self.export_and_parse_multiple(["Parent_with_spaces"])
    except FileNotFoundError as e:
      self.fail(str(e))

  def test_boundingr(self):
    self.open("boundingr")
    basename, ext, files = self.export_and_parse_multiple(["Planet", "Mond"])

    # Check bounding radius of file "Planet".
    # Not the original bounding radius of the linked file, but the scaled radius has to be specified.
    verknuepfte_nodes = files[""].findall(".//Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))
    self.assertEqual("10", verknuepfte_nodes[0].attrib["BoundingR"])

    # Check bounding radius of file "Mond".
    verknuepfte_nodes = files["Planet"].findall(".//Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))
    self.assertEqual("4", verknuepfte_nodes[0].attrib["BoundingR"])

    self.assertEqual([], files["Mond"].findall(".//Verknuepfte"))

  def test_boundingr_translation(self):
    self.open("boundingr_translation")
    basename, ext, files = self.export_and_parse_multiple(["Empty"])

    mainfile = files[""]
    verknuepfte_node = mainfile.find("./Landschaft/Verknuepfte")
    self.assertEqual(7, int(verknuepfte_node.attrib["BoundingR"]))

    linkedfile = files["Empty"]
    verknuepfte_node = linkedfile.find("./Landschaft/Verknuepfte")
    p_node = verknuepfte_node.find("./p")
    self.assertAlmostEqual(2.5, float(p_node.attrib["X"]))
    self.assertAlmostEqual(2.5, float(p_node.attrib["Z"]))
    # BoundingR: 1.41 for the mesh + 2.5 for the translation
    self.assertEqual(4, int(verknuepfte_node.attrib["BoundingR"]))

  def test_rotation_translation_animation(self):
    self.open("rotation_translation_animation")
    root = self.export_and_parse({"exportAnimations" : True})
    verknuepfte_node = root.find("./Landschaft/Verknuepfte")
    self.assertEqual(8, int(verknuepfte_node.attrib["BoundingR"]))
    self.assertAlmostEqual(5, float(verknuepfte_node.find("./p").attrib["X"]))

    ani_punkt_nodes = root.findall("./Landschaft/VerknAnimation/AniPunkt")
    self.assertEqual(2, len(ani_punkt_nodes))
    self.assertAlmostEqual(-5.0, float(ani_punkt_nodes[0].find("./p").attrib["X"]))
    self.assertAlmostEqual(5.0, float(ani_punkt_nodes[1].find("./p").attrib["X"]))

  def test_rotation_animation_translated(self):
    self.open("rotation_animation_translated")
    root = self.export_and_parse({"exportAnimations" : True})
    verknuepfte_node = root.find("./Landschaft/Verknuepfte")

    self.assertEqual(3, int(verknuepfte_node.attrib["BoundingR"]))
    self.assertAlmostEqual(10.0, float(verknuepfte_node.find("./p").attrib["X"]))

    ani_punkt_p_nodes = root.findall("./Landschaft/VerknAnimation/AniPunkt/p")
    for node in ani_punkt_p_nodes:
      self.assertXYZ(node, 0, 0, 0)

  def test_animation_continuation(self):
    self.open("animation_continuation")
    root = self.export_and_parse({"exportAnimations" : True})

    mesh_animation_nodes = root.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

    keyframes = [float(p.attrib["AniZeit"]) if "AniZeit" in p.attrib else 0.0 for p in mesh_animation_nodes[0].findall("./AniPunkt")]
    self.assertEqual([0.0, 0.25, 0.7, 1.25, 2.0], keyframes) # should add keyframes at 0.0 and 2.0

  def test_animation_loop(self):
    self.open("animation_loop")
    root = self.export_and_parse({"exportAnimations" : True})
    animation_nodes = root.findall("./Landschaft/Animation")
    self.assertEqual(3, len(animation_nodes))

    self.assertNotIn("AniLoopen", animation_nodes[0].attrib)
    self.assertEqual("1", animation_nodes[1].attrib["AniLoopen"])
    self.assertNotIn("AniLoopen", animation_nodes[2].attrib)

  def test_animation_with_and_without_loop(self):
    self.open("animation_with_and_without_loop")
    root = self.export_and_parse({"exportAnimations" : True})
    animation_nodes = root.findall("./Landschaft/Animation")
    self.assertEqual(2, len(animation_nodes))

    self.assertEqual("Zeitlich kontinuierlich (loop)", animation_nodes[1].attrib["AniBeschreibung"])
    self.assertEqual("1", animation_nodes[1].attrib["AniLoopen"])

    self.assertEqual("Zeitlich kontinuierlich", animation_nodes[0].attrib["AniBeschreibung"])
    self.assertNotIn("AniLoopen", animation_nodes[0].attrib)

  def test_set_interpolation_linear(self):
    self.open("animation_set_interpolation_linear")
    for fcurve in bpy.data.actions["CubeAction"].fcurves:
        for keyframe in fcurve.keyframe_points:
            self.assertEqual('BEZIER', keyframe.interpolation)

    self.assertEqual({'FINISHED'}, bpy.ops.action.set_interpolation_linear(action_name = "CubeAction"))
    for fcurve in bpy.data.actions["CubeAction"].fcurves:
        for keyframe in fcurve.keyframe_points:
            self.assertEqual('LINEAR', keyframe.interpolation)

  # ---
  # Anchor point tests
  # ---

  def test_anchor_point_export(self):
    self.open("anchor_points")
    assert(ZUSI3_EXPORTPATH != ZUSI3_DATAPATH);
    bpy.data.objects["01_Anchor_01"].zusi_anchor_point_files[0].name = os.path.join(ZUSI3_EXPORTPATH, "file.ls3")
    bpy.data.objects["01_Anchor_01"].zusi_anchor_point_files[1].name = os.path.join(ZUSI3_EXPORTPATH, "folder")
    bpy.data.objects["01_Anchor_01"].zusi_anchor_point_files[2].name = os.path.join(ZUSI3_DATAPATH, "file.ls3")
    bpy.data.objects["01_Anchor_01"].zusi_anchor_point_files[3].name = os.path.join(ZUSI3_DATAPATH, "folder")
    root = self.export_and_parse()

    anchor_point_nodes = root.findall("./Landschaft/Ankerpunkt")
    self.assertEqual(2, len(anchor_point_nodes))

    a1 = anchor_point_nodes[0]
    self.assertEqual("1", a1.attrib["AnkerKat"])
    self.assertEqual("2", a1.attrib["AnkerTyp"])
    self.assertEqual("Anchor point 1 description", a1.attrib["Beschreibung"])

    a1files = a1.findall("./Datei")
    self.assertEqual(4, len(a1files))

    # Paths must be relative to the data directory to work in Zusi 3D Editor
    self.assertEqual("ExportTest\\file.ls3", a1files[0].attrib["Dateiname"])
    self.assertEqual("ExportTest\\folder", a1files[1].attrib["Dateiname"])
    self.assertEqual("\\file.ls3", a1files[2].attrib["Dateiname"])
    self.assertEqual("\\folder", a1files[3].attrib["Dateiname"])

    for i in range(0, 4):
        self.assertEqual("1", a1files[1].attrib["NurInfo"])

    a2 = anchor_point_nodes[1]
    self.assertEqual("Anchor point 2 description", a2.attrib["Beschreibung"])
    self.assertXYZ(a2.find("./p"), -2, 1, 3)
    rot = mathutils.Euler((radians(10), radians(20), radians(30))).to_quaternion().to_euler('YXZ')
    self.assertXYZ(a2.find("./phi"), -rot.y, rot.x, rot.z)

    a2files = a2.findall("./Datei")
    self.assertEqual(0, len(a2files))

  def test_anchor_points_variants(self):
    self.open("anchor_points_variants")

    for variants, expected in [([0], ["A", "AB"]), ([1], ["B", "AB"]),
        ([0, 1], ["A", "B", "AB"]), ([], ["A", "B", "AB", "None"])]:
      root = self.export_and_parse({"variants": variants})
      anchor_points = set([a.attrib["Beschreibung"] for a in root.findall("./Landschaft/Ankerpunkt")])
      self.assertEqual(set(expected), anchor_points)

  # ---
  # Tests for Emptys exported as linked files
  # ---

  def test_linked_file_export(self):
    self.open("linked_files")
    root = self.export_and_parse()

    subset_nodes = root.findall("./Landschaft/SubSet")
    self.assertEqual(0, len(subset_nodes))

    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(5, len(verknuepfte_nodes))

    v1phi = verknuepfte_nodes[0].find("phi")
    self.assertXYZ(v1phi, 0, radians(40), 0)

    v2phi = verknuepfte_nodes[1].find("phi")
    self.assertXYZ(v2phi, radians(-30), 0, 0)

    v3phi = verknuepfte_nodes[2].find("phi")
    self.assertXYZ(v3phi, 0, 0, radians(20))

    v4 = verknuepfte_nodes[3]
    self.assertEqual(r"RollingStock\Diverse\Blindlok\Blindlok.ls3", v4.find("Datei").attrib["Dateiname"])
    self.assertEqual(0, len(v4.find("p").attrib))
    self.assertEqual(0, len(v4.find("phi").attrib))
    self.assertEqual(0, len(v4.find("sk").attrib))
    self.assertEqual("TestGroup", v4.attrib["GruppenName"])
    self.assertEqual(1.5, float(v4.attrib["SichtbarAb"]))
    self.assertEqual(5.5, float(v4.attrib["SichtbarBis"]))
    self.assertEqual(13.5, float(v4.attrib["Vorlade"]))
    self.assertEqual(15, int(v4.attrib["BoundingR"]))
    self.assertEqual(0.5, float(v4.attrib["Helligkeit"]))
    self.assertEqual(10, int(v4.attrib["LODbit"]))
    self.assertEqual(4 + 8, int(v4.attrib["Flags"])) # Tile + Billboard

    v5 = verknuepfte_nodes[4]
    self.assertEqual(r"RollingStock\Deutschland\Epoche5\Elektroloks\101\3D-Daten\101_vr.lod.ls3", v5.find("Datei").attrib["Dateiname"])
    self.assertXYZ(v5.find("p"), -1, 2, -3)

    rot = mathutils.Euler((radians(20), radians(-21), radians(45))).to_quaternion().to_euler('YXZ')
    self.assertXYZ(v5.find("phi"), -rot.y, rot.x, rot.z)

    self.assertXYZ(v5.find("sk"), 1.5, 2.5, 3.5)

    self.assertNotIn("GruppenName", v5.attrib)
    self.assertNotIn("SichtbarAb", v5.attrib)
    self.assertNotIn("SichtbarBis", v5.attrib)
    self.assertNotIn("SichtbarBis", v5.attrib)
    self.assertNotIn("Vorlade", v5.attrib)
    self.assertNotIn("BoundingR", v5.attrib)
    self.assertNotIn("Helligkeit", v5.attrib)
    self.assertEqual(5, int(v5.attrib["LODbit"]))
    self.assertEqual(32 + 16, int(v5.attrib["Flags"])) # Detail tile + read only

  def test_linked_file_parented(self):
    self.open("linked_file_parented")
    files = self.export_and_parse_multiple(["Cube"])[2]

    root = files["Cube"]
    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))
    self.assertXYZ(verknuepfte_nodes[0].find("./p"), 0, 6, 0)

  def test_linked_file_animation(self):
    self.open("linked_file_animation")
    root = self.export_and_parse({"exportAnimations": True})

    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))

    verkn_animation_nodes = root.findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    self.assertEqual(0, int(verkn_animation_nodes[0].attrib["AniIndex"]))

    ani_pkt_nodes = verkn_animation_nodes[0].findall("./AniPunkt")
    self.assertEqual(2, len(ani_pkt_nodes))

    animation_nodes = root.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animation_nodes))

    self.assertEqual(6, int(animation_nodes[0].attrib["AniID"]))

  def test_linked_file_boundingr(self):
    self.open("linked_file_boundingr")
    files = self.export_and_parse_multiple(["Cube"])[2]

    root = files[""]
    verknuepfte_node = root.find("./Landschaft/Verknuepfte")
    self.assertEqual(26, int(verknuepfte_node.attrib["BoundingR"]))

  def test_linked_file_animation_parented(self):
    self.open("linked_file_animation_parented")
    files = self.export_and_parse_multiple(["Cube", "Cube.001"])[2]

    root = files["Cube.001"]
    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))

    verkn_animation_nodes = root.findall("./Landschaft/VerknAnimation")
    self.assertEqual(0, len(verkn_animation_nodes))
    animation_nodes = root.findall("./Landschaft/Animation")
    self.assertEqual(0, len(animation_nodes))

  def test_linked_file_variant_visibility(self):
    self.open("linked_file_variant_visibility")
    root = self.export_and_parse({"variants" : [1]})

    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))

    root = self.export_and_parse({"variants" : [0]})

    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(0, len(verknuepfte_nodes))

  def test_linked_file_export_selected(self):
    self.open("linked_file_export_selected")
    root = self.export_and_parse({"exportSelected" : "1", "selected_objects": ["Cube", "Empty.001", "Empty"]})
    self.assertEqual(1, len(root.findall("./Landschaft/Verknuepfte")))

    root = self.export_and_parse({"exportSelected" : "1", "selected_objects": ["Cube", "Empty"]})
    self.assertEqual(1, len(root.findall("./Landschaft/Verknuepfte")))

    root = self.export_and_parse({"exportSelected" : "1", "selected_objects": ["Cube"]})
    self.assertEqual(0, len(root.findall("./Landschaft/Verknuepfte")))

    root = self.export_and_parse({"exportSelected" : "1", "selected_objects": ["Empty.001", "Empty"]})
    self.assertEqual(1, len(root.findall("./Landschaft/Verknuepfte")))

    root = self.export_and_parse({"exportSelected" : "1", "selected_objects": ["Empty"]})
    self.assertEqual(1, len(root.findall("./Landschaft/Verknuepfte")))

  def test_linked_file_lod(self):
    self.open("linked_file_lod")
    root = self.export_and_parse()

    verknuepfte_nodes = root.findall("./Landschaft/Verknuepfte")
    self.assertEqual(5, len(verknuepfte_nodes))

    self.assertEqual(8, int(verknuepfte_nodes[0].attrib["LODbit"]))
    self.assertEqual(4, int(verknuepfte_nodes[1].attrib["LODbit"]))
    self.assertEqual(2, int(verknuepfte_nodes[2].attrib["LODbit"]))
    self.assertEqual(1, int(verknuepfte_nodes[3].attrib["LODbit"]))
    self.assertEqual(11, int(verknuepfte_nodes[4].attrib["LODbit"]))

  def test_linked_file_link_animations(self):
    self.open("linked_file_link_animations")
    root = self.export_and_parse({"exportAnimations" : True})

    animationen = set((int(n.attrib.get("AniID", 0)), n.attrib.get("AniBeschreibung", ""))
            for n in root.findall("./Landschaft/Animation"))
    self.assertEqual(
        set([(0, "Test 1"), (0, "Test 2"), (0, "Undefiniert/signalgesteuert"), (8, "Test 2"), (8, "Stromabnehmer 1"), (8, "Stromabnehmer A"), ]),
        animationen)

  # ---
  # Batch export tests
  # ---

  def test_batch_export_settings(self):
    self.open("batchexport")
    batchexport_xml = """
      <batchexport_settings>
        <setting blendfile="{blendfile}">
          <export ls3file="{ls3file1}" exportmode="SubsetsOfSelectedObjects">
            <select>Cube</select>
            <variant>B</variant>
          </export>
          <export ls3file="{ls3file2}" exportmode="SelectedMaterials">
            <select>NonExistingMaterial</select>
            <variant>NonExistingVariant</variant>
          </export>
        </setting>
      </batchexport_settings>
    """.format(
        blendfile = os.path.join(os.getcwd(), "blends", "batchexport.blend"),
        ls3file1 = os.path.join(ZUSI3_EXPORTPATH, "Test", "export1.ls3"),
        ls3file2 = os.path.join(ZUSI3_EXPORTPATH, "Test", "export2.ls3"))

    with open(os.path.join(os.path.dirname(sys.modules['io_scene_ls3'].__file__),
        "batchexport_settings.xml"), "w") as f:
      f.write(batchexport_xml)

    with patch("io_scene_ls3.ls3_export.Ls3Exporter") as mock:
      self.assertEqual({'FINISHED'}, bpy.ops.export_scene.ls3_batch())
      self.assertEqual(2, mock.call_count)

      settings = mock.call_args_list[0][0][0]
      self.assertEqual(os.path.join(ZUSI3_EXPORTPATH, "Test", "export1.ls3"), settings.filePath)
      self.assertEqual("export1.ls3", settings.fileName)
      self.assertEqual(os.path.join(ZUSI3_EXPORTPATH, "Test"), settings.fileDirectory)
      self.assertEqual("2", settings.exportSelected)
      self.assertEqual([1], settings.variantIDs)
      self.assertEqual(["Cube"], settings.selectedObjects)

      settings = mock.call_args_list[1][0][0]
      self.assertEqual(os.path.join(ZUSI3_EXPORTPATH, "Test", "export2.ls3"), settings.filePath)
      self.assertEqual("3", settings.exportSelected)
      self.assertEqual([], settings.variantIDs)
      self.assertEqual(["NonExistingMaterial"], settings.selectedObjects)

if __name__ == '__main__':
  try:
    # Arguments passed after "--" are not parsed by Blender.
    argv = sys.argv[sys.argv.index("--") + 1:]
  except ValueError:
    argv = []
  unittest.main(argv=['ls3_export_test.py'] + argv, verbosity=2)
  bpy.ops.wm.quit_blender()
