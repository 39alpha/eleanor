# pyright: reportConstantRedefinition=false
from dataclasses import dataclass

import numpy as np

from eleanor.typing import Array1D, cast

from .libeq36 import read_data1

type FloatRange = tuple[float | np.float64, float | np.float64]
type CartesianCoord = tuple[float | np.float64, float | np.float64]


@dataclass
class BasisSpecies(object):
    name: str
    composition: dict[str, int]
    charge: int
    volume: float | None


@dataclass
class SolidSolution(object):
    name: str
    end_members: set[str]


@dataclass(init=False)
class TPCurve(object):
    T: dict[str, np.float64]
    P: tuple[Array1D[np.float64], Array1D[np.float64]]
    domain: list[FloatRange]

    def __init__(self, T: dict[str, np.float64], P: tuple[Array1D[np.float64], Array1D[np.float64]]):
        if not ("min" in T and "mid" in T and "max" in T):
            raise ValueError("temperature dictionary must have min, mid and max keys")

        if any(len(coeffs) == 0 for coeffs in P):
            raise ValueError("polynomial has no coefficients")

        self.P = P
        self.T = T
        self.domain = []

        _ = self.reset_domain()

        [coeff_left, coeff_right] = self.P

        tmp_left = cast(object, np.dot(coeff_left, self.T["mid"] ** np.arange(len(coeff_left))))
        if not isinstance(tmp_left, np.float64):
            raise TypeError(tmp_left)
        left = np.float64(tmp_left)

        tmp_right = cast(object, np.dot(coeff_right, self.T["mid"] ** np.arange(len(coeff_right))))
        if not isinstance(tmp_right, np.float64):
            raise TypeError(tmp_right)
        right = np.float64(tmp_right)

        if not np.isclose(left, right):
            raise ValueError("provided polynomials differ at the common temperature")

    def reset_domain(self):
        self.domain = [(self.T["min"], self.T["max"])]
        return self

    def temperature_in_domain(self, T: float | np.float32 | np.float64) -> bool:
        for subdomain in self.domain:
            if subdomain[0] <= T and T <= subdomain[1]:
                return True
        return False

    def __call__(self, T: float | np.float64) -> np.float64:
        if not self.temperature_in_domain(T):
            msg = f"the provided temperature ({T}) is not in the restricted domain {self.domain}"
            raise ValueError(msg)

        coefficients = self.P[0] if T <= self.T["mid"] else self.P[1]
        value = cast(object, np.dot(coefficients, T ** np.arange(len(coefficients))))
        if not isinstance(value, np.float64):
            raise TypeError(value)
        return np.float64(value)

    def set_domain(self, temperature_range: FloatRange, pressure_range: FloatRange):
        Tmin, Tmax = temperature_range
        Pmin, Pmax = pressure_range

        intersections = self.find_boundary_intersections(temperature_range, pressure_range)

        domain: list[FloatRange] = []
        notEmpty = True
        if len(intersections) == 0:
            endpoints = 0
            for T in [self.T["min"], self.T["max"]]:
                P = self(T)
                if Tmin <= T and T <= Tmax and Pmin <= P and P <= Pmax:
                    endpoints += 1

            if endpoints == 0:
                notEmpty = False
            elif endpoints == 1:
                msg = "expected to find intersections or both points inside/outside region"
                raise Exception(msg)
            else:
                domain = [(self.T["min"], self.T["max"])]
        elif len(intersections) == 1:
            ((Tint, _),) = intersections
            is_single_point = True
            for T in [self.T["min"], self.T["mid"], self.T["max"]]:
                if T == Tint or Tmax < T or T < Tmin:
                    continue

                P = self(T)
                if Pmin <= P and P <= Pmax:
                    domain.append((min(T, Tint), max(T, Tint)))
                    is_single_point = False

            if is_single_point:
                domain.append((Tint, Tint))
        else:
            for i in range(len(intersections) - 1):
                T1, _ = intersections[i]
                T2, _ = intersections[i + 1]
                P = self((T1 + T2) / 2)
                if Pmin <= P and P <= Pmax:
                    domain.append((T1, T2))

        self.domain = domain

        return notEmpty

    def find_boundary_intersections(
        self, temperature_range: FloatRange, pressure_range: FloatRange
    ) -> list[CartesianCoord]:
        Tmin, Tmax = temperature_range
        Pmin, Pmax = pressure_range

        intersections: list[CartesianCoord] = []
        for T in temperature_range:
            if not self.temperature_in_domain(T):
                continue

            P = self(T)
            if Pmin <= P and P <= Pmax:
                intersections.append((T, P))

        for P in pressure_range:
            for i, coefficients in enumerate(self.P):
                coefficients = np.copy(coefficients)
                coefficients[0] -= P
                roots = np.roots(coefficients[::-1])
                real_roots: Array1D[np.float64] = np.asarray(np.real(roots[np.isreal(roots)]), dtype=np.float64)
                for T in real_roots:
                    if (
                        Tmin <= T
                        and T <= Tmax
                        and (i == 0 and self.T["min"] <= T and T <= self.T["mid"])
                        or (i == 1 and self.T["mid"] <= T and T <= self.T["max"])
                    ):
                        intersections.append((T, self(T)))

        return sorted(set(intersections))

    @staticmethod
    def union_domains(curves: list[TPCurve]) -> list[FloatRange]:
        subdomains: list[FloatRange] = []
        for curve in curves:
            for subdomain in curve.domain:
                subdomains.append(subdomain)
        subdomains = sorted(set(subdomains))

        if len(subdomains) == 0:
            return subdomains

        domain: list[FloatRange] = []
        (start, stop), *_rest = subdomains
        for i in range(1, len(subdomains)):
            (a, b) = subdomains[i]
            if a <= stop and stop < b:
                stop = b
            elif stop < b:
                domain.append((start, stop))
                start, stop = a, b

        domain.append((start, stop))

        return domain

    @classmethod
    def sample(
        cls, curves: list[TPCurve], num_samples: int
    ) -> tuple[Array1D[np.float64], Array1D[np.float64], list[TPCurve]]:
        domain = cls.union_domains(curves)
        domain_size = sum(map(lambda s: s[1] - s[0], domain))
        steps = [domain[i + 1][0] - domain[i][1] for i in range(len(domain) - 1)]

        Ts: Array1D[np.float64] = np.random.uniform(0, domain_size, num_samples) + domain[0][0]
        Ps: list[np.float64] = []
        selected_curves: list[TPCurve] = []
        for i, T in enumerate(Ts):
            for j, subdomain in enumerate(domain):
                if subdomain[1] >= T:
                    break
                else:
                    T += steps[j]

            Ts[i] = T

            curves_above = [curve for curve in curves if curve.temperature_in_domain(T)]
            selected_index = np.random.randint(0, len(curves_above))
            selected_curve = curves_above[selected_index]

            P = selected_curve(T)
            Ps.append(P)

            selected_curves.append(selected_curve)

        return Ts, np.asarray(Ps), selected_curves


@dataclass
class Data1(object):
    filename: str
    elements: dict[str, np.float64]
    basis_species: dict[str, BasisSpecies]
    solid_solutions: dict[str, SolidSolution]
    tp_curve: TPCurve | None

    def get_basis_species(self, element: str) -> BasisSpecies | None:
        basis_species: list[BasisSpecies] = []
        for species in self.basis_species.values():
            if element in species.composition:
                basis_species.append(species)

        if len(basis_species) > 1:
            raise Exception(f"data1 file contains multiple basis species with element {element}")

        return None if not basis_species else basis_species[0]

    @classmethod
    def from_file(cls, filename: str):
        data = read_data1(filename)

        T: dict[str, np.float64] = {
            "min": data.min_temperature,
            "mid": data.max_temperature_range[0],
            "max": data.max_temperature_range[1],
        }
        P = (data.pressure_coefficients[:, 0], data.pressure_coefficients[:, 1])
        tp_curve = TPCurve(T, P)

        element_names: list[str] = []
        elements: dict[str, np.float64] = {}
        for raw_name_obj, weight in zip(cast(list[object], list(data.element_names)), data.atomic_weights):
            if not isinstance(raw_name_obj, bytes):
                raise TypeError(raw_name_obj)
            name = str(raw_name_obj.strip(), "ascii")
            element_names.append(name)
            elements[name] = weight

        basis_species: dict[str, BasisSpecies] = dict()
        for i, (raw_species_name_obj, c, charge, volume) in enumerate(
            zip(cast(list[object], list(data.species_names)), data.cdrsa, data.charges, data.volumes)
        ):
            if not isinstance(raw_species_name_obj, bytes):
                raise TypeError(raw_species_name_obj)

            if c != 0:
                break
            name = str(raw_species_name_obj[0:24].strip(), "ascii")
            a = int(cast(np.int32, data.nessra[0, i]))
            b = int(cast(np.int32, data.nessra[1, i]))
            indices = cast(Array1D[np.int32], data.nessa[a - 1 : b])
            composition: dict[str, int] = dict()
            selected_elements = [element_names[int(idx) - 1] for idx in indices]
            counts = cast(list[object], list(data.cessa[a - 1 : b]))
            for element, count in zip(selected_elements, counts):
                if not isinstance(count, np.float64):
                    raise TypeError(count)
                # TODO: Is this conversion correct? Can the compositions be non-integers?
                composition[element] = int(count)
            if volume == 0.0:
                basis_species[name] = BasisSpecies(name, composition, int(charge), None)
            else:
                basis_species[name] = BasisSpecies(name, composition, int(charge), volume)

        solid_solutions: dict[str, SolidSolution] = dict()
        for i in range(data.nxrn1a - 1, data.nxrn2a):
            line = cast(object, data.species_names[i])
            if not isinstance(line, bytes):
                raise TypeError(line)

            end_member = str(line[:24].strip(), "ascii")
            solid_solution = str(line[24:].strip(), "ascii")
            if solid_solution in solid_solutions:
                if end_member in solid_solutions[solid_solution].end_members:
                    raise RuntimeError(
                        f"solid solution ({solid_solution}) end member ({end_member}) occurs multiple times"
                    )
                solid_solutions[solid_solution].end_members.add(end_member)
            else:
                solid_solutions[solid_solution] = SolidSolution(solid_solution, set([end_member]))

        return cls(filename, elements, basis_species, solid_solutions, tp_curve)
