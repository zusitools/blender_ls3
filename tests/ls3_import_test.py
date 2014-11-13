import bpy
import os
import shutil
import tempfile
import unittest
from math import radians
from mathutils import *

class TestLs3Import(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    # Copy test LS3 files into temporary directory.
    cls._tempdir = tempfile.mkdtemp()
    shutil.copytree("ls3s", os.path.join(cls._tempdir, "ls3s"))

  @classmethod
  def tearDownClass(cls):
    shutil.rmtree(cls._tempdir)

  def setUp(self):
    # Clear scene.
    bpy.ops.wm.read_homefile()
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

  def ls3_import(self, filename, importargs={}):
    bpy.ops.import_scene.ls3(bpy.context.copy(),
      files=[{"name":filename}],
      directory=os.path.join(self._tempdir, "ls3s"),
      **importargs)

  def assertColorEqual(self, expected, actual):
    self.assertAlmostEqual(expected[0], actual.r)
    self.assertAlmostEqual(expected[1], actual.g)
    self.assertAlmostEqual(expected[2], actual.b)

  def assertVectorEqual(self, expected, actual):
    expected = Vector(expected)
    self.assertAlmostEqual(expected[0], actual[0], 5)
    self.assertAlmostEqual(expected[1], actual[1], 5)
    self.assertAlmostEqual(expected[2], actual[2], 5)

  def test_night_color(self):
    self.ls3_import("nightcolor1.ls3")
    mat = bpy.data.objects["nightcolor1.ls3.1"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)

    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((0.2, 0.2, 0.2), mat.zusi_emit_color)

    self.assertEqual(False, mat.zusi_allow_overexposure)

  def test_overexposure(self):
    self.ls3_import("overexposure.ls3")

    mat = bpy.data.objects["overexposure.ls3.1"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)

    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((1, 1, 1), mat.zusi_emit_color)

    self.assertEqual(True, mat.zusi_allow_overexposure)
    self.assertColorEqual((1, 1, 1), mat.zusi_overexposure_addition)

  def test_ambient_color(self):
    self.ls3_import("ambientcolor.ls3")
    gray = (128.0/255, 128.0/255, 128.0/255)

    mat = bpy.data.objects["ambientcolor.ls3.1"].data.materials[0]
    self.assertEqual(False, mat.zusi_use_emit)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual(gray, mat.zusi_ambient_color)
    self.assertEqual(False, mat.zusi_allow_overexposure)

    mat = bpy.data.objects["ambientcolor.ls3.2"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)
    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((0, 0, 0), mat.zusi_emit_color)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual((0, 0, 0), mat.zusi_ambient_color)
    self.assertEqual(False, mat.zusi_allow_overexposure)

    mat = bpy.data.objects["ambientcolor.ls3.3"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)
    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual(gray, mat.zusi_emit_color)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual((1, 1, 1), mat.zusi_ambient_color)
    self.assertEqual(True, mat.zusi_allow_overexposure)
    self.assertColorEqual((0, 0, 0), mat.zusi_overexposure_addition)
    self.assertColorEqual(gray, mat.zusi_overexposure_addition_ambient)

  def test_zbias(self):
    self.ls3_import("zbias.ls3")
    mat = bpy.data.objects["zbias.ls3.1"].data.materials[0]
    self.assertEqual(-1, mat.offset_z)

  def test_import_multiple_files(self):
    bpy.ops.import_scene.ls3(bpy.context.copy(),
      files=[{"name":"nightcolor1.ls3"}, {"name":"zbias.ls3"}],
      directory=os.path.join(self._tempdir, "ls3s"))
    self.assertIn("nightcolor1.ls3.1", bpy.data.objects)
    self.assertIn("zbias.ls3.1", bpy.data.objects)

  def test_anchor_points(self):
    self.ls3_import("anchor_points.ls3")
    a1 = bpy.data.objects["anchor_points.ls3_AnchorPoint.001"]
    a2 = bpy.data.objects["anchor_points.ls3_AnchorPoint.002"]

    self.assertEqual('EMPTY', a1.type)
    self.assertEqual('ARROWS', a1.empty_draw_type)
    self.assertEqual(True, a1.zusi_is_anchor_point)
    self.assertEqual("1", a1.zusi_anchor_point_category)
    self.assertEqual("2", a1.zusi_anchor_point_type)
    self.assertEqual("Anchor point 1 description", a1.zusi_anchor_point_description)
    self.assertVectorEqual((0.0, 0.0, 0.0), a1.matrix_world.to_translation())
    self.assertVectorEqual((0.0, 0.0, 0.0), a1.matrix_world.to_euler())

    self.assertEqual(2, len(a1.zusi_anchor_point_files))
    self.assertEqual("file.ls3", a1.zusi_anchor_point_files[0].name[-len("file.ls3"):])
    self.assertEqual("folder", a1.zusi_anchor_point_files[1].name[-len("folder"):])

    self.assertEqual('EMPTY', a2.type)
    self.assertEqual('ARROWS', a1.empty_draw_type)
    self.assertEqual(True, a2.zusi_is_anchor_point)
    self.assertEqual("0", a2.zusi_anchor_point_category)
    self.assertEqual("0", a2.zusi_anchor_point_type)
    self.assertEqual("Anchor point 2 description", a2.zusi_anchor_point_description)
    self.assertVectorEqual((1.0, 2.0, 3.0), a2.matrix_world.to_translation())
    self.assertVectorEqual((radians(10), radians(20), radians(30)), a2.matrix_world.to_euler())

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Import)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
