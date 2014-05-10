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

  def open(self, filename):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(self.tempdir, "blends", filename + ".blend"))

  def clear_scene(self):
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

  def export(self, exportargs={}):
    context = bpy.context.copy()
    context['selected_objects'] = []

    tempfile_file = tempfile.NamedTemporaryFile(suffix=exportargs.get("ext", ".ls3"))
    if "ext" in exportargs:
      del exportargs["ext"]
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
    if "exportAnimations" not in exportargs:
      exportargs["exportAnimations"] = True
    mainfile = self.export(exportargs)
    print(mainfile.read())

    (path, name) = os.path.split(mainfile.name)
    (basename, ext) = os.path.splitext(name)

    mainfile_tree = ET.parse(mainfile.name)
    mainfile_root = mainfile_tree.getroot()

    result = {"" : mainfile_root}

    for suffix in additional_suffixes:
      (path, name) = os.path.split(mainfile.name)
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

  def assertRotation(self, node, expected_x, expected_y, expected_z, expected_w):
    self.assertXYZ(node, expected_x, expected_y, expected_z)
    if expected_w != 0.0 or "W" in node.attrib:
      self.assertAlmostEqual(expected_w, float(node.attrib["W"]), places = 5)

  def assertXYZ(self, node, expected_x, expected_y, expected_z, msg = None):
    if expected_x != 0.0 or "X" in node.attrib:
      self.assertAlmostEqual(expected_x, float(node.attrib["X"]), places = 5, msg = msg)
    if expected_y != 0.0 or "Y" in node.attrib:
      self.assertAlmostEqual(expected_y, float(node.attrib["Y"]), places = 5, msg = msg)
    if expected_z != 0.0 or "Z" in node.attrib:
      self.assertAlmostEqual(expected_z, float(node.attrib["Z"]), places = 5, msg = msg)

  def assertKeyframes(self, node, keyframe_times):
    keyframes = node.findall("AniPunkt")
    self.assertEqual(len(keyframe_times), len(keyframes))
    for idx, keyframe_time in enumerate(keyframe_times):
      self.assertAlmostEqual(keyframe_time, float(keyframes[idx].attrib["AniZeit"]))

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
    self.open("multitexturing")
    self.assert_exported_cube_multitexturing()

  def test_multitexturing_inactive_texture(self):
    self.open("multitexturing_activetextures")
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

  def test_variants(self):
    self.open("variants")
    root = self.export_and_parse()

  def test_animation_structure_with_constraint(self):
    self.open("animation1")
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
    self.assertEqual("Speed (powered, braked)", animation_nodes[0].attrib["AniBeschreibung"])

    # Test for <VerknAnimation> node.
    verkn_animation_nodes = files[""].findall("./Landschaft/VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))

    # Test linked file #1.
    # Test for <MeshAnimation> node in linked file #1.
    mesh_animation_nodes = files["RadRotation"].findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))

    # No further linked file #2.
    self.assertEqual([], files["RadRotation"].findall("./Landschaft/Verknuepfte"))

  def test_animation_with_constraint(self):
    self.open("animation1")
    basename, ext, files = self.export_and_parse_multiple(["RadRotation"])

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
    self.assertKeyframes(verkn_animation_node, [0, 0.25, 0.5, 0.75, 1.0])
    self.assertEqual([], verkn_animation_node.findall("./AniPunkt/p"))
    q_nodes = verkn_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, 0.707107, 0, 0.707107)
    self.assertRotation(q_nodes[2], 0, 1, 0, 0)
    self.assertRotation(q_nodes[3], 0, 0.707107, 0, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

    # Check linked file #1.
    # Check for correct <VerknAnimation> node.
    mesh_animation_node = files["RadRotation"].find("./Landschaft/MeshAnimation")
    self.assertEqual("1", mesh_animation_node.attrib["AniNr"])

    # Check for keyframes.
    self.assertKeyframes(mesh_animation_node, [0.0, 0.25, 0.5, 0.75, 1.0])

    p_nodes = mesh_animation_node.findall("./AniPunkt/p")
    self.assertEqual(5, len(p_nodes))
    for i in range(0, 5):
      self.assertXYZ(p_nodes[i], 0, 0, 0.8, msg = "p node " + str(i))

    q_nodes = mesh_animation_node.findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, -0.707107, 0, 0.707107)
    self.assertRotation(q_nodes[2], 0, -1, 0, 0)
    self.assertRotation(q_nodes[3], 0, -0.707107, 0, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

    # Check subset.
    # There should be 4 vertices, all of which have the Y coordinate 0 (because
    # the translation is applied in the parent file's Verknuepfte node) and
    # Z coordinates between -0.1 and 0.1 (the object's scale is applied!)
    vertices = files["RadRotation"].findall("./Landschaft/SubSet/Vertex/p")
    self.assertEqual(4, len(vertices))
    for i in range(0, len(vertices)):
      self.assertAlmostEqual(0.0, float(vertices[i].attrib["Y"]),
        places = 5, msg = "Y coordinate of vertex " + str(i))
      self.assertLess(abs(float(vertices[i].attrib["Z"])), 0.1,
        msg = "Z coordinate of vertex " + str(i))

  def test_animation_structure_without_constraint(self):
    self.open("animation2")
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
    self.open("animation3")
    basename, ext, files = self.export_and_parse_multiple(["Unterarm", "Oberarm"])

    # Test animation of linked file "Unterarm" in main file.
    animation_nodes = files[""].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    aninrs_nodes = animation_nodes[0].findall("./AniNrs")
    self.assertEqual(1, len(aninrs_nodes))
    self.assertEqual("1", aninrs_nodes[0].attrib["AniNr"])

    self.assertEqual([], files[""].findall(".//MeshAnimation"))
    verkn_animation_nodes = files[""].findall(".//VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))
    self.assertEqual("1", verkn_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniIndex"])

    # Test animation of linked file "Oberarm" in file "Unterarm"
    animation_nodes = files["Unterarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    aninrs_nodes = animation_nodes[0].findall("./AniNrs")
    self.assertEqual(1, len(aninrs_nodes))
    self.assertEqual("1", aninrs_nodes[0].attrib["AniNr"])

    self.assertEqual([], files["Unterarm"].findall(".//MeshAnimation"))
    verkn_animation_nodes = files["Unterarm"].findall(".//VerknAnimation")
    self.assertEqual(1, len(verkn_animation_nodes))
    self.assertEqual("1", verkn_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("0", verkn_animation_nodes[0].attrib["AniIndex"])

    # Test animation of subset "Schleifstueck" in file "Oberarm"
    animation_nodes = files["Oberarm"].findall(".//Animation")
    self.assertEqual(1, len(animation_nodes))

    aninrs_nodes = animation_nodes[0].findall("./AniNrs")
    self.assertEqual(1, len(aninrs_nodes))
    self.assertEqual("2", aninrs_nodes[0].attrib["AniNr"])

    self.assertEqual([], files["Oberarm"].findall(".//VerknAnimation"))
    mesh_animation_nodes = files["Oberarm"].findall(".//MeshAnimation")
    self.assertEqual(1, len(mesh_animation_nodes))
    self.assertEqual("2", mesh_animation_nodes[0].attrib["AniNr"])
    self.assertEqual("1", mesh_animation_nodes[0].attrib["AniIndex"])

  def test_subset_animation_rotation(self):
    self.open("animation4")
    mainfile = self.export_and_parse({"exportAnimations":True})

    self.assertEqual([], mainfile.findall("./Landschaft/Verknuepfte"))
    self.assertEqual([], mainfile.findall("./Landschaft/VerknAnimation"))

    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual(2, len(subsets))

    animationNodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animationNodes))

    aniNrsNodes = animationNodes[0].findall("./AniNrs")
    self.assertEqual(1, len(aniNrsNodes))

    # AniNr should be 2 as the second subset is animated (the first subset is not,
    # but we skip it nonetheless in the animation indexing).
    self.assertEqual("2", aniNrsNodes[0].attrib["AniNr"])

    meshAnimationNodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(meshAnimationNodes))
    self.assertEqual("2", meshAnimationNodes[0].attrib["AniNr"])

    self.assertKeyframes(meshAnimationNodes[0], [0.0, 0.25, 0.5, 0.75, 1.0])
    self.assertEqual([], meshAnimationNodes[0].findall("./AniPunkt/p"))
    q_nodes = meshAnimationNodes[0].findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, 0, 0.707107, 0.707107)
    self.assertRotation(q_nodes[2], 0, 0, 1, 0)
    self.assertRotation(q_nodes[3], 0, 0, 0.707107, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

  def test_subset_animation_rotation_with_offset(self):
    self.open("animation5")
    mainfile = self.export_and_parse({"exportAnimations":True})

    self.assertEqual([], mainfile.findall("./Landschaft/Verknuepfte"))
    self.assertEqual([], mainfile.findall("./Landschaft/VerknAnimation"))

    subsets = mainfile.findall("./Landschaft/SubSet")
    self.assertEqual(1, len(subsets))

    animationNodes = mainfile.findall("./Landschaft/Animation")
    self.assertEqual(1, len(animationNodes))

    aniNrsNodes = animationNodes[0].findall("./AniNrs")
    self.assertEqual(1, len(aniNrsNodes))
    self.assertEqual("1", aniNrsNodes[0].attrib["AniNr"])

    meshAnimationNodes = mainfile.findall("./Landschaft/MeshAnimation")
    self.assertEqual(1, len(meshAnimationNodes))
    self.assertEqual("1", meshAnimationNodes[0].attrib["AniNr"])

    self.assertKeyframes(meshAnimationNodes[0], [0.0, 0.25, 0.5, 0.75, 1.0])

    p_nodes = meshAnimationNodes[0].findall("./AniPunkt/p")
    self.assertEqual(5, len(p_nodes))
    for i in range(0, 5):
      self.assertXYZ(p_nodes[i], -3, 2, 4, msg = "p node " + str(i))

    q_nodes = meshAnimationNodes[0].findall("./AniPunkt/q")
    self.assertEqual(5, len(q_nodes))

    self.assertRotation(q_nodes[0], 0, 0, 0, 1)
    self.assertRotation(q_nodes[1], 0, 0, 0.707107, 0.707107)
    self.assertRotation(q_nodes[2], 0, 0, 1, 0)
    self.assertRotation(q_nodes[3], 0, 0, 0.707107, -0.707107)
    self.assertRotation(q_nodes[4], 0, 0, 0, -1)

  def test_scaled_nonanimated_subset(self):
    self.open("animation7")
    files = self.export_and_parse_multiple(["Cube"])[2]

    # Check that the <Verknuepfte> node has correct scaling.
    verknuepfte_node = files[""].find("./Landschaft/Verknuepfte")
    sk_node = verknuepfte_node.find("./sk")
    self.assertXYZ(sk_node, 0.5, 0.5, 0.5)

    # Check that the animated subset in the linked file has its scaling
    # applied (relative to the parent subset) and the non-animated subset has not
    # (the scale is contained in the <Verknuepfte> node).
    mesh_animation_node = files["Cube"].find("./Landschaft/MeshAnimation")
    animated_subset_index = int(mesh_animation_node.attrib["AniIndex"])

    subsets = files["Cube"].findall("./Landschaft/SubSet")
    animated_subset = subsets[animated_subset_index]
    nonanimated_subset = subsets[(animated_subset_index + 1) % 2]

    vertices = animated_subset.findall("./Vertex/p")
    self.assertEqual(24, len(vertices))
    for i in range(0, 24):
      self.assertAlmostEqual(0.5, abs(float(vertices[i].attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.5, abs(float(vertices[i].attrib["Z"])), places = 5)

    vertices = nonanimated_subset.findall("./Vertex/p")
    self.assertEqual(24, len(vertices))
    for i in range(0, 24):
      self.assertAlmostEqual(1.0, abs(float(vertices[i].attrib["Y"])), places = 5)
      self.assertAlmostEqual(1.0, abs(float(vertices[i].attrib["Z"])), places = 5)

  def test_scaled_nonanimated_subset_without_animation(self):
    self.open("animation7")
    mainfile = self.export_and_parse()

    subsets = mainfile.findall("./Landschaft/SubSet")

    vertices = subsets[0].findall("./Vertex/p")
    self.assertEqual(24, len(vertices))
    for i in range(0, 24):
      # X coordinate between 2.5 and 3.5.
      self.assertLess(abs(float(vertices[i].attrib["X"]) - 3), 1.01)
      self.assertAlmostEqual(0.5, abs(float(vertices[i].attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.5, abs(float(vertices[i].attrib["Z"])), places = 5)

    vertices = subsets[1].findall("./Vertex/p")
    self.assertEqual(24, len(vertices))
    for i in range(0, 24):
      # X coordinate between 5.75 and 6.25
      self.assertLess(abs(float(vertices[i].attrib["X"]) - 6), 0.51)
      self.assertAlmostEqual(0.25, abs(float(vertices[i].attrib["Y"])), places = 5)
      self.assertAlmostEqual(0.25, abs(float(vertices[i].attrib["Z"])), places = 5)

  def test_animation_restore_frame_no(self):
    self.open("animation3")
    bpy.context.scene.frame_set(5)
    self.assertEqual(5, bpy.context.scene.frame_current)
    self.export()
    self.assertEqual(5, bpy.context.scene.frame_current)

  def test_night_color(self):
    self.open("nightcolor")
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

  def test_lod_suffix(self):
    self.open("animation2")
    mainfile = self.export({"ext" : ".lod1.ls3", "exportAnimations" : True})

    path, name = os.path.split(mainfile.name)
    basename, ext = name.split(os.extsep, 1)

    self.assertTrue(os.path.exists(os.path.join(path, basename + "_RadRotation.lod1.ls3")))

  def test_no_extension(self):
    self.open("animation2")
    mainfile = self.export({"ext" : "", "exportAnimations" : True})
    self.assertTrue(os.path.exists(mainfile.name + "_RadRotation"))

  def test_animation_range_extends_scene_range(self):
    self.open("animation6")
    mainfile = self.export_and_parse({"exportAnimations" : True})
    mesh_animation_node = mainfile.find("./Landschaft/MeshAnimation")
    self.assertKeyframes(mesh_animation_node, [0, 1, 2])

  def test_dont_export_animation(self):
    self.open("animation3")
    mainfile = self.export_and_parse({"exportAnimations" : False})
    self.assertEqual([], mainfile.findall(".//Verknuepfte"))
    self.assertEqual([], mainfile.findall(".//VerknAnimation"))
    self.assertEqual([], mainfile.findall(".//MeshAnimation"))
    self.assertEqual([], mainfile.findall(".//Animation"))

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Export)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
