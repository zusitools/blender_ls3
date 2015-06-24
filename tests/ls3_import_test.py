import bpy
from math import radians
import sys
import os
import shutil
import tempfile
import unittest
from math import radians
from mathutils import *

sys.path.append(os.getcwd())
from mocks import MockFS

ZUSI3_DATAPATH = r"Z:\Zusi3\Daten" if sys.platform.startswith("win") else "/mnt/Zusi3/Daten"
ZUSI2_DATAPATH = r"Z:\Zusi2\Daten" if sys.platform.startswith("win") else "/mnt/Zusi2/Daten"
NON_ZUSI_PATH = r"Z:\NichtZusi" if sys.platform.startswith("win") else "/mnt/nichtzusi"

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
    sys.modules["io_scene_ls3.zusiconfig"].datapath = ZUSI3_DATAPATH
    sys.modules["io_scene_ls3.zusiconfig"].z2datapath = ZUSI2_DATAPATH
    sys.modules["io_scene_ls3.zusiconfig"].use_lsb = False

    self._mock_fs = MockFS()
    self._mock_fs.start()

    # Clear scene.
    bpy.ops.wm.read_homefile()
    for ob in bpy.context.scene.objects:
      bpy.context.scene.objects.unlink(ob)
      bpy.data.objects.remove(ob)
    bpy.context.scene.update()

  def tearDown(self):
    self._mock_fs.stop()

  def ls3_import(self, filename, importargs={}):
    bpy.ops.import_scene.ls3(bpy.context.copy(),
      files=[{"name":filename}],
      directory=os.path.join(self._tempdir, "ls3s"),
      **importargs)

  def assertColorEqual(self, expected, actual):
    self.assertAlmostEqual(expected[0], actual.r)
    self.assertAlmostEqual(expected[1], actual.g)
    self.assertAlmostEqual(expected[2], actual.b)

  def assertVectorEqual(self, expected, actual, places = 5):
    expected = Vector(expected)
    self.assertAlmostEqual(expected[0], actual[0], places)
    self.assertAlmostEqual(expected[1], actual[1], places)
    self.assertAlmostEqual(expected[2], actual[2], places)

  def assertKeyframes(self, action, curve_data_path, curve_array_index, keyframes):
    fcurves = [c for c in action.fcurves if c.data_path == curve_data_path and c.array_index == curve_array_index]
    self.assertEqual(1, len(fcurves), "No unique FCurve with datapath %s, index %d exists" % (curve_data_path, curve_array_index))
    fcurve = fcurves[0]

    start = bpy.context.scene.frame_start
    end = bpy.context.scene.frame_end
    self.assertEqual(len(fcurve.keyframe_points), len(keyframes))
    for idx, point in enumerate(fcurve.keyframe_points):
      self.assertEqual("LINEAR", point.interpolation)
      self.assertAlmostEqual(start + keyframes[idx][0] * (end - start), point.co.x, places = 5)
      self.assertAlmostEqual(keyframes[idx][1], point.co.y, places = 5)

  @unittest.skipUnless(bpy.app.version >= (2, 74, 0), "Normal import available in Blender >= 2.74")
  def test_import_normals(self):
    self.ls3_import("custom_normals.ls3")
    ob = bpy.data.objects["custom_normals.ls3.0"]
    me = ob.data
    me.calc_normals_split()

    vertex_normals = [None] * len(me.loops) * 3
    me.loops.foreach_get("normal", vertex_normals)

    for normal in tuple(zip(*(iter(vertex_normals),) * 3)):
      self.assertVectorEqual((1, 0, 0), normal, places = 3) # normals are less accurate

  def test_night_color(self):
    self.ls3_import("nightcolor1.ls3")
    mat = bpy.data.objects["nightcolor1.ls3.0"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)

    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((0.2, 0.2, 0.2), mat.zusi_emit_color)

    self.assertEqual(False, mat.zusi_allow_overexposure)

  def test_overexposure(self):
    self.ls3_import("overexposure.ls3")

    mat = bpy.data.objects["overexposure.ls3.0"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)

    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((1, 1, 1), mat.zusi_emit_color)

    self.assertEqual(True, mat.zusi_allow_overexposure)
    self.assertColorEqual((1, 1, 1), mat.zusi_overexposure_addition)

  def test_ambient_color(self):
    self.ls3_import("ambientcolor.ls3")
    gray = (128.0/255, 128.0/255, 128.0/255)

    mat = bpy.data.objects["ambientcolor.ls3.0"].data.materials[0]
    self.assertEqual(False, mat.zusi_use_emit)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual(gray, mat.zusi_ambient_color)
    self.assertEqual(False, mat.zusi_allow_overexposure)

    mat = bpy.data.objects["ambientcolor.ls3.1"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)
    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual((0, 0, 0), mat.zusi_emit_color)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual((0, 0, 0), mat.zusi_ambient_color)
    self.assertEqual(False, mat.zusi_allow_overexposure)

    mat = bpy.data.objects["ambientcolor.ls3.2"].data.materials[0]
    self.assertColorEqual((1, 1, 1), mat.diffuse_color)
    self.assertEqual(True, mat.zusi_use_emit)
    self.assertColorEqual(gray, mat.zusi_emit_color)
    self.assertEqual(True, mat.zusi_use_ambient)
    self.assertColorEqual((1, 1, 1), mat.zusi_ambient_color)
    self.assertEqual(True, mat.zusi_allow_overexposure)
    self.assertColorEqual((0, 0, 0), mat.zusi_overexposure_addition)
    self.assertColorEqual(gray, mat.zusi_overexposure_addition_ambient)

  def test_color_order(self):
    self.ls3_import("color_order.ls3")
    mat = bpy.data.objects["color_order.ls3.0"].data.materials[0]
    self.assertColorEqual((0x22/0xFF, 0x44/0xFF, 0x66/0xFF), mat.diffuse_color)
    self.assertColorEqual((0x88/0xFF, 0xAA/0xFF, 0xCC/0xFF), mat.zusi_ambient_color)

  def test_zbias(self):
    self.ls3_import("zbias.ls3")
    mat = bpy.data.objects["zbias.ls3.0"].data.materials[0]
    self.assertEqual(-1, mat.offset_z)

  def test_import_multiple_files(self):
    bpy.ops.import_scene.ls3(bpy.context.copy(),
      files=[{"name":"nightcolor1.ls3"}, {"name":"zbias.ls3"}],
      directory=os.path.join(self._tempdir, "ls3s"))
    self.assertIn("nightcolor1.ls3.0", bpy.data.objects)
    self.assertIn("zbias.ls3.0", bpy.data.objects)

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
    self.assertEqual(r"zusi3:Loks\Elektroloks\file.ls3", a1.zusi_anchor_point_files[0].name)
    self.assertEqual(r"zusi3:Loks\Elektroloks", a1.zusi_anchor_point_files[1].name)

    self.assertEqual('EMPTY', a2.type)
    self.assertEqual('ARROWS', a2.empty_draw_type)
    self.assertEqual(True, a2.zusi_is_anchor_point)
    self.assertEqual("0", a2.zusi_anchor_point_category)
    self.assertEqual("0", a2.zusi_anchor_point_type)
    self.assertEqual("Anchor point 2 description", a2.zusi_anchor_point_description)
    self.assertVectorEqual((1.0, 2.0, 3.0), a2.matrix_world.to_translation())
    self.assertVectorEqual((radians(10), radians(20), radians(30)), a2.matrix_world.to_euler())

  def test_import_animated_subset(self):
    self.ls3_import("animated_subset.ls3")

    ob = bpy.data.objects["animated_subset.ls3.0"]
    anim_data = ob.animation_data
    action = ob.animation_data.action

    fcurves = action.fcurves
    self.assertEqual(6, len(fcurves))

    self.assertKeyframes(action, "location", 0, [(0, 0), (1, 0)])
    self.assertKeyframes(action, "location", 1, [(0, 3), (1, -3)])
    self.assertKeyframes(action, "location", 2, [(0, -3), (1, -3)])

    self.assertKeyframes(action, "rotation_euler", 0, [(0, radians(45)), (1, radians(45))])
    self.assertKeyframes(action, "rotation_euler", 1, [(0, radians(0)), (1, radians(0))])
    self.assertKeyframes(action, "rotation_euler", 2, [(0, radians(0)), (1, radians(-45))])

  def test_import_animated_linked_file(self):
    self.ls3_import("animated_linked_file.ls3", {"loadLinkedMode" : "2"})

    ob = bpy.data.objects["animated_linked_file.ls3_animated_linked_file_1.ls3.001"]
    self.assertEqual('EMPTY', ob.type)

    subset = bpy.data.objects["animated_linked_file_1.ls3.0"]
    self.assertEqual('MESH', subset.type)
    self.assertEqual(ob, subset.parent)
    self.assertEqual(None, subset.animation_data)

    anim_data = ob.animation_data
    action = ob.animation_data.action

    fcurves = action.fcurves
    self.assertEqual(6, len(fcurves))

    self.assertKeyframes(action, "location", 0, [(0, 0), (1, 0)])
    self.assertKeyframes(action, "location", 1, [(0, 3), (1, -3)])
    self.assertKeyframes(action, "location", 2, [(0, -3), (1, -3)])

    self.assertKeyframes(action, "rotation_euler", 0, [(0, radians(45)), (1, radians(45))])
    self.assertKeyframes(action, "rotation_euler", 1, [(0, radians(0)), (1, radians(0))])
    self.assertKeyframes(action, "rotation_euler", 2, [(0, radians(0)), (1, radians(-45))])

  def test_import_linked_file_as_empty(self):
    self.ls3_import("linked_file.ls3")

    ob = bpy.data.objects["linked_file.ls3_Blindlok.ls3.001"]
    self.assertEqual('EMPTY', ob.type)
    self.assertEqual(True, ob.zusi_is_linked_file)
    self.assertEqual(r'zusi3:RollingStock\Diverse\Blindlok\Blindlok.ls3', ob.zusi_link_file_name)
    self.assertEqual("TestGroup", ob.zusi_link_group)
    self.assertEqual(1.5, ob.zusi_link_visible_from)
    self.assertEqual(5.5, ob.zusi_link_visible_to)
    self.assertEqual(13.5, ob.zusi_link_preload_factor)
    self.assertEqual(15, ob.zusi_link_radius)
    self.assertEqual(0.5, ob.zusi_link_forced_brightness)
    self.assertEqual(5, ob.zusi_link_lod)
    self.assertEqual(True, ob.zusi_link_is_tile)
    self.assertEqual(False, ob.zusi_link_is_detail_tile)
    self.assertEqual(True, ob.zusi_link_is_billboard)
    self.assertEqual(False, ob.zusi_link_is_readonly)

    ob = bpy.data.objects["linked_file.ls3_101_vr.lod.ls3.002"]
    self.assertEqual('EMPTY', ob.type)
    self.assertEqual(True, ob.zusi_is_linked_file)
    self.assertEqual(r'zusi3:RollingStock\Deutschland\Epoche5\Elektroloks\101\3D-Daten\101_vr.lod.ls3', ob.zusi_link_file_name)
    self.assertEqual("", ob.zusi_link_group)
    self.assertEqual(0, ob.zusi_link_visible_from)
    self.assertEqual(0, ob.zusi_link_visible_to)
    self.assertEqual(0, ob.zusi_link_preload_factor)
    self.assertEqual(0, ob.zusi_link_radius)
    self.assertEqual(0, ob.zusi_link_forced_brightness)
    self.assertEqual(10, ob.zusi_link_lod)
    self.assertEqual(False, ob.zusi_link_is_tile)
    self.assertEqual(True, ob.zusi_link_is_detail_tile)
    self.assertEqual(False, ob.zusi_link_is_billboard)
    self.assertEqual(True, ob.zusi_link_is_readonly)

    self.assertVectorEqual(Vector((2, 1, -3)), ob.location)
    self.assertVectorEqual(Vector((radians(10), radians(20), radians(-30))), ob.rotation_euler)
    self.assertEqual('YXZ', ob.rotation_mode)
    self.assertVectorEqual(Vector((2.5, 1.5, 3.5)), ob.scale)

  def test_import_zusi2_linked_file(self):
    # make sure the file exists (in the mock file system)
    with open(os.path.join(*[ZUSI2_DATAPATH, "Loks", "Elektrotriebwagen", "450", "AVG_803_Front.ls"]), 'w'):
      pass

    self.ls3_import("linked_file_zusi2.ls3")
    ob = bpy.data.objects["linked_file_zusi2.ls3_AVG_803_Front.ls.001"]
    self.assertEqual(True, ob.zusi_is_linked_file)
    self.assertEqual(r'zusi2:Loks\Elektrotriebwagen\450\AVG_803_Front.ls', ob.zusi_link_file_name)

if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(TestLs3Import)
  unittest.TextTestRunner(verbosity=2).run(suite)
  bpy.ops.wm.quit_blender()
