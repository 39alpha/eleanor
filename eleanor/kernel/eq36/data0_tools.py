import io
import os
import os.path
import re
import shutil
import sys
from tempfile import TemporaryDirectory

import numpy as np

from eleanor.typing import Optional, Species
from eleanor.util import WorkingDirectory, find_files, hash_dir

from . import util
from .exec import eqpt


def determine_species(
        file: Optional[str | io.TextIOWrapper] = None) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    if file is None:
        return determine_species('problem.3o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return determine_species(file)

    suppress = []
    elements = []
    aqueous_species = []
    solids = []
    solid_solutions = []
    gases = []

    lines = file.readlines()

    # gather suppress info from near the top of the
    for i in range(len(lines)):
        if ' * Alter/suppress options' in lines[i]:
            # number of suppression options
            supp_n = int(lines[i + 1].split()[-1])
            # print(supp_n)
            for j in range(1, supp_n + 1):
                suppress.append(lines[i + 2 * j][12:].strip())
            break

    # search for all other info from teh bottom of the file
    for i in range(len(lines) - 1, 0, -1):
        # find the beginning of the print section for the final system composition.
        if ' Done. Hybrid Newton-Raphson iteration converged in ' in lines[i]:
            break

    # now count forward in lines against to read the system composition
    while i < len(lines):
        if re.findall('^\n', lines[i]):
            i += 1
        elif '           --- Elemental Composition of the Aqueous Solution ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                ele = lines[i][:13].strip()
                if ele not in ['O', 'H']:
                    if float(lines[i].split()[1]) == 0.0:
                        # element not loaded (ie. Cl). this shows up in
                        # the eq3 element set even if set to 0.
                        pass
                    else:
                        elements.append(ele)
                    i += 1
                else:
                    i += 1

        elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                name = lines[i][:26].strip()
                # O2(g) is a ficticious aqueous species
                if name != 'O2(g)':
                    aqueous_species.append(name)
                i += 1
        elif '           --- Saturation States of Pure Solids ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                if 'None' not in lines[i]:
                    solids.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif '--- Saturation States of Solid Solutions ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                if 'None' not in lines[i]:
                    solid_solutions.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif '--- Fugacities ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                gases.append(lines[i][:26].strip())
                i += 1

            break

        else:
            i += 1

    # without knowing which lists contain the suppressions, they all must be searched
    elements = [element for element in elements if element not in suppress]
    aqueous_species = [species for species in aqueous_species if species not in suppress]
    solids = [solid for solid in solids if solid not in suppress]
    solid_solutions = [solid_solution for solid_solution in solid_solutions if solid_solutions not in suppress]
    gases = [gas for gas in gases if gas not in suppress]

    return elements, aqueous_species, solids, solid_solutions, gases


def determine_loaded_sp(file: Optional[str | io.TextIOWrapper] = None):
    if file is None:
        return determine_loaded_sp('problem.3o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return determine_loaded_sp(handle)

    loaded_sp = []

    lines = file.readlines()
    grab_loaded_sp = False
    for line_num in range(len(lines)):
        # These only appear if verbose 'v' is set with local_3i.write() above
        if ' --- Listing of Species and Reactions ---' in lines[line_num]:
            grab_loaded_sp = True
        elif ' - - BEGIN ITERATIVE CALCULATIONS  - - - ' in lines[line_num]:
            break
        elif grab_loaded_sp and '------------------' in lines[line_num]:
            # The two options below avoid the 'BEGIN ITERATIVE . .' which is also caught with the above string.
            if '1.000' in lines[line_num + 2]:
                # Exclude basis species
                #
                # Grab full string (with spaces) after the stoichiometry this correctly differentiates solid
                # solution end-members from their stand alone counterparts ie: 'CA-SAPONITE' vs 'CA-SAPONITE
                # (SAPONITE)'
                loaded_sp.append(lines[line_num + 2].split('1.000  ')[-1].strip())
            elif 'is a strict' in lines[line_num + 2]:
                # Grab the basis species
                loaded_sp.append(lines[line_num + 2].split(' is a strict ')[0].strip())

    # O2(g) shows up as a strict basis species, and again with the gasses so its basis form is removed here. Also,
    # H2O shows up 2 times, and regardless is separately tracked via the aH2O variable.
    loaded_sp = [species for species in loaded_sp if species not in ['H2O', 'O2(g)']]

    # Alter loaded_sp to reflect correct search names required for 6o
    aqueous_and_solid_species = [species for species in loaded_sp if ' (' not in species]
    solid_solutions_and_gases = [species for species in loaded_sp if ' (' in species]
    gases = [species.split(' (')[0] for species in solid_solutions_and_gases if '(Gas)' in species]
    solid_solutions = [
        species.split(' (')[1].strip(')(') for species in solid_solutions_and_gases if '(Gas)' not in species
    ]

    species = aqueous_and_solid_species + gases
    solid_solutions = list(set(solid_solutions))

    return species, solid_solutions


def data0_TP(suffix):
    """
    return T/P range of a data0 file given its suffix
    """
    t = suffix[0]
    p = suffix[1:]
    char = [
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l',
        'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
    ]

    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    t_pos = char.index(t)
    t_rng = [t_pos * data0_system_T_interval, t_pos * data0_system_T_interval + 7]
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.join([i, j]))

    p_pos = dualchar.index(p)
    p_val = p_pos * data0_system_P_interval

    return t_rng, p_val


def convert_to_data1s(src, dst):

    def run_eqpt(data0):
        data0copy = os.path.basename(canonical_d0_name(data0))
        shutil.copyfile(data0, data0copy)
        eqpt(data0copy)
        os.remove(data0copy)

    src = os.path.realpath(src)
    dst = os.path.realpath(dst)

    if os.path.exists(dst) and not os.path.isdir(dst):
        raise ValueError('destination must be a directory')
    elif not os.path.exists(dst):
        os.makedirs(dst)

    with WorkingDirectory(dst):
        if os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                os.makedirs(os.path.relpath(root, src), exist_ok=True)
                with WorkingDirectory(os.path.join(dst, os.path.relpath(root, src))):
                    for data0 in files:
                        data0 = os.path.join(root, data0)
                        if is_data0_file(data0):
                            run_eqpt(data0)
        elif os.path.isfile(src):
            run_eqpt(src)
        else:
            raise ValueError('source argument must be a file or directory')


def canonical_d0_name(data0):
    stem, ext = os.path.splitext(os.path.basename(data0))
    if ext == '.d0':
        return data0
    elif ext == '' or ext == '.':
        ext = ''
    elif ext[0] == '.':
        ext = '_' + ext[1:]
    else:
        ext = '_' + ext

    return os.path.join(os.path.dirname(data0), stem + ext + '.d0')


def hash_data0s(data0dir):
    """
    Recursively generate a hash of all data0 files in a directory. If a file is identified as not
    a data0 file (see :func:`is_data0_file`), then it is not hashed and is added to a list of
    unhashed files. Both the hash and the list of unhashed files are returned.

    :param data0dir: path to the directory of data0 files to hash
    :type data0dir: str
    :return: a hash of all data0 files and a list of unhashed files
    :rtype: (str, hash) """
    unhashed = []
    with TemporaryDirectory() as tmpdir:
        for root, dirs, files in os.walk(data0dir):
            files = [_ for _ in files if not _[0] == '.']
            tmp = os.path.join(tmpdir, os.path.relpath(root, data0dir))
            os.makedirs(tmp, exist_ok=True)
            for data0 in files:
                src = os.path.join(root, data0)
                if is_data0_file(src):
                    dst = os.path.join(tmp, canonical_d0_name(data0))
                    shutil.copyfile(src, dst)
                else:
                    unhashed.append(src)
                    continue

        return hash_dir(tmpdir), unhashed


def is_data0_file(data0):
    """
    Determine whether a file is a data0 file by inspecting the first 5 characters of the file.
    Those characters must exist and must be :code:`data0` after converting to lower case.

    :param data0: path to a data0 file
    :type data0: str
    :return: whether or not we think the file is in fact a data0 file
    :rtype: str
    """
    if data0.split('/')[-1][0] != '.':
        with open(data0, 'r') as handle:
            return handle.read(5).lower() == 'data0'


class TPCurve(object):

    def __init__(self, fname, T, P):
        if not ('min' in T and 'mid' in T and 'max' in T):
            raise ValueError('temperature dictionary must have min, mid and max keys')

        if len(P) != 2:
            raise ValueError('expected exactly two polynomials')
        elif any(len(coeffs) == 0 for coeffs in P):
            raise ValueError('polynomial has no coefficients')

        self.fname = fname
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

    @property
    def data1file(self):
        stem, _ = os.path.splitext(self.fname)
        return stem + '.d1'

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

    @classmethod
    def from_data1f(cls, filename):

        def read_coefficients(line, chars=16):
            line = line.rstrip()
            if len(line) % chars != 0:
                msg = f'the precision is not what was expected\n  len({line})=={len(line)}'
                raise Exception(msg)
            return np.asarray([float(line[i:i + chars]) for i in range(0, len(line), chars)])

        P, T = [], {}

        with open(filename, 'r') as file:
            lines = file.readlines()
            for i, line in enumerate(lines):
                if re.findall('^presg\n', line):
                    P = [read_coefficients(lines[j]) for j in range(i + 1, i + 3)]
                    continue

                if 'Data file maximum and minimum temperatures (C)' in line:
                    T = {
                        'min': float(lines[i + 1][:10]),
                        'mid': float(lines[i + 3][:10]),
                        'max': float(lines[i + 4][:10]),
                    }

        return cls(filename, T, P)

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
