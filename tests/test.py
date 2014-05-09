import bpy
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

class TestLs3Export(unittest.TestCase):
  def setUp(self):
    bpy.ops.wm.read_homefile()

    # Copy test blend files into temporary directory
    self.tempfiles = []
    self.tempdir = tempfile.mkdtemp()
    shutil.copytree("blends", os.path.join(self.tempdir, "blends"))

  def tearDown(self):
    for tempfile in self.tempfiles:
      tempfile.close()
    shutil.rmtree(self.tempdir)

  def clear_scene(self):
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

  def export(self, exportargs={}):
    context = bpy.context.copy()
    context['selected_objects'] = []

    tempfile_file = tempfile.NamedTemporaryFile(suffix=exportargs.get("ext", ".ls3"))
    self.tempfiles.append(tempfile_file)

    tempfile_path = tempfile_file.name
    (tempfile_dir, tempfile_name) = os.path.split(tempfile_path)

    if "exportSelected" not in exportargs:
      exportargs["exportSelected"] = "0"

    if "optimizeMesh" not in exportargs:
      exportargs["optimizeMesh"] = False

    bpy.ops.io_export_scene.ls3(context,
      filepath=tempfile_path, filename=tempfile_name, directory=tempfile_dir,
      **exportargs)

    return tempfile_file

  def export_and_parse(self, exportargs={}):
    exported_file = self.export(exportargs)
    print(exported_file.read())
    tree = ET.parse(exported_file.name)
    return tree.getroot()

  def export_and_parse_multiple(self, additional_suffixes, exportargs={}):
    mainfile = self.export(exportargs)
    print(mainfile.read())

    (path, name) = os.path.split(mainfile.name)
    (basename, ext) = os.path.splitext(name)

    mainfile_tree = ET.parse(mainfile.name)
    mainfile_root = mainfile_tree.getroot()

    result = {"" : mainfile_root}

    for suffix in additional_suffixes:
      (path, name) = os.path.split(mainfile.name)
      (basename, ext) = os.path.splitext(name)

      additional_filename = os.path.join(path, basename + "_" + suffix + ext)
      additional_tree = ET.parse(additional_filename)
      additional_root = additional_tree.getroot()
      result[suffix] = additional_root

    return basename, ext, result

  def assertRotation(self, node, expected_x, expected_y, expected_z, expected_w):
    self.assertXYZ(node, expected_x, expected_y, expected_z)
    if expected_w != 0.0 or "W" in node.attrib:
      self.assertAlmostEqual(expected_w, float(node.attrib["W"]), places = 5)

  def assertXYZ(self, node, expected_x, expected_y, expected_z):
    if expected_x != 0.0 or "X" in node.attrib:
      self.assertAlmostEqual(expected_x, float(node.attrib["X"]), places = 5)
    if expected_y != 0.0 or "Y" in node.attrib:
      self.assertAlmostEqual(expected_y, float(node.attrib["Y"]), places = 5)
    if expected_z != 0.0 or "Z" in node.attrib:
      self.assertAlmostEqual(expected_z, float(node.attrib["Z"]), places = 5)

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

  def test_export_simple_cube(self):
    root = self.export_and_parse()

    # <Landschaft> node contains one subset
    landschaft_node = root.find("./Landschaft")
    self.assertEqual(1, len(landschaft_node))
    self.assertEqual("SubSet", landschaft_node[0].tag)

    vertex_nodes = [n for n in landschaft_node[0] if n.tag == "Vertex"]
    face_nodes = [n for n in landschaft_node[0] if n.tag == "Face"]

    self.assertEqual(24, len(vertex_nodes))
    self.assertEqual(12, len(face_nodes))

  def test_multitexturing(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "multitexturing.blend"))
    self.assert_exported_cube_multitexturing()

  def test_multitexturing_inactive_texture(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "multitexturing_activetextures.blend"))
    self.assert_exported_cube_multitexturing()

  def assert_exported_cube_multitexturing(self, exportargs={}):
    root = self.export_and_parse(exportargs)

    subset_nodes = root.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subset_nodes))
    subset_node = subset_nodes[0]

    # Check that two textures are given.
    textur_nodes = subset_node.findall("./Textur")
    self.assertEqual(2, len(textur_nodes))

    # First texture must be the intransparent one, second texture the transparent one.
    datei1_node = textur_nodes[0].find("./Datei")
    self.assertEqual("texture.dds", datei1_node.attrib["Dateiname"][-len("texture.dds"):])

    datei2_node = textur_nodes[1].find("./Datei")
    self.assertEqual("texture_alpha.dds", datei2_node.attrib["Dateiname"][-len("texture_alpha.dds"):])

    # Check for correct UV coordinates.
    vertex_nodes = [n for n in subset_node if n.tag == "Vertex"]
    face_nodes = [n for n in subset_node if n.tag == "Face"]

    self.assertEqual(24, len(vertex_nodes))
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

  def test_animation_structure_with_constraint(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "animation1.blend"))
    basename, ext, files = self.export_and_parse_multiple(["RadRotation", "Kuppelstange"])

    # Test for correct linked file #1.
    verkn_nodes = files[""].findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verkn_nodes))

    datei_node = verkn_nodes[0].find("./Datei")
    self.assertEqual(basename + "_RadRotation" + ext, datei_node.attrib["Dateiname"])

    # Test for <Animation> node.
    animation_nodes = files[""].findall("./Landschaft/Animation")
    self.assertEqual(1, len(animation_nodes))
    self.assertEqual("2", animation_nodes[0].attrib["AniID"])
    self.assertEqual("Speed (powered, braked)", animation_nodes[0].attrib["AniBeschreibung"])

    # Test for <VerknAnimation> node.
    verkn_animation_nodes = files[""].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    # Test linked file #1.
    # Test for <VerknAnimation> node in linked file #1.
    mesh_animation_nodes = files["RadRotation"].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

    # Test for correct linked file #2.
    verkn_nodes = files["RadRotation"].findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verkn_nodes))

    datei_node = verkn_nodes[0].find("./Datei")
    self.assertEqual(basename + "_Kuppelstange" + ext, datei_node.attrib["Dateiname"])

    # Test linked file #2.
    # Test that no <Animation>, <VerknAnimation> and <MeshAnimation> nodes are present.
    self.assertEqual([], files["Kuppelstange"].findall(".//Animation"))
    self.assertEqual([], files["Kuppelstange"].findall(".//VerknAnimation"))
    self.assertEqual([], files["Kuppelstange"].findall(".//MeshAnimation"))

  def test_animation_with_constraint(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "animation1.blend"))
    basename, ext, files = self.export_and_parse_multiple(["RadRotation", "Kuppelstange"])

    # Check for correct position of linked file #1.
    verknuepfte_node = files[""].find("./Landschaft/Verknuepfte")
    p_node = verknuepfte_node.find("./p")
    self.assertXYZ(p_node, 0, 1, 0)
    self.assertEqual(None, verknuepfte_node.find('sk'))

    # Check for <AniNrs> node in <Animation> node.
    animation_node = files[""].find("./Landschaft/Animation")
    ani_nrs_nodes = animation_node.findall("./AniNrs")
    self.assertEqual(1, len(ani_nrs_nodes))

    ani_nrs_node = ani_nrs_nodes[0]
    self.assertEqual("1", ani_nrs_node.attrib["AniNr"])

    # Check for correct <VerknAnimation> node.
    verkn_animation_node = files[""].find("./Landschaft/VerknAnimation")
    self.assertEqual("1", verkn_animation_node.attrib["AniNr"])

    # Check for keyframes.
    ani_pkt_nodes = verkn_animation_node.findall("./AniPunkt")
    self.assertEqual(5, len(ani_pkt_nodes))

    self.assertAlmostEqual(0.0, float(ani_pkt_nodes[0].attrib["AniZeit"]))
    self.assertAlmostEqual(0.25, float(ani_pkt_nodes[1].attrib["AniZeit"]))
    self.assertAlmostEqual(0.5, float(ani_pkt_nodes[2].attrib["AniZeit"]))
    self.assertAlmostEqual(0.75, float(ani_pkt_nodes[3].attrib["AniZeit"]))
    self.assertAlmostEqual(1.0, float(ani_pkt_nodes[4].attrib["AniZeit"]))

    self.assertEqual([], verkn_animation_node.findall("./AniPunkt/p"))
    q_nodes = verkn_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, 0.707107, 0, 0.707107)
    self.assertRotation(q_nodes[2], 0, 1, 0, 0)
    self.assertRotation(q_nodes[3], 0, 0.707107, 0, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

    # Check linked file #1.
    # Check for correct position and scale of linked file #2.
    verknuepfte_node = files["RadRotation"].find("./Landschaft/Verknuepfte")
    p_node = verknuepfte_node.find("./p")
    self.assertXYZ(p_node, 0, 0, 0.8)
    sk_node = verknuepfte_node.find("./sk")
    self.assertXYZ(sk_node, 0.050899, 0.050899, 0.050899)

    # Check for correct <VerknAnimation> node.
    verkn_animation_node = files["RadRotation"].find("./Landschaft/VerknAnimation")
    self.assertEqual("1", verkn_animation_node.attrib["AniNr"])

    # Check for keyframes.
    ani_pkt_nodes = verkn_animation_node.findall("./AniPunkt")
    self.assertEqual(5, len(ani_pkt_nodes))

    self.assertAlmostEqual(0.0, float(ani_pkt_nodes[0].attrib["AniZeit"]))
    self.assertAlmostEqual(0.25, float(ani_pkt_nodes[1].attrib["AniZeit"]))
    self.assertAlmostEqual(0.5, float(ani_pkt_nodes[2].attrib["AniZeit"]))
    self.assertAlmostEqual(0.75, float(ani_pkt_nodes[3].attrib["AniZeit"]))
    self.assertAlmostEqual(1.0, float(ani_pkt_nodes[4].attrib["AniZeit"]))

    self.assertEqual([], verkn_animation_node.findall("./AniPunkt/p"))
    q_nodes = verkn_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, -0.707107, 0, 0.707107)
    self.assertRotation(q_nodes[2], 0, -1, 0, 0)
    self.assertRotation(q_nodes[3], 0, -0.707107, 0, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

    # Check linked file #2.
    # There should be 4 vertices, all of which have the Y coordinate 0 (because
    # the translation is applied in the parent file's Verknuepfte node) and
    # Z coordinates of -1 or 1 (the object is scaled!)
    vertices = files["Kuppelstange"].findall("./Landschaft/SubSet/Vertex/p")
    self.assertEqual(4, len(vertices))
    for i in range(0, len(vertices)):
      self.assertAlmostEqual(0.0, float(vertices[i].attrib["Y"]),
        places = 5, msg = "Y coordinate of vertex " + str(i))
      self.assertAlmostEqual(1.0, abs(float(vertices[i].attrib["Z"])),
        places = 5, msg = "Z coordinate of vertex " + str(i))

  def test_animation_structure_without_constraint(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "animation2.blend"))
    basename, ext, files = self.export_and_parse_multiple(["RadRotation"])

    verknuepfte_nodes = files[""].findall("./Landschaft/Verknuepfte")
    self.assertEqual(1, len(verknuepfte_nodes))

    verkn_animation_nodes = files[""].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    # The plane should not be in a separate file, as it animates with its parent
    # and has no constraint.
    self.assertEqual([], files["RadRotation"].findall("./Landschaft/Verknuepfte"))
    self.assertEqual([], files["RadRotation"].findall("./Landschaft/VerknAnimation"))
    self.assertEqual([], files["RadRotation"].findall("./Landschaft/MeshAnimation"))

  def test_animation_structure_multiple_actions(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "animation3.blend"))
    basename, ext, files = self.export_and_parse_multiple(["Unterarm", "Oberarm", "Schleifstueck"])

    animation_nodes = files[""].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    animation_nodes = files["Unterarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    animation_nodes = files["Oberarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    self.assertEqual([], files["Schleifstueck"].findall(".//Animation"))

  def test_animation_restore_frame_no(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "animation3.blend"))
    bpy.context.scene.frame_set(5)
    self.assertEqual(5, bpy.context.scene.frame_current)
    self.export()
    self.assertEqual(5, bpy.context.scene.frame_current)

  def test_night_color(self):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", "nightcolor.blend"))
    root = self.export_and_parse()

    subsets = root.findall("./Landschaft/SubSet")
    self.assertEqual(4, len(subsets))

    # Subset 1 has no night color, C (diffuse) is white.
    self.assertEqual("0FFFFFFFF", subsets[0].attrib["C"])
    self.assertNotIn("E", subsets[0].attrib)

    # Subset 2 has a night color of black and a day color of white.
    # It will be black at night and white by day.
    self.assertEqual("0FFFFFFFF", subsets[1].attrib["C"])
    self.assertEqual("000000000", subsets[1].attrib["E"])

    # Subset 3 has a night color of white and a day color of gray.
    # This does not work in Zusi's lighting model (night color must be darker),
    # so we adjust the night color accordingly (to be gray, too).
    self.assertEqual("0FF000000", subsets[2].attrib["C"])
    self.assertEqual("000808080", subsets[2].attrib["E"])

    # Subset 4 allows overexposure and therefore has a (theoretical)
    # day color of RGB(510, 510, 510).
    self.assertEqual("0FFFFFFFF", subsets[3].attrib["C"])
    self.assertEqual("000FFFFFF", subsets[3].attrib["E"])


if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Export)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
