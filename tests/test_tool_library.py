import math
import unittest
from types import SimpleNamespace

import ToolLibrary
from ToolLibrary import DRILL, ENDMILL, VBIT, cut_width, from_mm


class FakeLibrary(ToolLibrary.ToolLibrary):
    """The library's data methods, without its widget."""

    def __init__(self, app):
        self.app = app


def make_library(tools, operations):
    return FakeLibrary(SimpleNamespace(defaults={"cutting_tools": tools,
                                                 "cutting_operations": operations}))


def tool(tool_id, kind, dia, angle=0.0, feed=100.0, depthperpass=0.5):
    return {"id": tool_id, "name": "T%d" % tool_id, "type": kind, "dia": dia, "angle": angle,
            "feed": feed, "spindle": None, "depthperpass": depthperpass}


class ToolLibraryTestCase(unittest.TestCase):

    def test_cut_width(self):
        self.assertEqual(cut_width(tool(1, ENDMILL, 0.8), -1.0), 0.8)
        # 90 degree V-bit: width grows by twice the depth
        self.assertAlmostEqual(cut_width(tool(1, VBIT, 0.1, angle=90.0), -0.2), 0.5)
        self.assertAlmostEqual(cut_width(tool(1, VBIT, 0.1, angle=30.0), -0.1),
                               0.1 + 0.2 * math.tan(math.radians(15)))

    def test_from_mm(self):
        self.assertEqual(from_mm(2.54, "MM"), 2.54)
        self.assertAlmostEqual(from_mm(2.54, "IN"), 0.1)

    def test_isolation_settings(self):
        lib = make_library([tool(1, VBIT, 0.1, angle=90.0, feed=254.0, depthperpass=0.1)],
                           {"isolation": {"tool": 1, "cutz": -0.2},
                            "outline": {"tool": None, "cutz": -1.8},
                            "drilling": {"enabled": False, "cutz": -1.8}})
        iso = lib.isolation_settings("IN")
        self.assertAlmostEqual(iso["dia"], 0.5 / 25.4)
        self.assertAlmostEqual(iso["cutz"], -0.2 / 25.4)
        self.assertAlmostEqual(iso["feedrate"], 10.0)
        self.assertTrue(iso["multidepth"])
        self.assertIsNone(lib.outline_settings("IN"))
        self.assertIsNone(lib.drilling_settings("IN"))

    def test_outline_single_pass(self):
        lib = make_library([tool(3, ENDMILL, 2.0, depthperpass=2.0)],
                           {"isolation": {"tool": None, "cutz": -0.1},
                            "outline": {"tool": 3, "cutz": -1.8},
                            "drilling": {"enabled": True, "cutz": -1.8}})
        self.assertFalse(lib.outline_settings("MM")["multidepth"])

    def test_drilling_settings_and_matching(self):
        lib = make_library([tool(5, DRILL, 1.0), tool(4, DRILL, 0.6), tool(2, ENDMILL, 0.8)],
                           {"isolation": {"tool": None, "cutz": -0.1},
                            "outline": {"tool": None, "cutz": -1.8},
                            "drilling": {"enabled": True, "cutz": -1.8}})
        drilling = lib.drilling_settings("MM")
        self.assertEqual([b["id"] for b in drilling["bits"]], [4, 5])  # drill bits only, by size
        match = ToolLibrary.ToolLibrary.match_drill_bit
        self.assertEqual(match(0.7, drilling["bits"])["id"], 4)
        self.assertEqual(match(0.9, drilling["bits"])["id"], 5)
        self.assertEqual(match(3.0, drilling["bits"])["id"], 5)


class DepthEntryTestCase(unittest.TestCase):

    def setUp(self):
        import sys
        from PyQt6 import QtWidgets
        from FlatCAMApp import App
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.library = self.fc.tool_library
        self.ops = self.fc.defaults["cutting_operations"]

    def type_depth(self, entry, text):
        entry.setText(text)
        entry.editingFinished.emit()
        self.app.processEvents()  # Let the library redisplay its values

    def test_typed_depths_are_stored_as_cut_z(self):
        self.type_depth(self.library.isolation_cutz, "0.15")
        self.assertEqual(self.ops["isolation"]["cutz"], -0.15)
        self.assertEqual(self.library.isolation_cutz.text(), "0.15")

        self.type_depth(self.library.outline_cutz, "-1.6")  # Either sign
        self.assertEqual(self.ops["outline"]["cutz"], -1.6)
        self.assertEqual(self.library.outline_cutz.text(), "1.6")

        self.type_depth(self.library.drilling_cutz, "2")
        self.assertEqual(self.ops["drilling"]["cutz"], -2.0)

    def test_typed_depth_changes_v_bit_cut_width(self):
        self.ops["isolation"]["tool"] = 1  # 30 degree V-bit, 0.1mm tip
        self.type_depth(self.library.isolation_cutz, "0.2")
        width = self.library.isolation_settings("MM")["dia"]
        self.assertAlmostEqual(width, 0.1 + 0.4 * math.tan(math.radians(15)))
        self.assertIn("%.3f" % width, self.library.isolation_width.text())

    def test_invalid_depth_is_rejected(self):
        messages = []
        self.fc.inform.connect(messages.append)
        before = self.ops["isolation"]["cutz"]
        for text in ("abc", "0", ""):
            self.type_depth(self.library.isolation_cutz, text)
            self.assertEqual(self.ops["isolation"]["cutz"], before)
            self.assertEqual(self.library.isolation_cutz.text(), "%g" % abs(before))
        self.assertTrue(any("Invalid isolation depth" in m for m in messages))


if __name__ == '__main__':
    unittest.main()
