import os
import sys
import tempfile
import unittest

from PyQt6 import QtWidgets

from FlatCAMApp import App


class OpenFilesTestCase(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.messages = []
        self.fc.inform.connect(self.messages.append)

    def test_drill_file_opened_as_gcode_opens_as_excellon(self):
        self.fc.open_gcode('tests/excellon_files/case1.drl')
        obj = self.fc.collection.get_by_name('case1.drl')
        self.assertEqual(obj.kind, "excellon")
        self.assertTrue(obj.drills)
        self.assertTrue(any("Excellon drill file" in m for m in self.messages))

    def test_gcode_without_moves_warns_and_zoom_fit_still_works(self):
        self.fc.open_gerber('tests/gerber_files/simple1.gbr')
        with tempfile.NamedTemporaryFile('w', suffix='.nc', delete=False) as f:
            f.write("G20\nG90\nM05\n")
        try:
            self.fc.open_gcode(f.name)
        finally:
            os.remove(f.name)
        self.assertTrue(any("No tool movements" in m for m in self.messages))

        # The empty job must not stop zooming to fit the rest
        xmin, ymin, xmax, ymax = self.fc.collection.get_bounds()
        gerber = self.fc.collection.get_by_name('simple1.gbr').bounds()
        self.assertEqual((xmin, ymin, xmax, ymax), tuple(gerber))
        self.fc.on_zoom_fit(None)
        x0, x1 = self.fc.plotcanvas.axes.get_xlim()
        self.assertLess(x0, gerber[0])
        self.assertGreater(x1, gerber[2])


if __name__ == '__main__':
    unittest.main()
