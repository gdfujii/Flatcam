from shapely.geometry import *
import unittest


def ring_vertex_count(geom):
    # Vertex count depends on GEOS buffer tessellation, so derive it from the geometry
    polygon = shape(geom)
    return sum(len(r.coords) for r in [polygon.exterior, *polygon.interiors])

from descartes.patch import PolygonPatch

class PolygonTestCase(unittest.TestCase):
    polygon = Point(0, 0).buffer(10.0).difference(
                MultiPoint([(-5, 0), (5, 0)]).buffer(3.0))
    def test_patch(self):
        patch = PolygonPatch(self.polygon)
        self.assertEqual(str(type(patch)), 
            "<class 'matplotlib.patches.PathPatch'>")
        path = patch.get_path()
        self.assertTrue(len(path.vertices) == len(path.codes) == ring_vertex_count(self.polygon))

class JSONPolygonTestCase(unittest.TestCase):
    polygon = Point(0, 0).buffer(10.0).difference(
                MultiPoint([(-5, 0), (5, 0)]).buffer(3.0))
    def test_patch(self):
        geo = self.polygon.__geo_interface__
        patch = PolygonPatch(geo)
        self.assertEqual(str(type(patch)), 
            "<class 'matplotlib.patches.PathPatch'>")
        path = patch.get_path()
        self.assertTrue(len(path.vertices) == len(path.codes) == ring_vertex_count(self.polygon))

class GeoInterfacePolygonTestCase(unittest.TestCase):
    class GeoThing:
        __geo_interface__ = None
    thing = GeoThing()
    thing.__geo_interface__ = Point(0, 0).buffer(10.0).difference(
                MultiPoint([(-5, 0), (5, 0)]).buffer(3.0)).__geo_interface__
    def test_patch(self):
        patch = PolygonPatch(self.thing)
        self.assertEqual(str(type(patch)), 
            "<class 'matplotlib.patches.PathPatch'>")
        path = patch.get_path()
        self.assertTrue(len(path.vertices) == len(path.codes) == ring_vertex_count(self.thing.__geo_interface__))
