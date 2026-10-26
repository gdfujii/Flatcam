"""
Plunge feed rates and how jobs end, in the generated G-code.
"""

import re
import sys
import time
import unittest

from PyQt6 import QtWidgets

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

    def isolation_gcode(self):
        self.gerber.isolate(passes=1, combine=True)
        geo = self.wait_for('simple1.gbr_iso')
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
        self.assertEqual(gcode[-3:], ["G00 Z%.4f" % (15.0 / INCH), "M05", "G00 X0.0000Y0.0000"])

    def test_job_can_end_without_returning(self):
        self.fc.defaults["cutting_job_end"].update(z_end=10.0, return_to_origin=False)
        gcode = self.isolation_gcode()
        self.assertEqual(gcode[-2:], ["G00 Z%.4f" % (10.0 / INCH), "M05"])

    def test_end_height_never_below_travel_height(self):
        self.fc.defaults["cutting_job_end"].update(z_end=0.01, return_to_origin=True)
        gcode = self.isolation_gcode()
        travel = self.fc.collection.get_by_name('simple1.gbr_iso').options["travelz"]
        self.assertEqual(gcode[-3], "G00 Z%.4f" % travel)

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
