import bpy
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

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
    bpy.ops.io_import_scene.ls3(bpy.context,
      filepath=os.path.join(self.tempdir, "ls3s", filename),
      filename=filename,
      directory=os.path.join(self.tempdir, "ls3s"),
      **exportargs)

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Import)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
