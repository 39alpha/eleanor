from dataclasses import dataclass, field

import numpy as np
from eleanor.typing import NDArray, Optional

from .libeq36 import read_data1


@dataclass
class BasisSpecies(object):
    name: str
    composition: dict[str, int]
    charge: int
    volume: Optional[float]


@dataclass
class SolidSolution(object):
    name: str
    end_members: set[str]


@dataclass(init=False)
class TPCurve(object):
    T: dict[str, float]
    P: tuple[NDArray[float], NDArray[float]]
    domain: list[list[float]]

    def __init__(self, T, P):
        if not ('min' in T and 'mid' in T and 'max' in T):
            raise ValueError('temperature dictionary must have min, mid and max keys')

        if len(P) != 2:
            raise ValueError('expected exactly two polynomials')
        elif any(len(coeffs) == 0 for coeffs in P):
            raise ValueError('polynomial has no coefficients')

        self.P = P
        self.T = T
        self.domain = []

        if len(self.P) == 0:
            raise RuntimeError('interpolation coefficients for pressure not found')
        elif len(self.T) == 0:
            raise RuntimeError('interpolation coefficients for termperature not found')

        self.reset_domain()

        [coeff_left, coeff_right] = self.P
        left = np.dot(coeff_left, self.T['mid']**np.arange(len(coeff_left)))
        right = np.dot(coeff_right, self.T['mid']**np.arange(len(coeff_right)))

        if not np.isclose(left, right):
            raise ValueError('provided polynomials differ at the common temperature')

    def reset_domain(self):
        self.domain = [[self.T['min'], self.T['max']]]
        return self

    def temperature_in_domain(self, T):
        for subdomain in self.domain:
            if subdomain[0] <= T and T <= subdomain[1]:
                return True
        return False

    def __call__(self, T):
        if not self.temperature_in_domain(T):
            msg = f'the provided temperature ({T}) is not in the restricted domain {self.domain}'
            raise ValueError(msg)

        coefficients = self.P[0] if T <= self.T['mid'] else self.P[1]
        return np.dot(coefficients, T**np.arange(len(coefficients)))

    def set_domain(self, temperature_range, pressure_range):
        Tmin, Tmax = temperature_range
        Pmin, Pmax = pressure_range

        intersections = self.find_boundary_intersections(temperature_range, pressure_range)

        domain = []
        notEmpty = True
        if len(intersections) == 0:
            endpoints = 0
            for T in [self.T['min'], self.T['max']]:
                P = self(T)
                if Tmin <= T and T <= Tmax and Pmin <= P and P <= Pmax:
                    endpoints += 1

            if endpoints == 0:
                notEmpty = False
            elif endpoints == 1:
                msg = 'expected to find intersections or both points inside/outside region'
                raise Exception(msg)
            else:
                domain = [[self.T['min'], self.T['max']]]
        elif len(intersections) == 1:
            (Tint, _), = intersections
            is_single_point = True
            for T in [self.T['min'], self.T['mid'], self.T['max']]:
                if T == Tint or Tmax < T or T < Tmin:
                    continue

                P = self(T)
                if Pmin <= P and P <= Pmax:
                    domain.append([min(T, Tint), max(T, Tint)])
                    is_single_point = False

            if is_single_point:
                domain.append([Tint, Tint])
        else:
            for i in range(len(intersections) - 1):
                T1, _ = intersections[i]
                T2, _ = intersections[i + 1]
                P = self((T1 + T2) / 2)
                if Pmin <= P and P <= Pmax:
                    domain.append([T1, T2])

        self.domain = domain

        return notEmpty

    def find_boundary_intersections(self, temperature_range, pressure_range):
        Tmin, Tmax = temperature_range
        Pmin, Pmax = pressure_range

        intersections = []
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
                roots = np.real(roots[np.isreal(roots)])
                points = [(T, self(T)) for T in roots
                          if Tmin <= T and T <= Tmax and (i == 0 and self.T['min'] <= T and T <= self.T['mid']) or (
                              i == 1 and self.T['mid'] <= T and T <= self.T['max'])]
                intersections.extend(points)

        return sorted(set(intersections))

    @staticmethod
    def union_domains(curves):
        subdomains = []
        for curve in curves:
            for subdomain in curve.domain:
                subdomains.append(tuple(subdomain))
        subdomains = sorted(set(subdomains))

        if len(subdomains) == 0:
            return []

        domain = []
        (start, stop), *rest = subdomains
        for i in range(1, len(subdomains)):
            (a, b) = subdomains[i]
            if a <= stop and stop < b:
                stop = b
            elif stop < b:
                domain.append([start, stop])
                start, stop = a, b

        domain.append([start, stop])

        return domain

    @classmethod
    def sample(cls, curves, num_samples):
        domain = cls.union_domains(curves)
        domain_size = sum(map(lambda s: s[1] - s[0], domain))
        steps = [domain[i + 1][0] - domain[i][1] for i in range(len(domain) - 1)]

        Ts = np.random.uniform(0, domain_size, num_samples) + domain[0][0]
        Ps = []
        selected_curves = []
        for i, T in enumerate(Ts):
            for j, subdomain in enumerate(domain):
                if subdomain[1] >= T:
                    break
                else:
                    T += steps[j]

            Ts[i] = T = float(T)

            curves_above = [curve for curve in curves if curve.temperature_in_domain(T)]
            selected_index = np.random.randint(0, len(curves_above))
            selected_curve = curves_above[selected_index]

            P = float(selected_curve(T))
            Ps.append(P)

            selected_curves.append(selected_curve)

        return Ts, Ps, selected_curves


@dataclass
class Data1(object):
    filename: str
    elements: dict[str, float]
    basis_species: dict[str, BasisSpecies]
    solid_solutions: dict[str, SolidSolution]
    tp_curve: Optional[TPCurve]

    def get_basis_species(self, element: str) -> Optional[BasisSpecies]:
        basis_species = []
        for species in self.basis_species.values():
            if element in species.composition:
                basis_species.append(species)

        if len(basis_species) == 0:
            raise Exception(f'data1 file contains multiple basis species with element {element}')

        return None if not basis_species else basis_species[0]

    @classmethod
    def from_file(cls, filename: str):
        [
            min_temperature,
            max_temperature_by_range,
            pressure_coefficients,
            element_names,
            atomic_weights,
            species_names,
            cdrsa,
            charges,
            volumes,
            nessra,
            nessa,
            cessa,
            nxrn1a,
            nxrn2a,
        ] = read_data1(filename)

        T = {
            'min': min_temperature,
            'mid': max_temperature_by_range[0],
            'max': max_temperature_by_range[1],
        }
        P = [pressure_coefficients[:, 0], pressure_coefficients[:, 1]]
        tp_curve = TPCurve(T, P)

        elements = dict(zip(map(lambda e: e.strip(), element_names), atomic_weights))

        basis_species: dict[str, BasisSpecies] = dict()
        for i, (name, c, charge, volume) in enumerate(zip(species_names, cdrsa, charges, volumes)):
            if c != 0:
                break
            name = str(name[0:24].strip(), 'ascii')
            a, b = nessra[:, i]
            indices = nessa[a - 1:b]
            composition: dict[str, int] = dict()
            for element, count in zip(element_names[indices - 1], cessa[a - 1:b]):
                element = str(element.strip(), 'ascii')
                composition[element] = int(count)
            if volume == 0.0:
                volume = None
            basis_species[name] = BasisSpecies(name, composition, int(charge), volume)

        solid_solutions: dict[str, SolidSolution] = dict()
        for i in range(nxrn1a - 1, nxrn2a):
            end_member = str(species_names[i][:24].strip(), 'ascii')
            solid_solution = str(species_names[i][24:].strip(), 'ascii')
            if solid_solution in solid_solutions:
                if end_member in solid_solutions[solid_solution].end_members:
                    raise RuntimeError(
                        f'solid solution ({solid_solution}) end member ({end_member}) occurs multiple times')
                solid_solutions[solid_solution].end_members.add(end_member)
            else:
                solid_solutions[solid_solution] = SolidSolution(solid_solution, set([end_member]))

        return cls(filename, elements, basis_species, solid_solutions, tp_curve)
