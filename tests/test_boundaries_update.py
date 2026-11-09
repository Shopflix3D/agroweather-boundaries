import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from update_boundaries import validate_geojson, remote_catalog


class GeoJsonSafetyTests(unittest.TestCase):
    def sample(self):
        return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {}, 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]}

    def test_simple_valid_geometry(self):
        self.assertEqual(validate_geojson(self.sample())['points'], 4)

    def test_rejects_unclosed_ring(self):
        data = self.sample()
        data['features'][0]['geometry']['coordinates'][0][-1] = [0.1, 0.1]
        with self.assertRaises(ValueError):
            validate_geojson(data)

    def test_rejects_out_of_bounds(self):
        data = self.sample()
        data['features'][0]['geometry']['coordinates'][0][1] = [181, 0]
        with self.assertRaises(ValueError):
            validate_geojson(data)

    def test_rejects_unexpected_catalog(self):
        with self.assertRaises(ValueError):
            remote_catalog([{'boundaryISO': 'BRA', 'boundaryType': 'ADM1', 'boundaryID': 'abc'}])


if __name__ == '__main__':
    unittest.main()
