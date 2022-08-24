from ...common import TestCase
import eleanor.hanger.data0_tools as data0
import numpy as np

class TestTPCurve(TestCase):
    """
    Tests of the TPCurve class
    """

    def assertDomainsAlmostEqual(self, first, second):
        """
        Compare two domains
        """
        self.assertEquals(len(first), len(second))
        for (f, s) in zip(first, second):
            if not np.all(np.isclose(f, s)):
                self.fail(f'expected {second}, got {first}')

    def assertIntersectionsAlmostEqual(self, first, second):
        """
        Compare two arrays of intersection points
        """
        self.assertEquals(len(first), len(second))
        for (f, s) in zip(first, second):
            for (x, y) in zip(f, s):
                if not np.all(np.isclose(x, y)):
                    self.fail(f'expected {s}, got {f}')

    def test_canary(self):
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_initialization(self):
        """
        Test that TPCurve can be initialized
        """
        with self.assertRaises(ValueError):
            data0.TPCurve({'min': 5, 'max': 10}, [[1, 0, 0, 0]])
        with self.assertRaises(ValueError):
            data0.TPCurve({'min': 5, 'mid': 8, 'max': 10}, [])
        with self.assertRaises(ValueError):
            data0.TPCurve({'min': 5, 'mid': 8, 'max': 10}, [[1, 0, 0, 0], []])

        with self.assertRaises(ValueError):
            data0.TPCurve({'min': 5, 'mid': 8, 'max': 10}, [[1, 0, 0, 0], [2, 0, 0, 0, 0]])

        curve = data0.TPCurve({'min': 5, 'mid': 8, 'max': 10},
                              [[1, 0, 0, 0], [-7, 1, 0, 0, 0]])
        self.assertEquals(curve.T, {'min': 5, 'mid': 8, 'max': 10})
        self.assertEquals(curve.P, [[1, 0, 0, 0], [-7, 1, 0, 0, 0]])
        self.assertEquals(curve.domain, [[5, 10]])

    def test_reset_domain(self):
        """
        Test that we can reset the temperature domain to the default
        """
        curve = data0.TPCurve({'min': 5, 'mid': 8, 'max': 10},
                              [[1, 0, 0, 0], [-7, 1, 0, 0, 0]])
        curve.domain = [[5, 7], [8, 10]]
        self.assertEquals(curve.domain, [[5, 7], [8, 10]])

        curve.reset_domain()
        self.assertEquals(curve.domain, [[5, 10]])

    def test_temperature_in_domain(self):
        """
        Test that we can determine if a temperature is in the interpolation's domain
        """
        curve = data0.TPCurve({'min': 5, 'mid': 8, 'max': 10}, [[1, 0, 0, 0], [-7, 1, 0]])

        for T in [5, 5.1, 7.9, 8, 8.1, 9.9, 10]:
            self.assertTrue(curve.temperature_in_domain(T))

        for T in [4.9, 10.1]:
            self.assertFalse(curve.temperature_in_domain(T))

        curve.domain = [[6, 7], [8.5, 9.3]]

        for T in [6, 6.5, 7, 8.5, 8.7, 9.3]:
            self.assertTrue(curve.temperature_in_domain(T))

        for T in [5, 5.9, 7.1, 8.4, 9.4, 10]:
            self.assertFalse(curve.temperature_in_domain(T))

    def test_evaluate(self):
        """
        Test that we can evaluate the polynomial at a given temperature in it's domain
        """
        curve = data0.TPCurve({'min': 5, 'mid': 8, 'max': 10}, [[1, 0, 0], [-7, 1, 0]])

        for T in [4, 4.9999, 10.0001, 11]:
            with self.assertRaises(ValueError):
                curve(T)

        for T in np.linspace(5, 8):
            self.assertEquals(curve(T), 1.0)
        for T in np.linspace(8, 10):
            self.assertEquals(curve(T), T - 7)

        curve.domain = [[6, 7], [8.5, 9.3]]

        for T in [4, 4.9999, 5, 5.9999, 7.0001, 8, 8.4999, 9.3001, 9.4, 10.0001, 11]:
            with self.assertRaises(ValueError):
                curve(T)

        for T in np.linspace(6, 7):
            self.assertEquals(curve(T), 1.0)
        for T in np.linspace(8.5, 9.3):
            self.assertEquals(curve(T), T - 7)

    def test_boundary_intersections(self):
        """
        Test that we correctly compute the curve intersections with a bounded region
        """
        table = [{
            # Completely contained
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [4, 11],
            'Prange': [0, 10],
            'intersections': [],
        }, {
            # Not contained at all
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [11, 12],
            'Prange': [0, 10],
            'intersections': [],
        }, {
            # Intersects the vertical edges
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 7],
            'Prange': [0, 10],
            'intersections': [(6, 1), (7, 1)],
        }, {
            # Intersects the vertical edges
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 9],
            'Prange': [0, 10],
            'intersections': [(6, 1), (9, 2)],
        }, {
            # Intersects the vertical and top horizontal
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 11],
            'Prange': [0, 3],
            'intersections': [(6, 1), (10, 3)],
        }, {
            # Intersects the top and bottom horizontal
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 13],
            'Prange': [2, 3],
            'intersections': [(9, 2), (10, 3)],
        }, {
            # Just intersects
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 13],
            'Prange': [3, 4],
            'intersections': [(10, 3)],
        }, {
            # Intersect the top horizonal twice
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[9, -1, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [5, 11],
            'Prange': [0, 3],
            'intersections': [(6, 3), (10, 3)],
        }, {
            # Intersect verticals and the top mutiple times
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[-4, 11, -6, 1], [-4, 11, -6, 1]],
            'Trange': [0.5, 3.0],
            'Prange': [0.0, 2.0],
            # The fourth element comes from the max T boundary and the fifth comes
            # from the intersection with the max P boundary because the curve hits
            # the corner exactly
            'intersections': [(0.5, 0.125), (1.0, 2.0), (2.0, 2.0), (3.0, 2.0), (3.0, 2.0)],
        }, {
            # Horizontal line that crosses a vertical
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[2, 0, 0, 0], [2, 0, 0, 0]],
            'Trange': [3, 5],
            'Prange': [1, 3],
            'intersections': [(3, 2)],
        }, {
            # Horizontal line that hits a P bound
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[2, 0, 0, 0], [2, 0, 0, 0]],
            'Trange': [3, 5],
            'Prange': [2, 3],
            'intersections': [(3, 2)],
        }]

        for row in table:
            curve = data0.TPCurve(row['T'], row['P'])
            intersections = curve.find_boundary_intersections(row['Trange'], row['Prange'])
            self.assertIntersectionsAlmostEqual(intersections, row['intersections'])

    def test_set_domain(self):
        """
        Test that we correctly set the domain
        """
        table = [{
            # Completely contained
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [4, 11],
            'Prange': [0, 10],
            'domain': [[5, 10]],
            'notEmpty': True,
        }, {
            # Not contained at all
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [11, 12],
            'Prange': [0, 10],
            'domain': [],
            'notEmpty': False,
        }, {
            # Intersects the vertical edges
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 7],
            'Prange': [0, 10],
            'domain': [[6, 7]],
            'notEmpty': True,
        }, {
            # Intersects the vertical edges
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 9],
            'Prange': [0, 10],
            'domain': [[6, 9]],
            'notEmpty': True,
        }, {
            # Intersects the vertical and top horizontal
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 11],
            'Prange': [0, 3],
            'domain': [[6, 10]],
            'notEmpty': True,
        }, {
            # Intersects the top and bottom horizontal
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 13],
            'Prange': [2, 3],
            'domain': [[9, 10]],
            'notEmpty': True,
        }, {
            # Just intersects
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[1, 0, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [6, 13],
            'Prange': [3, 4],
            'domain': [(10, 10)],
            'notEmpty': True,
        }, {
            # Intersect the top horizonal twice
            'T': {'min': 5, 'mid': 8, 'max': 10},
            'P': [[9, -1, 0, 0], [-7, 1, 0, 0, 0]],
            'Trange': [5, 11],
            'Prange': [0, 3],
            'domain': [[6, 10]],
            'notEmpty': True,
        }, {
            # Intersect verticals and the top mutiple times
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[-4, 11, -6, 1], [-4, 11, -6, 1]],
            'Trange': [0.5, 3.0],
            'Prange': [0.0, 2.0],
            # The last subdomain is basically a single point
            'domain': [[0.5, 1.0], [2.0, 3.0], [3.0, 3.0]],
            'notEmpty': True,
        }, {
            # Horizontal line that crosses a vertical
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[2, 0, 0, 0], [2, 0, 0, 0]],
            'Trange': [3, 5],
            'Prange': [1, 3],
            'domain': [[3, 4]],
            'notEmpty': True,
        }, {
            # Horizontal line that hits a P bound
            'T': {'min': 0, 'mid': 2, 'max': 4},
            'P': [[2, 0, 0, 0], [2, 0, 0, 0]],
            'Trange': [3, 5],
            'Prange': [2, 3],
            'domain': [[3, 4]],
            'notEmpty': True
        }]

        for row in table:
            curve = data0.TPCurve(row['T'], row['P'])
            notEmpty = curve.set_domain(row['Trange'], row['Prange'])
            self.assertDomainsAlmostEqual(curve.domain, row['domain'])
            self.assertEquals(notEmpty, row['notEmpty'])
