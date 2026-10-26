import os
import sys
import tempfile
import unittest

from PyQt6 import QtCore, QtWidgets

from FlatCAMApp import App

# Two drill files in the style of DesignSpark's plated and unplated output.
# Both number their smallest drill T1, with different sizes, and both have
# a 0.020" tool. One 0.020" hole is in both files.
PLATED = """M48
INCH,TZ
T1C000.01600
T2C000.02000
%
T001
X1.00000Y1.00000
X1.10000Y1.00000
T002
X2.00000Y2.00000
M30
"""

UNPLATED = """M48
INCH,TZ
T1C000.01500
T2C000.02000
T3C000.03100
%
T001
X3.00000Y3.00000
T002
X2.00000Y2.00000
X2.50000Y2.00000
T003
X4.00000Y4.00000
M30
"""


def holes_by_size(obj):
    """{diameter: sorted [(x, y)]} of an Excellon object."""
    result = {}
    for drill in obj.drills:
        dia = round(obj.tools[drill["tool"]]["C"], 6)
        result.setdefault(dia, []).append((round(drill["point"].x, 6), round(drill["point"].y, 6)))
    return {dia: sorted(points) for dia, points in result.items()}


class ExcellonJoinTestCase(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.fc.options["units"] = "IN"
        self.tmpdir = tempfile.mkdtemp()
        for name, text in (("plated.drl", PLATED), ("unplated.drl", UNPLATED)):
            with open(os.path.join(self.tmpdir, name), "w") as f:
                f.write(text)
            self.fc.open_excellon(os.path.join(self.tmpdir, name))

    def tearDown(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def join(self):
        view = self.fc.collection.view
        view.selectAll()
        self.fc.on_edit_join_excellon()
        return self.fc.collection.get_by_name("Joined drills")

    def test_join_groups_holes_by_size(self):
        joined = self.join()
        self.assertIsNotNone(joined)

        # One tool per size, numbered by size
        self.assertEqual({t: round(v["C"], 6) for t, v in joined.tools.items()},
                         {"1": 0.015, "2": 0.016, "3": 0.020, "4": 0.031})

        # Every hole kept at its own size (T1 of each file is a different
        # drill), and the hole in both files only once
        self.assertEqual(holes_by_size(joined), {
            0.015: [(3.0, 3.0)],
            0.016: [(1.0, 1.0), (1.1, 1.0)],
            0.020: [(2.0, 2.0), (2.5, 2.0)],
            0.031: [(4.0, 4.0)],
        })

    def test_join_needs_two_excellon_objects(self):
        messages = []
        self.fc.inform.connect(messages.append)
        self.fc.collection.set_all_inactive()
        self.fc.collection.set_active("plated.drl")
        self.assertEqual(len(self.fc.collection.get_selected()), 1)
        self.fc.on_edit_join_excellon()
        self.assertIsNone(self.fc.collection.get_by_name("Joined drills"))
        self.assertTrue(any("two or more" in m for m in messages))

    def test_export_groups_by_tool_and_reads_back(self):
        joined = self.join()
        path = os.path.join(self.tmpdir, "joined.drl")
        self.fc.export_excellon(joined.options["name"], path)

        with open(path) as f:
            body = f.read().split("%", 1)[1]
        # Each tool is selected once, holes following it, in order of size
        selections = [line for line in body.splitlines() if line.startswith("T")]
        self.assertEqual(selections, ["T1", "T2", "T3", "T4", "T0"])

        self.fc.open_excellon(path)
        reread = self.fc.collection.get_by_name("joined.drl")
        self.assertEqual(holes_by_size(reread), holes_by_size(joined))

    def test_join_converts_units(self):
        metric = os.path.join(self.tmpdir, "metric.drl")
        with open(metric, "w") as f:
            f.write("M48\nMETRIC,TZ\nT1C0.508\n%\nT01\nX25.400Y25.400\nM30\n")
        self.fc.open_excellon(metric)  # Converted to the project's inches on opening
        joined = self.join()
        self.assertIn((1.0, 1.0), holes_by_size(joined)[0.020])


if __name__ == '__main__':
    unittest.main()
