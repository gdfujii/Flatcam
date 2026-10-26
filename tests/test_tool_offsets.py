"""
Checks that toolpaths are offset from the copper (or board edge, or hole
wall) by the tool's radius, not its diameter, all the way to the G-code.
"""

import re
import sys
import time
import unittest

from PyQt6 import QtWidgets
from shapely.geometry import Point, box

from FlatCAMApp import App
from camlib import Geometry, autolist

# Coordinates are written to the G-code with 4 decimals (inches here)
GCODE_TOLERANCE = 1e-4
GEOMETRY_TOLERANCE = 1e-6
# GEOS simplifies the input of a buffer by up to 1% of the buffer distance,
# so offset curves can come up to that much closer.
BUFFER_TOLERANCE = 0.01


def cutting_points(gcode):
    """XY of every G01 move made with the tool below Z=0."""
    points = []
    x = y = z = 0.0
    for line in gcode.splitlines():
        words = dict((k, float(v)) for k, v in re.findall(r'([XYZG])(-?[\d.]+)', line))
        x, y, z = words.get('X', x), words.get('Y', y), words.get('Z', z)
        if words.get('G') == 1 and z < 0 and ('X' in words or 'Y' in words):
            points.append((x, y))
    return points


class ToolOffsetTestCase(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.fc.version_check = lambda: None
        self.library = self.fc.tool_library
        # Isolate and cut out with the 0.8mm end mill: radius and diameter differ by 0.4mm
        ops = self.fc.defaults["cutting_operations"]
        ops["isolation"]["tool"] = 2
        ops["outline"]["tool"] = 2
        self.fc.open_gerber('tests/gerber_files/simple1.gbr')
        self.gerber = self.fc.collection.get_by_name('simple1.gbr')
        self.fc.collection.set_active('simple1.gbr')

    def wait_for(self, name, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            obj = self.fc.collection.get_by_name(name)
            if obj is not None:
                return obj
            time.sleep(0.05)
        self.fail("%s was not created" % name)

    def make_gcode(self, geo):
        geo.generatecncjob()
        job = self.wait_for(geo.options["name"] + "_cnc")
        return "".join(job.gcode)

    def test_isolation_offset_is_tool_radius(self):
        tool = self.library.isolation_settings(self.gerber.units)
        radius = tool["dia"] / 2
        self.assertAlmostEqual(tool["dia"], 0.8 / 25.4)

        self.gerber.isolate(passes=1, combine=True)
        geo = self.wait_for('simple1.gbr_iso')
        copper = self.gerber.solid_geometry

        # Toolpath vertices sit one radius away from the copper
        paths = [ring for poly in autolist(geo.solid_geometry) for p in autolist(poly)
                 for ring in [p.exterior, *p.interiors]]
        distances = [copper.distance(Point(c)) for ring in paths for c in ring.coords]
        self.assertTrue(distances)
        for d in distances:
            self.assertAlmostEqual(d, radius, delta=radius * BUFFER_TOLERANCE)

        # The G-code follows those paths: the tool centre stays a radius from
        # the copper, and the paths are not offset again
        points = cutting_points(self.make_gcode(geo))
        self.assertTrue(points)
        for x, y in points:
            self.assertAlmostEqual(copper.distance(Point(x, y)), radius,
                                   delta=radius * BUFFER_TOLERANCE + GCODE_TOLERANCE)

    def test_multiple_passes_step_by_tool_width(self):
        tool = self.library.isolation_settings(self.gerber.units)
        dia = tool["dia"]
        overlap = 0.15
        self.gerber.isolate(passes=2, overlap=overlap, combine=False)
        copper = self.gerber.solid_geometry
        for n, expected in ((1, dia / 2), (2, dia / 2 + dia * (1 - overlap))):
            geo = self.wait_for('simple1.gbr_iso%d' % n)
            ring = autolist(geo.solid_geometry)[0].exterior
            for c in ring.coords:
                self.assertAlmostEqual(copper.distance(Point(c)), expected,
                                       delta=expected * BUFFER_TOLERANCE)

    def test_cutout_offset_is_tool_radius(self):
        tool = self.library.outline_settings(self.gerber.units)
        radius = tool["dia"] / 2
        margin = self.gerber.options["cutoutmargin"]
        gap = self.gerber.options["cutoutgapsize"]

        self.gerber.on_generatecutout_button_click()
        geo = self.wait_for('simple1.gbr_cutout')

        minx, miny, maxx, maxy = self.gerber.bounds()
        expected = (minx - margin - radius, miny - margin - radius,
                    maxx + margin + radius, maxy + margin + radius)
        for got, want in zip(geo.bounds(), expected):
            self.assertAlmostEqual(got, want, delta=GEOMETRY_TOLERANCE)

        # The gaps in the path leave exactly `gap` of material: the path gap
        # is wider by one radius on each side
        gcode_pts = cutting_points(self.make_gcode(geo))
        for x, y in gcode_pts:
            on_outline = min(abs(x - expected[0]), abs(x - expected[2]),
                             abs(y - expected[1]), abs(y - expected[3]))
            self.assertLess(on_outline, GCODE_TOLERANCE)
        path = geo.solid_geometry
        top = box(minx - 1, expected[3] - 1e-9, maxx + 1, expected[3] + 1e-9)
        top_cuts = sorted(autolist(path.intersection(top)), key=lambda g: g.bounds[0])
        material_gap = top_cuts[1].bounds[0] - top_cuts[0].bounds[2] - 2 * radius
        self.assertAlmostEqual(material_gap, gap, delta=GEOMETRY_TOLERANCE)

    def test_geocutout_gaps_allow_for_tool_radius(self):
        dia, gap = 0.1, 0.2

        def init(geo_obj, app_obj):
            geo_obj.solid_geometry = [box(0, 0, 2, 1).exterior]
        self.fc.new_object("geometry", "outline", init)
        self.fc.exec_command_test('geocutout outline -dia %g -gapsize %g -gaps 4' % (dia, gap))

        # Left in the material between the cuts on the top edge: the gap in the
        # toolpath less a tool radius at each end
        path = self.fc.collection.get_by_name("outline").solid_geometry
        top = box(-1, 1 - 1e-9, 3, 1 + 1e-9)
        cuts = sorted(autolist(path.intersection(top)), key=lambda g: g.bounds[0])
        self.assertEqual(len(cuts), 2)
        material_gap = cuts[1].bounds[0] - cuts[0].bounds[2] - dia
        self.assertAlmostEqual(material_gap, gap, delta=GEOMETRY_TOLERANCE)

    def test_paint_offset_is_tool_radius(self):
        tooldia = 0.1
        square = box(0, 0, 2, 2)
        paths = Geometry.clear_polygon(square, tooldia, overlap=0.15, connect=False)
        outer = max(paths.get_objects(), key=lambda p: p.length)
        for c in outer.coords:
            self.assertAlmostEqual(square.exterior.distance(Point(c)), tooldia / 2,
                                   delta=GEOMETRY_TOLERANCE)


class HoleMillingOffsetTestCase(unittest.TestCase):

    wait_for = ToolOffsetTestCase.wait_for

    def setUp(self):
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.fc = App(user_defaults=False)
        self.fc.version_check = lambda: None
        self.fc.open_excellon('tests/excellon_files/case1.drl')
        self.excellon = self.fc.collection.get_by_name('case1.drl')

    def test_mill_holes_offset_is_tool_radius(self):
        tooldia = min(t["C"] for t in self.excellon.tools.values()) / 2
        self.excellon.generate_milling(tools="all", tooldia=tooldia)
        geo = self.wait_for('case1.drl_mill')
        for ring in geo.solid_geometry:
            centre = ring.centroid
            hole = [self.excellon.tools[d["tool"]]["C"] for d in self.excellon.drills
                    if d["point"].distance(centre) < 1e-9][0]
            for c in ring.coords:
                # Tool centre one radius inside the hole wall
                self.assertAlmostEqual(Point(c).distance(centre), hole / 2 - tooldia / 2,
                                       delta=GEOMETRY_TOLERANCE)


if __name__ == '__main__':
    unittest.main()
