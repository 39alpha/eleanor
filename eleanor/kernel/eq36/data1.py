from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast

import numpy as np

from eleanor.kernel.eq36.libeq36 import read_data1
from eleanor.typing import Array1D, StrPath

type FloatRange = tuple[np.float64, np.float64]
type CartesianCoord = tuple[np.float64, np.float64]


@dataclass(init=False)
class Species:
    name: str
    molar_mass: np.float64

    def __init__(self, *, name: str, molar_mass: np.float64) -> None:
        self.name = name
        self.molar_mass = molar_mass

        if self.name == "":
            msg = "cannot construct Species with empty name"
            raise ValueError(msg)

        if self.molar_mass < 0:
            msg = "cannot construct Species with negative molar mass"
            raise ValueError(msg)


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
    ) -> None:
        super().__init__(name=name, molar_mass=molar_mass)
        self.composition = composition
        self.charge = charge
        self.volume = volume

        if not self.composition:
            msg = "cannot construct BasisSpecies with an empty composition"
            raise ValueError(msg)

        for count in self.composition.values():
            if count < 0:
                msg = "cannot construct a BasisSpecies with a component with negative count"
                raise ValueError(msg)

        if self.volume is not None and self.volume < 0:
            msg = "cannot construct a BasisSpecies with negative volume"
            raise ValueError(msg)


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

    def __init__(self, *, name: str, end_members: dict[str, np.float64]) -> None:
        self.name = name
        self.end_members = end_members

        if self.name == "":
            msg = "cannot construct SolidSolution with empty name"
            raise ValueError(msg)

        if not self.end_members:
            msg = "cannot construct SolidSolution without end members"
            raise ValueError(msg)

        for molar_mass in self.end_members.values():
            if molar_mass < 0:
                msg = "cannot construct SolidSolution with negative end member molar mass"
                raise ValueError(msg)

    def molar_mass(self, mole_fractions: dict[str, np.float64]) -> np.float64:
        if not mole_fractions:
            msg = "no mole_fractions provided"
            raise ValueError(msg)

        missing = set(mole_fractions) - set(self.end_members)
        if missing:
            msg = f"unknown end member(s) for solid solution {self.name!r}: {sorted(missing)}"
            raise KeyError(msg)

        missing = set(self.end_members) - set(mole_fractions)
        if missing:
            msg = f"missing mole fractions for end member(s) for solid solution {self.name!r}: {sorted(missing)}"
            raise KeyError(msg)

        for end_member, fraction in mole_fractions.items():
            if fraction < 0.0:
                msg = f"mole fraction for solid solution {self.name!r} end member {end_member!r} is negative"
                raise ValueError(msg)

        total = sum(mole_fractions.values())
        if total <= 0:
            msg = f"mole fractions for solid solution {self.name!r} must sum to a positive value"
            raise ValueError(msg)

        weighted = np.float64(0.0)
        for name, fraction in mole_fractions.items():
            weighted += fraction * self.end_members[name]
        return weighted / total


@dataclass(init=False)
class TPCurve:
    temperature: dict[str, np.float64]
    pressure: tuple[Array1D[np.float64], Array1D[np.float64]]
    domain: list[FloatRange]

    def __init__(self, temp: dict[str, np.float64], press: tuple[Array1D[np.float64], Array1D[np.float64]]) -> None:
        if not ("min" in temp and "mid" in temp and "max" in temp):
            msg = "temperature dictionary must have min, mid and max keys"
            raise ValueError(msg)

        if any(len(coeffs) == 0 for coeffs in press):
            msg = "polynomial has no coefficients"
            raise ValueError(msg)

        self.pressure = press
        self.temperature = temp
        self.domain = []

        _ = self.reset_domain()

        [coeff_left, coeff_right] = self.pressure

        tmp_left = cast(object, np.dot(coeff_left, self.temperature["mid"] ** np.arange(len(coeff_left))))
        if not isinstance(tmp_left, np.float64):
            raise TypeError(tmp_left)
        left = tmp_left

        tmp_right = cast(object, np.dot(coeff_right, self.temperature["mid"] ** np.arange(len(coeff_right))))
        if not isinstance(tmp_right, np.float64):
            raise TypeError(tmp_right)
        right = tmp_right

        if not np.isclose(left, right):
            msg = "provided polynomials differ at the common temperature"
            raise ValueError(msg)

    def reset_domain(self) -> Self:
        self.domain = [(self.temperature["min"], self.temperature["max"])]
        return self

    def temperature_in_domain(self, temp: np.float64) -> bool:
        return any(subdomain[0] <= temp <= subdomain[1] for subdomain in self.domain)

    def __call__(self, temp: np.float64) -> np.float64:
        if not self.temperature_in_domain(temp):
            msg = f"the provided temperature ({temp}) is not in the restricted domain {self.domain}"
            raise ValueError(msg)

        coefficients = self.pressure[0] if temp <= self.temperature["mid"] else self.pressure[1]
        value = cast(object, np.dot(coefficients, temp ** np.arange(len(coefficients))))
        if not isinstance(value, np.float64):
            raise TypeError(value)
        return value

    def set_domain(self, temperature_range: FloatRange, pressure_range: FloatRange) -> bool:
        temp_min, temp_max = temperature_range
        press_min, press_max = pressure_range

        intersections = self.find_boundary_intersections(temperature_range, pressure_range)

        domain: list[FloatRange] = []
        not_empty = True
        if len(intersections) == 0:
            endpoints = 0
            for temp in [self.temperature["min"], self.temperature["max"]]:
                press = self(temp)
                if temp_min <= temp <= temp_max and press_min <= press <= press_max:
                    endpoints += 1

            if endpoints == 0:
                not_empty = False
            elif endpoints == 1:
                msg = "expected to find intersections or both points inside/outside region"
                raise Exception(msg)
            else:
                domain = [(self.temperature["min"], self.temperature["max"])]
        elif len(intersections) == 1:
            ((temp_intersect, _),) = intersections
            is_single_point = True
            for temp in [self.temperature["min"], self.temperature["mid"], self.temperature["max"]]:
                if temp == temp_intersect or not (temp_min <= temp <= temp_max):
                    continue

                press = self(temp)
                if press_min <= press <= press_max:
                    domain.append((min(temp, temp_intersect), max(temp, temp_intersect)))
                    is_single_point = False

            if is_single_point:
                domain.append((temp_intersect, temp_intersect))
        else:
            for i in range(len(intersections) - 1):
                temp_1, _ = intersections[i]
                temp_2, _ = intersections[i + 1]
                press = self((temp_1 + temp_2) / 2)
                if press_min <= press <= press_max:
                    domain.append((temp_1, temp_2))

        self.domain = domain

        return not_empty

    def find_boundary_intersections(
        self,
        temperature_range: FloatRange,
        pressure_range: FloatRange,
    ) -> list[CartesianCoord]:
        temp_min, temp_max = temperature_range
        press_min, press_max = pressure_range

        intersections = [
            (temp, press)
            for temp in temperature_range
            if self.temperature_in_domain(temp) and press_min <= (press := self(temp)) <= press_max
        ]

        for press in pressure_range:
            for i, coefficients in enumerate(self.pressure):
                if i == 0:
                    temp_bounds = self.temperature["min"], self.temperature["mid"]
                elif i == 1:
                    temp_bounds = self.temperature["mid"], self.temperature["max"]
                else:
                    # This should never raise as __init__ ensures that len(self.pressure) == 2
                    msg = "temperature-pressure curve has more than two domains"
                    raise RuntimeError(msg)

                coeff = np.copy(coefficients)
                coeff[0] -= press
                roots = np.roots(coeff[::-1])
                real_roots: Array1D[np.float64] = np.asarray(np.real(roots[np.isreal(roots)]), dtype=np.float64)

                intersections.extend(
                    (temp, press)
                    for temp in real_roots
                    if temp_min <= temp <= temp_max
                    and temp_bounds[0] <= temp <= temp_bounds[1]
                    and self.temperature_in_domain(temp)
                    and press_min <= (press := self(temp)) <= press_max
                )

        return sorted(set(intersections))

    @staticmethod
    def union_domains(curves: list[TPCurve]) -> list[FloatRange]:
        subdomains = [subdomain for curve in curves for subdomain in curve.domain]
        subdomains = sorted(set(subdomains))

        if len(subdomains) == 0:
            return subdomains

        domain: list[FloatRange] = []
        (start, stop), *_rest = subdomains
        for i in range(1, len(subdomains)):
            (a, b) = subdomains[i]
            if a <= stop < b:
                stop = b
            elif stop < b:
                domain.append((start, stop))
                start, stop = a, b

        domain.append((start, stop))

        return domain

    @classmethod
    def sample(
        cls, curves: list[TPCurve], num_samples: int, *, rng: np.random.Generator | None = None
    ) -> tuple[Array1D[np.float64], Array1D[np.float64], list[TPCurve]]:
        if rng is None:
            rng = np.random.default_rng()

        domain = cls.union_domains(curves)
        domain_size = sum(s[1] - s[0] for s in domain)
        steps = [domain[i + 1][0] - domain[i][1] for i in range(len(domain) - 1)]

        temps: Array1D[np.float64] = rng.uniform(0, domain_size, num_samples) + domain[0][0]
        presses: list[np.float64] = []
        selected_curves: list[TPCurve] = []
        for i in range(len(temps)):
            temp = cast(np.float64, temps[i])
            for j, subdomain in enumerate(domain):
                if subdomain[1] >= temp:
                    break
                temp += steps[j]
            temps[i] = temp

            curves_above = [curve for curve in curves if curve.temperature_in_domain(temp)]
            selected_index = rng.integers(0, len(curves_above))
            selected_curve = curves_above[selected_index]

            press = selected_curve(temp)
            presses.append(press)

            selected_curves.append(selected_curve)

        return temps, np.asarray(presses), selected_curves


@dataclass
class Data1:
    filename: Path
    elements: dict[str, np.float64]
    basis_species: dict[str, BasisSpecies]
    aqueous_species: dict[str, AqueousSpecies]
    minerals: dict[str, Mineral]
    liquids: dict[str, Liquid]
    gases: dict[str, Gas]
    solid_solutions: dict[str, SolidSolution]
    tp_curve: TPCurve | None

    def get_basis_species(self, element: str) -> BasisSpecies | None:
        basis_species = [species for species in self.basis_species.values() if element in species.composition]

        if len(basis_species) > 1:
            msg = f"data1 file contains multiple basis species with element {element}"
            raise Exception(msg)

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
                msg = "mole_fractions is required to get the molar_mass of a solid solution"
                raise ValueError(msg)
            return self.solid_solutions[name].molar_mass(mole_fractions)
        for category in (self.aqueous_species, self.minerals, self.liquids, self.gases):
            if name in category:
                return category[name].molar_mass
        for solid_solution in self.solid_solutions.values():
            if name in solid_solution.end_members:
                return solid_solution.end_members[name]
        msg = f"no species named {name!r} in {self.filename}"
        raise KeyError(msg)

    def compute_molar_mass(self, composition: dict[str, int]) -> np.float64:
        """Compute a molar mass from an element-count composition.

        Uses the element atomic weights parsed from the data1 file. Useful for
        custom species not present in the database or for cross-checking
        ``molar_mass`` lookups.
        """
        if not composition:
            msg = "composition must contain at least one element"
            raise ValueError(msg)

        total = np.float64(0.0)
        for element, count in composition.items():
            if element not in self.elements:
                msg = f"unknown element {element!r}"
                raise KeyError(msg)
            if count < 0:
                msg = f"{element!r} has negative count"
                raise ValueError(msg)
            total += np.float64(count) * self.elements[element]
        return total

    @classmethod
    def from_file(cls, filename: StrPath) -> Self:
        filename = Path(filename)

        data = read_data1(filename)

        temp: dict[str, np.float64] = {
            "min": data.min_temperature,
            "mid": data.max_temperature_range[0],
            "max": data.max_temperature_range[1],
        }
        press = (data.pressure_coefficients[:, 0], data.pressure_coefficients[:, 1])
        tp_curve = TPCurve(temp, press)

        element_names: list[str] = []
        elements: dict[str, np.float64] = {}
        for raw_name_obj, weight in zip(
            cast(list[object], list(data.element_names)),
            data.atomic_weights,
            strict=True,
        ):
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

        def _make_species[S: Species](
            start: np.int32,
            stop: np.int32,
            factory: Callable[..., S],
        ) -> dict[str, S]:
            result: dict[str, S] = {}
            if int(start) <= 0 or int(stop) <= 0:
                return result
            for idx in range(int(start) - 1, int(stop)):
                weight = cast(object, data.species_molar_weights[idx])
                if not isinstance(weight, np.float64):
                    raise TypeError(weight)
                name = _species_name(idx)
                result[name] = factory(name=name, molar_mass=weight)
            return result

        aqueous_species = _make_species(data.narn1a, data.narn2a, AqueousSpecies)
        minerals = _make_species(data.nmrn1a, data.nmrn2a, Mineral)
        liquids = _make_species(data.nlrn1a, data.nlrn2a, Liquid)
        gases = _make_species(data.ngrn1a, data.ngrn2a, Gas)

        basis_species: dict[str, BasisSpecies] = {}
        for i, (raw_species_name_obj, c, charge, volume) in enumerate(
            zip(
                cast(list[object], list(data.species_names)),
                data.cdrsa,
                data.charges,
                data.volumes,
                strict=False,
            ),
        ):
            if not isinstance(raw_species_name_obj, bytes):
                raise TypeError(raw_species_name_obj)

            if c != 0:
                break
            name = str(raw_species_name_obj[0:24].strip(), "ascii")
            a = int(cast(np.int32, data.nessra[0, i]))
            b = int(cast(np.int32, data.nessra[1, i]))
            indices = cast(Array1D[np.int32], data.nessa[a - 1 : b])
            composition: dict[str, int] = {}
            selected_elements = [element_names[int(idx) - 1] for idx in indices]
            counts = cast(list[object], list(data.cessa[a - 1 : b]))
            for element, count in zip(selected_elements, counts, strict=False):
                if not isinstance(count, np.float64):
                    raise TypeError(count)
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

        solid_solutions: dict[str, SolidSolution] = {}
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
                    msg = f"solid solution ({solid_solution}) end member ({end_member}) occurs multiple times"
                    raise RuntimeError(msg)
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
