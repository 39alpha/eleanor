from typing import cast
from unittest import TestCase, mock

import numpy as np

from eleanor.kernel.eq36.data1 import AqueousSpecies, BasisSpecies, Data1, Gas, Liquid, Mineral, TPCurve
from eleanor.kernel.eq36.libeq36 import Data


class TestEq36Data1(TestCase):
    """
    Tests of the eleanor.kernel.eq36.data1 module.
    """

    def _curve(self):
        return TPCurve(
            {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
            (np.array([1.0], dtype=np.float64), np.array([1.0], dtype=np.float64)),
        )

    def test_tpcurve_init_validation_errors(self):
        """
        Ensure TPCurve validates input temperature metadata and polynomial shape/content.
        """
        with self.assertRaises(ValueError):
            _ = TPCurve(
                cast(dict[str, np.float64], cast(object, {"min": np.float64(0.0), "max": np.float64(10.0)})),
                (np.array([1.0], dtype=np.float64), np.array([1.0], dtype=np.float64)),
            )
        with self.assertRaises(ValueError):
            _ = TPCurve(
                {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
                cast(
                    tuple[
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                    ],
                    cast(object, [np.array([1.0])]),
                ),
            )
        with self.assertRaises(ValueError):
            _ = TPCurve(
                {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
                cast(
                    tuple[
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                    ],
                    cast(object, [np.array([]), np.array([1.0])]),
                ),
            )
        with self.assertRaises(ValueError):
            _ = TPCurve(
                {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
                cast(
                    tuple[
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                        np.ndarray[tuple[int], np.dtype[np.float64]],
                    ],
                    cast(object, [np.array([1.0]), np.array([2.0])]),
                ),
            )

    def test_tpcurve_init_requires_float64_dot_results(self):
        """
        Ensure TPCurve constructor rejects non-np.float64 polynomial evaluations.
        """
        with mock.patch("numpy.dot", side_effect=[1.0, np.float64(1.0)]):
            with self.assertRaises(TypeError):
                _ = TPCurve(
                    {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
                    (np.array([1.0], dtype=np.float64), np.array([1.0], dtype=np.float64)),
                )

        with mock.patch("numpy.dot", side_effect=[np.float64(1.0), 1.0]):
            with self.assertRaises(TypeError):
                _ = TPCurve(
                    {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
                    (np.array([1.0], dtype=np.float64), np.array([1.0], dtype=np.float64)),
                )

    def test_tpcurve_domain_and_call(self):
        """
        Ensure domain helpers and polynomial evaluation dispatch behave as expected.
        """
        c = TPCurve(
            {"min": np.float64(0.0), "mid": np.float64(5.0), "max": np.float64(10.0)},
            cast(
                tuple[
                    np.ndarray[tuple[int], np.dtype[np.float64]],
                    np.ndarray[tuple[int], np.dtype[np.float64]],
                ],
                cast(object, [np.array([2.0, 1.0]), np.array([2.0, 1.0])]),
            ),
        )
        self.assertIs(c.reset_domain(), c)
        self.assertTrue(c.temperature_in_domain(np.float64(1.0)))
        self.assertFalse(c.temperature_in_domain(np.float64(20.0)))
        self.assertEqual(float(c(np.float64(0.0))), np.float64(2.0))
        self.assertEqual(float(c(np.float64(10.0))), np.float64(12.0))
        with self.assertRaises(ValueError):
            _ = c(np.float64(99.0))

    def test_tpcurve_call_requires_float64_dot_result(self):
        """
        Ensure TPCurve.__call__ rejects non-np.float64 dot-product outputs.
        """
        c = self._curve()
        with mock.patch("numpy.dot", return_value=1.0):
            with self.assertRaises(TypeError):
                _ = c(np.float64(1.0))

    def test_tpcurve_set_domain_zero_intersections_branches(self):
        """
        Ensure zero-intersection branches handle empty, inconsistent, and full-domain outcomes.
        """
        with mock.patch.object(TPCurve, "find_boundary_intersections", return_value=[]):
            c = self._curve()
            self.assertFalse(c.set_domain((np.float64(20.0), np.float64(30.0)), (np.float64(0.0), np.float64(2.0))))
            self.assertEqual(c.domain, [])
            c = self._curve()

            with self.assertRaises(Exception):
                _ = c.set_domain((np.float64(0.0), np.float64(3.0)), (np.float64(0.0), np.float64(2.0)))
            c = self._curve()

            self.assertTrue(c.set_domain((-np.float64(1.0), np.float64(11.0)), (np.float64(0.0), np.float64(2.0))))
            self.assertEqual(c.domain, [(0.0, 10.0)])

    def test_tpcurve_set_domain_one_and_multiple_intersections(self):
        """
        Ensure one-intersection and multi-intersection branches build expected subdomains.
        """
        c = self._curve()
        with mock.patch.object(TPCurve, "find_boundary_intersections", return_value=[(5.0, 1.0)]):
            c = self._curve()
            self.assertTrue(c.set_domain((np.float64(5.0), np.float64(5.0)), (np.float64(0.0), np.float64(2.0))))
            self.assertEqual(c.domain, [(5.0, 5.0)])
            c = self._curve()

            self.assertTrue(c.set_domain((np.float64(0.0), np.float64(10.0)), (np.float64(0.0), np.float64(2.0))))
            self.assertEqual(c.domain, [(0.0, 5.0), (5.0, 10.0)])

        with mock.patch.object(
            TPCurve,
            "find_boundary_intersections",
            return_value=[(1.0, 1.0), (3.0, 1.0), (8.0, 1.0)],
        ):
            c = self._curve()
            self.assertTrue(c.set_domain((np.float64(0.0), np.float64(10.0)), (np.float64(0.0), np.float64(2.0))))
            self.assertEqual(c.domain, [(1.0, 3.0), (3.0, 8.0)])

    def test_tpcurve_find_intersections_union_and_sample(self):
        """
        Ensure intersection detection, domain unioning, and sampling flow execute as expected.
        """
        c = self._curve()
        intersections = c.find_boundary_intersections(
            (np.float64(0.0), np.float64(10.0)), (np.float64(1.0), np.float64(2.0))
        )
        self.assertTrue((0.0, 1.0) in intersections and (10.0, 1.0) in intersections)

        c1 = self._curve()
        c1.domain = [(np.float64(0.0), np.float64(2.0)), (np.float64(3.0), np.float64(4.0))]
        c2 = self._curve()
        c2.domain = [(np.float64(1.0), np.float64(3.5))]
        self.assertEqual(TPCurve.union_domains([]), [])
        self.assertEqual(TPCurve.union_domains([c1, c2]), [(0.0, 4.0)])

        c3 = self._curve()
        c3.domain = [(np.float64(0.0), np.float64(2.0))]
        with (
            mock.patch("numpy.random.uniform", return_value=np.array([0.5, 1.5])),
            mock.patch("numpy.random.randint", side_effect=[0, 0]),
        ):
            Ts, Ps, selected = TPCurve.sample([c3], 2)
        self.assertEqual(list(Ts), [0.5, 1.5])
        self.assertEqual(list(Ps), [1.0, 1.0])
        self.assertEqual(len(selected), 2)

    def test_tpcurve_find_intersections_skips_temperatures_outside_domain(self):
        """
        Ensure find_boundary_intersections skips candidate temperatures outside the active curve domain.
        """
        c = self._curve()
        c.domain = [(np.float64(1.0), np.float64(2.0))]
        intersections = c.find_boundary_intersections(
            (np.float64(0.0), np.float64(2.0)), (np.float64(1.0), np.float64(1.0))
        )
        self.assertFalse(any(t == 0.0 for t, _ in intersections))

    def test_tpcurve_find_intersections_includes_right_polynomial_roots(self):
        """
        Ensure find_boundary_intersections includes roots from the right-hand polynomial branch.
        """
        c = self._curve()
        with mock.patch("numpy.roots", return_value=np.array([8.0])):
            intersections = c.find_boundary_intersections(
                (np.float64(0.0), np.float64(10.0)), (np.float64(1.0), np.float64(1.0))
            )
        self.assertIn((8.0, 1.0), intersections)

    def test_tpcurve_union_domains_disjoint_subdomains(self):
        """
        Ensure union_domains preserves separated intervals when subdomains do not overlap.
        """
        c1 = self._curve()
        c1.domain = [(np.float64(0.0), np.float64(1.0))]
        c2 = self._curve()
        c2.domain = [(np.float64(3.0), np.float64(4.0))]
        self.assertEqual(TPCurve.union_domains([c1, c2]), [(0.0, 1.0), (3.0, 4.0)])

    def test_tpcurve_sample_adjusts_across_domain_steps(self):
        """
        Ensure sample shifts candidate temperatures across gaps between disjoint domain intervals.
        """
        c1 = self._curve()
        c1.domain = [(np.float64(0.0), np.float64(1.0))]
        c2 = self._curve()
        c2.domain = [(np.float64(3.0), np.float64(4.0))]
        with (
            mock.patch("numpy.random.uniform", return_value=np.array([0.2, 1.8])),
            mock.patch("numpy.random.randint", side_effect=[0, 0]),
        ):
            Ts, Ps, selected = TPCurve.sample([c1, c2], 2)
        self.assertEqual(list(Ts), [0.2, 3.8])
        self.assertEqual(list(Ps), [1.0, 1.0])
        self.assertEqual(selected[0], c1)
        self.assertEqual(selected[1], c2)

    def _read_data1_payload(self, duplicate_end_member: bool = False):
        species = np.array(
            [
                b"H+                      ",
                b"Calcite                 ",
                b"H2O(l)                  ",
                b"CO2(g)                  ",
                b"EM1                     SOLID1",
                (b"EM1                     SOLID1" if duplicate_end_member else b"EM2                     SOLID1"),
            ],
            dtype="|S48",
        )
        return Data(
            min_temperature=np.float64(0.0),
            max_temperature_range=np.array([5.0, 10.0]),
            pressure_coefficients=np.array([[1.0, 1.0]]),
            element_names=np.array([b"H", b"O"]),
            atomic_weights=np.array([1.0, 16.0]),
            species_names=species,
            species_molar_weights=np.array([1.0, 100.09, 18.0, 44.01, 50.0, 70.0]),
            cdrsa=np.array([0, 1, 1, 1, 1, 1]),
            charges=np.array([1, 0, 0, 0, 0, 0]),
            volumes=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            nessra=np.array([[1, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0]]),
            nessa=np.array([1, 2]),
            cessa=np.array([2.0, 1.0]),
            narn1a=np.int32(1),
            narn2a=np.int32(1),
            nmrn1a=np.int32(2),
            nmrn2a=np.int32(2),
            nlrn1a=np.int32(3),
            nlrn2a=np.int32(3),
            ngrn1a=np.int32(4),
            ngrn2a=np.int32(4),
            nxrn1a=np.int32(5),
            nxrn2a=np.int32(6),
        )

    def test_data1_get_basis_species_and_from_file(self):
        """
        Ensure Data1 basis-species lookup and from_file parser wiring work for normal payloads.
        """
        d = Data1(
            filename="x",
            elements={"H": np.float64(1.0)},
            basis_species={
                "H+": BasisSpecies(name="H+", composition={"H": 1}, charge=1, volume=None, molar_mass=np.float64(1.0))
            },
            aqueous_species={"H+": AqueousSpecies(name="H+", molar_mass=np.float64(1.0))},
            minerals={},
            liquids={},
            gases={},
            solid_solutions={},
            tp_curve=None,
        )
        h_basis = d.get_basis_species("H")
        self.assertIsNotNone(h_basis)
        assert h_basis is not None
        self.assertEqual(h_basis.name, "H+")
        self.assertIsNone(d.get_basis_species("Na"))

        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=self._read_data1_payload()):
            parsed = Data1.from_file("fake.d1")
        self.assertEqual(parsed.filename, "fake.d1")
        self.assertIn("H", parsed.elements)
        self.assertIn("H+", parsed.basis_species)
        self.assertEqual(parsed.basis_species["H+"].molar_mass, np.float64(1.0))
        self.assertEqual(parsed.aqueous_species, {"H+": AqueousSpecies(name="H+", molar_mass=np.float64(1.0))})
        self.assertEqual(parsed.minerals, {"Calcite": Mineral(name="Calcite", molar_mass=np.float64(100.09))})
        self.assertEqual(parsed.liquids, {"H2O(l)": Liquid(name="H2O(l)", molar_mass=np.float64(18.0))})
        self.assertEqual(parsed.gases, {"CO2(g)": Gas(name="CO2(g)", molar_mass=np.float64(44.01))})
        self.assertIn("SOLID1", parsed.solid_solutions)
        self.assertEqual(
            parsed.solid_solutions["SOLID1"].end_members,
            {"EM1": np.float64(50.0), "EM2": np.float64(70.0)},
        )
        self.assertIsNotNone(parsed.tp_curve)

        self.assertEqual(parsed.molar_mass("H+"), np.float64(1.0))
        self.assertEqual(parsed.molar_mass("Calcite"), np.float64(100.09))
        self.assertEqual(parsed.molar_mass("H2O(l)"), np.float64(18.0))
        self.assertEqual(parsed.molar_mass("CO2(g)"), np.float64(44.01))
        self.assertEqual(parsed.molar_mass("EM1"), np.float64(50.0))

        with self.assertRaises(ValueError):
            self.assertEqual(parsed.molar_mass("SOLID1"), np.float64(60.0))

        self.assertEqual(
            parsed.molar_mass("SOLID1", {"EM1": np.float64(0.25), "EM2": np.float64(0.75)}),
            np.float64(0.25 * 50.0 + 0.75 * 70.0),
        )
        with self.assertRaises(KeyError):
            _ = parsed.molar_mass("Unknown")

        self.assertEqual(parsed.compute_molar_mass({"H": 2, "O": 1}), np.float64(18.0))
        with self.assertRaises(ValueError):
            _ = parsed.compute_molar_mass({})
        with self.assertRaises(KeyError):
            _ = parsed.compute_molar_mass({"Xe": 1})
        with self.assertRaises(ValueError):
            _ = parsed.compute_molar_mass({"H": -1})

    def test_species_init_validation(self):
        """
        Ensure Species rejects empty names and negative molar masses via concrete subclasses.
        """
        with self.assertRaises(ValueError):
            _ = AqueousSpecies(name="", molar_mass=np.float64(1.0))
        with self.assertRaises(ValueError):
            _ = AqueousSpecies(name="H2O", molar_mass=np.float64(-1.0))

    def test_basis_species_init_validation(self):
        """
        Ensure BasisSpecies rejects empty compositions, negative element counts, and negative volumes.
        """
        with self.assertRaises(ValueError):
            _ = BasisSpecies(name="H+", composition={}, charge=1, volume=None, molar_mass=np.float64(1.0))
        with self.assertRaises(ValueError):
            _ = BasisSpecies(name="H+", composition={"H": -1}, charge=1, volume=None, molar_mass=np.float64(1.0))
        with self.assertRaises(ValueError):
            _ = BasisSpecies(
                name="H+", composition={"H": 1}, charge=1, volume=np.float64(-1.0), molar_mass=np.float64(1.0)
            )

    def test_solid_solution_init_validation(self):
        """
        Ensure SolidSolution rejects empty names, empty end-member dicts, and negative end-member molar masses.
        """
        from eleanor.kernel.eq36.data1 import SolidSolution

        with self.assertRaises(ValueError):
            _ = SolidSolution(name="", end_members={"A": np.float64(1.0)})
        with self.assertRaises(ValueError):
            _ = SolidSolution(name="SS", end_members={})
        with self.assertRaises(ValueError):
            _ = SolidSolution(name="SS", end_members={"A": np.float64(-1.0)})

    def test_data1_from_file_returns_empty_species_for_zero_range(self):
        """
        Ensure Data1.from_file returns an empty dict for a species category whose range index is zero.
        """
        payload = self._read_data1_payload()
        payload.narn1a = np.int32(0)
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            parsed = Data1.from_file("zero-range.d1")
        self.assertEqual(parsed.aqueous_species, {})

    def test_data1_from_file_rejects_non_float64_species_molar_weight(self):
        """
        Ensure Data1.from_file raises TypeError for a non-float64 molar weight in a species category range.
        """
        payload = self._read_data1_payload()
        payload.species_molar_weights = np.array(
            [42, np.float64(100.09), np.float64(18.0), np.float64(44.01), np.float64(50.0), np.float64(70.0)],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-species-weight.d1")

    def test_data1_from_file_rejects_invalid_basis_species_name(self):
        """
        Ensure Data1.from_file raises TypeError for a basis species name not covered by any category range.
        """
        payload = self._read_data1_payload()
        payload.narn1a = np.int32(0)
        payload.nmrn1a = np.int32(0)
        payload.nlrn1a = np.int32(0)
        payload.ngrn1a = np.int32(0)
        payload.species_names = np.array(
            [
                456,
                b"Calcite                 ",
                b"H2O(l)                  ",
                b"CO2(g)                  ",
                b"EM1                     SOLID1",
                b"EM2                     SOLID1",
            ],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-basis-name.d1")

    def test_data1_from_file_rejects_non_float64_basis_species_molar_weight(self):
        """
        Ensure Data1.from_file raises TypeError for a non-float64 molar weight in the basis-species loop.
        """
        payload = self._read_data1_payload()
        payload.narn1a = np.int32(0)
        payload.nmrn1a = np.int32(0)
        payload.nlrn1a = np.int32(0)
        payload.ngrn1a = np.int32(0)
        payload.species_molar_weights = np.array(
            [42, np.float64(100.09), np.float64(18.0), np.float64(44.01), np.float64(50.0), np.float64(70.0)],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-basis-weight.d1")

    def test_data1_from_file_rejects_non_float64_solid_solution_molar_weight(self):
        """
        Ensure Data1.from_file raises TypeError for a non-float64 molar weight in the solid-solution loop.
        """
        payload = self._read_data1_payload()
        payload.species_molar_weights = np.array(
            [np.float64(1.0), np.float64(100.09), np.float64(18.0), np.float64(44.01), 42, np.float64(70.0)],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-solid-solution-weight.d1")

    def test_data1_from_file_duplicate_end_member_raises(self):
        """
        Ensure duplicate solid-solution end members in read_data1 payload are rejected.
        """
        with mock.patch(
            "eleanor.kernel.eq36.data1.read_data1",
            return_value=self._read_data1_payload(duplicate_end_member=True),
        ):
            with self.assertRaises(RuntimeError):
                _ = Data1.from_file("dup.d1")

    def test_data1_from_file_rejects_non_bytes_element_names(self):
        """
        Ensure Data1.from_file rejects element names that are not bytes.
        """
        payload = self._read_data1_payload()
        payload.element_names = np.array(["H", b"O"], dtype=object)
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-elements.d1")

    def test_data1_from_file_rejects_non_bytes_species_names(self):
        """
        Ensure Data1.from_file rejects basis-species names that are not bytes.
        """
        payload = self._read_data1_payload()
        payload.species_names = np.array(
            [123, b"EM1                     SOLID1", b"EM2                     SOLID1"],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-species-name.d1")

    def test_data1_from_file_rejects_non_float64_composition_counts(self):
        """
        Ensure Data1.from_file rejects composition counts that are not np.float64.
        """
        payload = self._read_data1_payload()
        payload.cessa = np.array([2, 1])
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-counts.d1")

    def test_data1_from_file_preserves_nonzero_basis_species_volume(self):
        """
        Ensure Data1.from_file preserves nonzero basis-species volume values.
        """
        payload = self._read_data1_payload()
        payload.volumes = np.array([1.5, 0.0, 0.0, 0.0, 0.0, 0.0])
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            parsed = Data1.from_file("with-volume.d1")
        self.assertEqual(parsed.basis_species["H+"].volume, 1.5)

    def test_data1_from_file_rejects_non_bytes_solid_solution_lines(self):
        """
        Ensure Data1.from_file rejects solid-solution lines that are not bytes.
        """
        payload = self._read_data1_payload()
        payload.species_names = np.array(
            [
                b"H+                      ",
                b"Calcite                 ",
                b"H2O(l)                  ",
                b"CO2(g)                  ",
                b"EM1                     SOLID1",
                456,
            ],
            dtype=object,
        )
        with mock.patch("eleanor.kernel.eq36.data1.read_data1", return_value=payload):
            with self.assertRaises(TypeError):
                _ = Data1.from_file("bad-solid-solution-line.d1")

    def test_data1_get_basis_species_raises_on_multiple_matches(self):
        """
        Ensure get_basis_species rejects ambiguous element mappings with multiple matches.
        """
        d = Data1(
            filename="x",
            elements={"H": np.float64(1.0)},
            basis_species={
                "H+": BasisSpecies(name="H+", composition={"H": 1}, charge=1, volume=None, molar_mass=np.float64(1.0)),
                "H2+": BasisSpecies(
                    name="H2+",
                    composition={"H": 2},
                    charge=2,
                    volume=None,
                    molar_mass=np.float64(2.0),
                ),
            },
            aqueous_species={
                "H+": AqueousSpecies(name="H+", molar_mass=np.float64(1.0)),
                "H2+": AqueousSpecies(name="H2+", molar_mass=np.float64(2.0)),
            },
            minerals={},
            liquids={},
            gases={},
            solid_solutions={},
            tp_curve=None,
        )
        with self.assertRaises(Exception):
            _ = d.get_basis_species("H")

    def test_solid_solution_molar_mass(self):
        """
        Ensure SolidSolution molar mass supports defaults, custom fractions, and error cases.
        """
        from eleanor.kernel.eq36.data1 import SolidSolution

        ss = SolidSolution(
            name="SS",
            end_members={"A": np.float64(40.0), "B": np.float64(60.0)},
        )
        self.assertEqual(ss.molar_mass(mole_fractions={"A": np.float64(0.25), "B": np.float64(0.75)}), np.float64(55.0))
        self.assertEqual(ss.molar_mass({"A": np.float64(1.0), "B": np.float64(3.0)}), np.float64(55.0))

        with self.assertRaises(ValueError):
            _ = ss.molar_mass({})
        with self.assertRaises(KeyError):
            _ = ss.molar_mass({"A": np.float64(1.0), "C": np.float64(1.0)})
        with self.assertRaises(KeyError):
            _ = ss.molar_mass({"A": np.float64(1.0)})
        with self.assertRaises(ValueError):
            _ = ss.molar_mass({"A": np.float64(-0.5), "B": np.float64(1.5)})
        with self.assertRaises(ValueError):
            _ = ss.molar_mass({"A": np.float64(0.0), "B": np.float64(0.0)})
