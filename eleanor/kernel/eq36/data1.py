# pyright: reportConstantRedefinition=false
from dataclasses import dataclass
from typing import TypedDict, cast

import numpy as np

from eleanor.kernel.eq36.libeq36 import read_data1
from eleanor.typing import Array1D

type FloatRange = tuple[np.float64, np.float64]
type CartesianCoord = tuple[np.float64, np.float64]


class _SpeciesRaw(TypedDict):
    name: str
    molar_mass: np.float64


@dataclass(init=False)
class Species:
    name: str
    molar_mass: np.float64

    def __init__(self, *, name: str, molar_mass: np.float64):
        self.name = name
        self.molar_mass = molar_mass

        if self.name == "":
            raise ValueError("cannot construct Species with empty name")

        if self.molar_mass < 0:
            raise ValueError("cannot construct Species with negative molar mass")


@dataclass(init=False)
class BasisSpecies(Species):
    composition: dict[str, int]
    charge: int
    volume: np.float64 | None

    def __init__(
        self,
        *,
        name: str,
        molar_mass: np.float64,
        composition: dict[str, int],
        charge: int,
        volume: np.float64 | None,
    ):
        super().__init__(name=name, molar_mass=molar_mass)
        self.composition = composition
        self.charge = charge
        self.volume = volume

        if not self.composition:
            raise ValueError("cannot construct BasisSpecies with an empty composition")

        for count in self.composition.values():
            if count < 0:
                raise ValueError("cannot construct a BasisSpecies with a component with negative count")

        if self.volume is not None and self.volume < 0:
            raise ValueError("cannot construct a BasisSpecies with negative volume")


@dataclass(init=False)
class AqueousSpecies(Species):
    pass


@dataclass(init=False)
class Mineral(Species):
    pass


@dataclass(init=False)
class Liquid(Species):
    pass


@dataclass(init=False)
class Gas(Species):
    pass


@dataclass(init=False)
class SolidSolution:
    name: str
    end_members: dict[str, np.float64]

    def __init__(self, *, name: str, end_members: dict[str, np.float64]):
        self.name = name
        self.end_members = end_members

        if self.name == "":
            raise ValueError("cannot construct SolidSolution with empty name")

        if not self.end_members:
            raise ValueError("cannot construct SolidSolution without end members")

        for molar_mass in self.end_members.values():
            if molar_mass < 0:
                raise ValueError("cannot construct SolidSolution with negative end member molar mass")

    def molar_mass(self, mole_fractions: dict[str, np.float64]) -> np.float64:
        if not mole_fractions:
            raise ValueError("no mole_fractions provided")

        missing = set(mole_fractions) - set(self.end_members)
        if missing:
            raise KeyError(f"unknown end member(s) for solid solution {self.name!r}: {sorted(missing)}")

        missing = set(self.end_members) - set(mole_fractions)
        if missing:
            raise KeyError(
                f"missing mole fractions for end member(s) for solid solution {self.name!r}: {sorted(missing)}"
            )

        for end_member, fraction in mole_fractions.items():
            if fraction < 0.0:
                raise ValueError(
                    f"mole fraction for solid solution {self.name!r} end member {end_member!r} is negative"
                )

        total = sum(mole_fractions.values())
        if total <= 0:
            raise ValueError(f"mole fractions for solid solution {self.name!r} must sum to a positive value")

        weighted = np.float64(0.0)
        for name, fraction in mole_fractions.items():
            weighted += fraction * self.end_members[name]
        return weighted / total


@dataclass(init=False)
class TPCurve:
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
        left = tmp_left

        tmp_right = cast(object, np.dot(coeff_right, self.T["mid"] ** np.arange(len(coeff_right))))
        if not isinstance(tmp_right, np.float64):
            raise TypeError(tmp_right)
        right = tmp_right

        if not np.isclose(left, right):
            raise ValueError("provided polynomials differ at the common temperature")

    def reset_domain(self):
        self.domain = [(self.T["min"], self.T["max"])]
        return self

    def temperature_in_domain(self, T: np.float64) -> bool:
        for subdomain in self.domain:
            if subdomain[0] <= T and T <= subdomain[1]:
                return True
        return False

    def __call__(self, T: np.float64) -> np.float64:
        if not self.temperature_in_domain(T):
            msg = f"the provided temperature ({T}) is not in the restricted domain {self.domain}"
            raise ValueError(msg)

        coefficients = self.P[0] if T <= self.T["mid"] else self.P[1]
        value = cast(object, np.dot(coefficients, T ** np.arange(len(coefficients))))
        if not isinstance(value, np.float64):
            raise TypeError(value)
        return value

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
class Data1:
    filename: str
    elements: dict[str, np.float64]
    basis_species: dict[str, BasisSpecies]
    aqueous_species: dict[str, AqueousSpecies]
    minerals: dict[str, Mineral]
    liquids: dict[str, Liquid]
    gases: dict[str, Gas]
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

    def molar_mass(
        self,
        name: str,
        mole_fractions: dict[str, np.float64] | None = None,
    ) -> np.float64:
        """Return the molar mass (g/mol) of any species in the database.

        Looks up *name* across aqueous species, pure minerals, pure liquids,
        gases, and solid-solution end members. For a solid solution, supply
        *mole_fractions* (end-member name -> fraction).
        """
        if name in self.solid_solutions:
            if mole_fractions is None:
                raise ValueError("mole_fractions is required to get the molar_mass of a solid solution")
            return self.solid_solutions[name].molar_mass(mole_fractions)
        for category in (self.aqueous_species, self.minerals, self.liquids, self.gases):
            if name in category:
                return category[name].molar_mass
        for solid_solution in self.solid_solutions.values():
            if name in solid_solution.end_members:
                return solid_solution.end_members[name]
        raise KeyError(f"no species named {name!r} in {self.filename}")

    def compute_molar_mass(self, composition: dict[str, int]) -> np.float64:
        """Compute a molar mass from an element-count composition.

        Uses the element atomic weights parsed from the data1 file. Useful for
        custom species not present in the database or for cross-checking
        ``molar_mass`` lookups.
        """
        if not composition:
            raise ValueError("composition must contain at least one element")

        total = np.float64(0.0)
        for element, count in composition.items():
            if element not in self.elements:
                raise KeyError(f"unknown element {element!r}")
            if count < 0:
                raise ValueError(f"{element!r} has negative count")
            total += np.float64(count) * self.elements[element]
        return total

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

        def _species_name(idx: int) -> str:
            raw = cast(object, data.species_names[idx])
            if not isinstance(raw, bytes):
                raise TypeError(raw)
            return str(raw[:24].strip(), "ascii")

        def _raw_species(start: np.int32, stop: np.int32) -> dict[str, _SpeciesRaw]:
            result: dict[str, _SpeciesRaw] = {}
            if int(start) <= 0 or int(stop) <= 0:
                return result
            for idx in range(int(start) - 1, int(stop)):
                weight = cast(object, data.species_molar_weights[idx])
                if not isinstance(weight, np.float64):
                    raise TypeError(weight)
                name = _species_name(idx)
                result[name] = {"name": name, "molar_mass": weight}
            return result

        aqueous_species = {k: AqueousSpecies(**v) for k, v in _raw_species(data.narn1a, data.narn2a).items()}
        minerals = {k: Mineral(**v) for k, v in _raw_species(data.nmrn1a, data.nmrn2a).items()}
        liquids = {k: Liquid(**v) for k, v in _raw_species(data.nlrn1a, data.nlrn2a).items()}
        gases = {k: Gas(**v) for k, v in _raw_species(data.ngrn1a, data.ngrn2a).items()}

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
            molar_mass_obj = cast(object, data.species_molar_weights[i])
            if not isinstance(molar_mass_obj, np.float64):
                raise TypeError(molar_mass_obj)
            mass = molar_mass_obj
            resolved_volume: np.float64 | None = None if volume == 0.0 else volume
            basis_species[name] = BasisSpecies(
                name=name,
                molar_mass=mass,
                composition=composition,
                charge=int(charge),
                volume=resolved_volume,
            )

        solid_solutions: dict[str, SolidSolution] = dict()
        for i in range(int(data.nxrn1a) - 1, int(data.nxrn2a)):
            line = cast(object, data.species_names[i])
            if not isinstance(line, bytes):
                raise TypeError(line)

            end_member = str(line[:24].strip(), "ascii")
            solid_solution = str(line[24:].strip(), "ascii")
            end_member_mass_obj = cast(object, data.species_molar_weights[i])
            if not isinstance(end_member_mass_obj, np.float64):
                raise TypeError(end_member_mass_obj)
            end_member_mass = end_member_mass_obj
            if solid_solution in solid_solutions:
                if end_member in solid_solutions[solid_solution].end_members:
                    raise RuntimeError(
                        f"solid solution ({solid_solution}) end member ({end_member}) occurs multiple times"
                    )
                solid_solutions[solid_solution].end_members[end_member] = end_member_mass
            else:
                solid_solutions[solid_solution] = SolidSolution(
                    name=solid_solution,
                    end_members={end_member: end_member_mass},
                )

        return cls(
            filename,
            elements,
            basis_species,
            aqueous_species,
            minerals,
            liquids,
            gases,
            solid_solutions,
            tp_curve,
        )
