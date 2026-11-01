"""
Plunge feed rates and how jobs end, in the generated G-code.
"""

import math
import re
import sys
import time
import unittest

from PyQt6 import QtWidgets
from shapely.geometry import LineString, Point

from FlatCAMApp import App

INCH = 25.4


def lines(gcode):
    return [l.strip() for l in gcode.splitlines() if l.strip()]


class GCodeMotionTestCase(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.library = self.fc.tool_library
        # Isolate with the 0.8mm end mill: feed 200, plunge 60 mm/min
        self.tool = self.library.get_tool(2)
        self.tool["feed"], self.tool["plunge"] = 200.0, 60.0
        self.fc.defaults["cutting_operations"]["isolation"]["tool"] = 2
        self.fc.open_gerber('tests/gerber_files/simple1.gbr')
        self.gerber = self.fc.collection.get_by_name('simple1.gbr')

    def wait_for(self, name, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            obj = self.fc.collection.get_by_name(name)
            if obj is not None:
                return obj
            time.sleep(0.05)
        self.fail("%s was not created" % name)

    def isolation_gcode(self, **options):
        """G-code of the isolation, with ``options`` changed on its geometry."""
        self.gerber.isolate(passes=1, combine=True)
        geo = self.wait_for('simple1.gbr_iso')
        geo.options.update(options)
        geo.generatecncjob()
        return lines(self.wait_for('simple1.gbr_iso_cnc').gcode)

    def test_plunges_at_plunge_rate_and_cuts_at_feed_rate(self):
        gcode = self.isolation_gcode()
        plunge = "F%.2f" % (60.0 / INCH)
        feed = "F%.2f" % (200.0 / INCH)
        plunges = [i for i, l in enumerate(gcode) if re.match(r'G01 Z-', l)]
        self.assertTrue(plunges)
        for i in plunges:
            self.assertEqual(gcode[i - 1], plunge, "plunge not slowed at line %d" % i)
            self.assertEqual(gcode[i + 1], feed, "feed not restored at line %d" % i)

    def test_job_ends_lifted_before_returning(self):
        self.fc.defaults["cutting_job_end"].update(z_end=15.0, return_to_origin=True)
        gcode = self.isolation_gcode()
        self.assertEqual(gcode[-3:], ["G00 Z%.4f" % (15.0 / INCH), "M05", "G00 X0.0000 Y0.0000"])

    def test_job_can_end_without_returning(self):
        self.fc.defaults["cutting_job_end"].update(z_end=10.0, return_to_origin=False)
        gcode = self.isolation_gcode()
        self.assertEqual(gcode[-2:], ["G00 Z%.4f" % (10.0 / INCH), "M05"])

    def test_end_height_never_below_travel_height(self):
        self.fc.defaults["cutting_job_end"].update(z_end=0.01, return_to_origin=True)
        gcode = self.isolation_gcode()
        travel = self.fc.collection.get_by_name('simple1.gbr_iso').options["travelz"]
        self.assertEqual(gcode[-3], "G00 Z%.4f" % travel)

    def cuts(self, gcode):
        """(start, end) of every XY move made at cutting depth."""
        moves = []
        x = y = z = 0.0
        for line in gcode:
            words = dict((k, float(v)) for k, v in re.findall(r'([GXYZ])(-?[\d.]+)', line))
            nx, ny, z = words.get('X', x), words.get('Y', y), words.get('Z', z)
            if words.get('G') == 1 and z < 0 and ('X' in words or 'Y' in words):
                moves.append(((x, y), (nx, ny)))
            x, y = nx, ny
        return moves

    def longest(self, gcode):
        return max(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in self.cuts(gcode))

    def regenerate(self, **options):
        """Starts over and returns the isolation G-code with ``options``."""
        self.fc.collection.delete_all()
        self.fc.open_gerber('tests/gerber_files/simple1.gbr')
        self.gerber = self.fc.collection.get_by_name('simple1.gbr')
        return self.isolation_gcode(**options)

    def test_new_geometry_splits_as_set_in_tool_tab(self):
        self.fc.defaults["cutting_job_end"].update(split=True, segment_length=3.0)
        self.gerber.isolate(passes=1, combine=True)
        geo = self.wait_for('simple1.gbr_iso')
        self.assertTrue(geo.options["segmented"])
        self.assertAlmostEqual(geo.options["segmentlength"], 3.0 / INCH)

        self.fc.defaults["cutting_job_end"]["split"] = False
        self.gerber.isolate(passes=1, combine=True, outname='unsplit_iso')
        self.assertFalse(self.wait_for('unsplit_iso').options["segmented"])

    def test_long_cuts_are_split_for_height_maps(self):
        split = self.isolation_gcode(segmented=True, segmentlength=2.0 / INCH)
        # Rounded to 4 decimals of an inch in the G-code
        self.assertLessEqual(self.longest(split), 2.0 / INCH + 2e-4)
        # The board's long edges did need splitting
        unsplit = self.regenerate(segmented=False)
        self.assertGreater(self.longest(unsplit), 2.0 / INCH + 2e-4)
        self.assertGreater(len(self.cuts(split)), len(self.cuts(unsplit)))

    def test_split_length_is_per_object(self):
        gcode = self.isolation_gcode(segmented=True, segmentlength=0.5 / INCH)
        self.assertLessEqual(self.longest(gcode), 0.5 / INCH + 2e-4)

    def test_invalid_split_length_leaves_cuts_whole(self):
        messages = []
        self.fc.inform.connect(messages.append)
        gcode = self.isolation_gcode(segmented=True, segmentlength=0.0)
        unsplit = self.regenerate(segmented=False)
        self.assertEqual(self.cuts(gcode), self.cuts(unsplit))
        self.assertTrue(any("Max cut length" in m for m in messages))

    def test_split_cuts_follow_the_same_path(self):
        split = self.isolation_gcode(segmented=True, segmentlength=2.0 / INCH)
        path = LineString([b for a, b in self.cuts(split)])
        for a, b in self.cuts(self.regenerate(segmented=False)):
            self.assertLess(path.distance(Point(b)), 2e-4)

    def test_selected_tab_controls_split(self):
        self.gerber.isolate(passes=1, combine=True)
        geo = self.wait_for('simple1.gbr_iso')
        self.fc.collection.set_all_inactive()
        self.fc.collection.set_active('simple1.gbr_iso')
        self.app.processEvents()
        ui = geo.ui
        self.assertTrue(ui.segmented_cb.isChecked())  # The Tool tab's default
        ui.segmentlength_entry.set_value(1.0 / INCH)
        ui.segmented_cb.set_value(True)
        geo.on_generatecnc_button_click()
        gcode = lines(self.wait_for('simple1.gbr_iso_cnc').gcode)
        self.assertLessEqual(self.longest(gcode), 1.0 / INCH + 2e-4)

        ui.segmented_cb.set_value(False)
        self.assertFalse(ui.segmentlength_entry.isEnabled())
        geo.on_generatecnc_button_click()
        self.assertFalse(geo.options["segmented"])

    def test_coordinates_are_separated(self):
        gcode = self.isolation_gcode()
        xy = [l for l in gcode if 'X' in l]
        self.assertTrue(xy)
        for line in xy:
            self.assertRegex(line, r'^G0[01] X-?[\d.]+ Y-?[\d.]+$')

    def test_settings_saved_before_splitting_get_default(self):
        del self.fc.defaults["cutting_job_end"]["segment_length"]
        del self.fc.defaults["cutting_job_end"]["split"]
        self.assertEqual(self.library.split_settings("MM"), {"split": True, "segment_length": 2.0})

    def test_drill_bits_plunge_at_their_plunge_rate(self):
        for bit in self.library.drill_bits():
            bit["feed"], bit["plunge"] = 300.0, 40.0
        self.fc.defaults["cutting_job_end"].update(z_end=15.0, return_to_origin=False)
        self.fc.open_excellon('tests/excellon_files/case1.drl')
        exc = self.fc.collection.get_by_name('case1.drl')
        self.fc.collection.set_active('case1.drl')
        exc.ui.tools_table.selectAll()
        exc.on_create_cncjob_button_click()
        gcode = lines(self.wait_for('case1.drl_cnc').gcode)
        feeds = {l for l in gcode if l.startswith("F")}
        self.assertIn("F%.2f" % (40.0 / INCH), feeds)
        self.assertNotIn("F%.2f" % (300.0 / INCH), feeds)
        self.assertEqual(gcode[-2:], ["G00 Z%.4f" % (15.0 / INCH), "M05"])

        # Each hole: plunge at feed, then straight back up at rapid
        travel = "G00 Z%.4f" % exc.options["travelz"]
        holes = [i for i, l in enumerate(gcode) if re.match(r'G01 Z-', l)]
        self.assertEqual(len(holes), len(exc.drills))
        for i in holes:
            self.assertEqual(gcode[i + 1], travel, "retract after line %d is not a rapid" % i)
        self.assertNotIn("G01 Z0", gcode)


class ToolTableTestCase(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.library = self.fc.tool_library
        for _ in range(20):
            self.library.on_add_tool()
        self.library.table.setFixedHeight(220)
        self.library.show()
        self.app.processEvents()

    def test_edit_keeps_row_and_scroll_position(self):
        table = self.library.table
        row = table.rowCount() - 3
        table.setCurrentCell(row, 4)
        table.scrollToItem(table.item(row, 4))
        scroll = table.verticalScrollBar().value()
        self.assertGreater(scroll, 0)

        table.item(row, 4).setText("150")
        self.app.processEvents()  # The library redraws itself after an edit

        self.assertEqual(self.library.tools()[row]["feed"], 150.0)
        self.assertEqual(table.currentRow(), row)
        self.assertEqual(table.verticalScrollBar().value(), scroll)


if __name__ == '__main__':
    unittest.main()
