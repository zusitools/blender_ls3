import bpy
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

class TestLs3Export(unittest.TestCase):
  def setUp(self):
    bpy.ops.wm.read_homefile()

    self.tempfiles = []

  def tearDown(self):
    for tempfile in self.tempfiles:
      tempfile.close()

  def clear_scene(self):
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

  def export(self):
    context = bpy.context.copy()
    context['selected_objects'] = []

    tempfile_file = tempfile.NamedTemporaryFile(suffix=".ls3")
    self.tempfiles.append(tempfile_file)

    tempfile_path = tempfile_file.name
    (tempfile_dir, tempfile_name) = os.path.split(tempfile_path)

    bpy.ops.io_export_scene.ls3(context,
      filepath=tempfile_path, filename=tempfile_path, directory=tempfile_dir,
      exportSelected="0", optimizeMesh=False)

    return tempfile_file

  def export_and_parse(self):
    exported_file = self.export()
    print(exported_file.read())
    tree = ET.parse(exported_file.name)
    return tree.getroot()

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
    landschaft_node = root.findall("./Landschaft")[0]
    self.assertEqual(1, len(landschaft_node))
    self.assertEqual("SubSet", landschaft_node[0].tag)

    vertex_nodes = [n for n in landschaft_node[0] if n.tag == "Vertex"]
    face_nodes = [n for n in landschaft_node[0] if n.tag == "Face"]

    self.assertEqual(24, len(vertex_nodes))
    self.assertEqual(12, len(face_nodes))

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Export)
  unittest.TextTestRunner(verbosity=2).run(suite)
  #bpy.ops.wm.quit_blender()
