# coding=utf-8

import os
import sys
import unittest

import bpy

class TestLs3Ui(unittest.TestCase):
  def setUp(self):
    # Check that we are testing the right file
    io_scene_ls3_module_file = sys.modules["io_scene_ls3"].__file__
    expected_module_file = os.path.join(os.path.dirname(sys.modules[self.__module__].__file__), os.pardir, '__init__.py')
    assert os.path.samefile(io_scene_ls3_module_file, expected_module_file), \
        "Expected to test {}, but got {}".format(expected_module_file, io_scene_ls3_module_file)

    bpy.ops.wm.read_homefile()

  def open(self, filename):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(os.getcwd(), "blends", filename + ".blend"))

  def clear_scene(self):
    for ob in bpy.context.scene.objects:
      bpy.data.objects.remove(ob)
    bpy.context.view_layer.update()

  # ---
  # TESTS START HERE
  # ---

  def test_add_variants(self):
    self.open("variants")
    
    self.assertEqual(2, len(bpy.data.scenes["Scene"].zusi_variants))
    self.assertEqual(1, len(bpy.data.objects["Object.000"].zusi_variants_visibility))  # Nur in den ausgewählten Varianten sichtbar
    self.assertEqual(0, len(bpy.data.objects["Object.001"].zusi_variants_visibility))  # In allen Varianten sichtbar
    self.assertEqual(1, len(bpy.data.objects["Object.002"].zusi_variants_visibility))  # In allen außer den ausgewählten Varianten sichtbar
    self.assertEqual(2, len(bpy.data.objects["Object.003"].zusi_variants_visibility))  # Nur in den ausgewählten Varianten sichtbar
    self.assertEqual(1, len(bpy.data.objects["Object.Linked"].zusi_variants_visibility))  # Nur in den ausgewählten Varianten sichtbar

    bpy.ops.zusi_variants.add()
    
    self.assertEqual(3, len(bpy.data.scenes["Scene"].zusi_variants))
    self.assertEqual(2, bpy.data.scenes["Scene"].zusi_variants[2].id)

    self.assertEqual(1, len(bpy.data.objects["Object.000"].zusi_variants_visibility))  # unchanged
    self.assertEqual(0, len(bpy.data.objects["Object.001"].zusi_variants_visibility))  # unchanged
    self.assertEqual(2, len(bpy.data.objects["Object.002"].zusi_variants_visibility))
    self.assertEqual(2, bpy.data.objects["Object.002"].zusi_variants_visibility[1].variant_id)
    self.assertEqual(2, len(bpy.data.objects["Object.003"].zusi_variants_visibility))  # unchanged
    self.assertEqual(1, len(bpy.data.objects["Object.Linked"].zusi_variants_visibility))  # unchanged -- linked object is not modifiable

if __name__ == '__main__':
  try:
    # Arguments passed after "--" are not parsed by Blender.
    argv = sys.argv[sys.argv.index("--") + 1:]
  except ValueError:
    argv = []
  unittest.main(argv=['ls3_export_test.py'] + argv, verbosity=2)
  bpy.ops.wm.quit_blender()
