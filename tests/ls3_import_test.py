import bpy
import os
import shutil
import tempfile
import unittest

class TestLs3Import(unittest.TestCase):
  def setUp(self):
    bpy.ops.wm.read_homefile()
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

    # Copy test LS3 files into temporary directory.
    self.tempdir = tempfile.mkdtemp()
    shutil.copytree("ls3s", os.path.join(self.tempdir, "ls3s"))

  def tearDown(self):
    shutil.rmtree(self.tempdir)

  def ls3_import(self, filename, importargs={}):
    bpy.ops.io_import_scene.ls3(bpy.context.copy(),
      filepath=os.path.join(self.tempdir, "ls3s", filename),
      filename=filename,
      directory=os.path.join(self.tempdir, "ls3s"),
      **importargs)

  def test_night_color(self):
    self.ls3_import("nightcolor1.ls3")
    mat = bpy.data.objects["nightcolor1.ls3.1"].data.materials[0]
    self.assertAlmostEqual(1.0, mat.diffuse_color.r)
    self.assertAlmostEqual(1.0, mat.diffuse_color.g)
    self.assertAlmostEqual(1.0, mat.diffuse_color.b)
    self.assertEqual(True, mat.zusi_use_emit)
    self.assertAlmostEqual(0.2, mat.zusi_emit_color.r)
    self.assertAlmostEqual(0.2, mat.zusi_emit_color.g)
    self.assertAlmostEqual(0.2, mat.zusi_emit_color.b)

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Import)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
