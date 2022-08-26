"""
 data0 analysis tools
 Tucker Ely
 April 8th 2020
"""
import math
import os
import os.path
import pandas as pd
import numpy as np
import re
import shutil

from os.path import abspath, dirname, join, realpath
import matplotlib.pyplot as plt

from .tool_room import grab_lines, grab_str, read_inputs, WorkingDirectory
from .eq36 import eqpt


DATA_PATH = join(abspath(join(dirname(realpath(__file__)), '..')), 'data')
SLOP_DF = pd.read_csv(join(DATA_PATH, 'test_worm_data.csv'), index_col=0)

def species_info(sp):
    """
    in:
        species name in worm slop file 'SLOP_DF'
    out:
        dict['ele'] = sto containing elements in species
    """
    comp_dict = {}
    formula_ox = SLOP_DF['formula_ox'][sp]
    for _ in formula_ox.split():
        front = (re.sub(r'[-+][0-9]{0,2}', '', _))
        if re.findall('^[A-Za-z]', front):
            front = '1{}'.format(front)
        sto, ele = re.findall(r'([0-9+\.]{1,}|[A-Za-z]+)', front)
        comp_dict[ele] = sto
    return comp_dict


def determine_ele_set(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded elements
        :param path: campaign huffer path to test.3o file
        :type path: str
            :return: list of elements

    """
    elements = []
    grab_ele = False
    with open('{}test.3o'.format(path), 'r') as f:
        for line in f:
            if '           --- Elemental Composition of the Aqueous Solution ---' in line:
                grab_ele = True
            elif grab_ele and re.findall('^     [A-Z]', line):

                if float(line.split()[1]) == 0.0:
                    # element not loaded (ie. Cl). this shows up in
                    # the eq3 element set even if set to 0.
                    pass
                else:
                    elements.append(grab_str(line, 0))
            elif '--- Numerical Composition of the Aqueous Solution ---' in line:
                return [_ for _ in elements if _ not in ['O', 'H']]


def determine_species_set(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded species
        separated into their groups (elements, aqueous, solids, solid solutions, and gases)
        :param path: campaign huffer path to test.3o file
        :return:
            list of elements,
            list of aqueous species,
            list of solids
            list of solid solutions
            list of gases

    """
    suppress = []

    elements = []
    aqueous_sp = []
    solids = []
    solid_solutions = []
    gases = []

    with open('{}test.3o'.format(path), 'r') as f:
        lines = f.readlines()

        # ### gather suppress info from near the top of the
        for i in range(len(lines)):
            if ' * Alter/suppress options' in lines[i]:
                # ### numebr of suppresion options
                supp_n = int(lines[i + 1].split()[-1])
                # print(supp_n)
                for j in range(1, supp_n + 1):
                    suppress.append(lines[i + 2 * j][12:].strip())
                break

        # ### search for all other info from teh bottom of the file
        for i in range(len(lines) - 1, 0, -1):
            # ### find the beginning of the print section for the final system compostion.
            if ' Done. Hybrid Newton-Raphson iteration converged in ' in lines[i]:
                break

        # ### now count forward in lines against to read the system compostion
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
                    aqueous_sp.append(lines[i][:26].strip())
                    i += 1

                # ### this fictive aq speices shows up in the aqueous block
                aqueous_sp.remove('O2(g)')

            elif '           --- Saturation States of Pure Solids ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    solids.append(lines[i][:26].strip())
                    i += 1

            elif '--- Saturation States of Solid Solutions ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    solid_solutions.append(lines[i][:26].strip())
                    i += 1

            elif '--- Fugacities ---' in lines[i]:
                i += 4
                while not re.findall('^\n', lines[i]):
                    gases.append(lines[i][:26].strip())
                    i += 1

                break

            else:
                i += 1

    # ### without knowing which lists contain the supressions, they all must be searched
    elements = [_ for _ in elements if _ not in suppress]
    aqueous_sp = [_ for _ in aqueous_sp if _ not in suppress]
    solids = [_ for _ in solids if _ not in suppress]
    solid_solutions = [_ for _ in solid_solutions if _ not in suppress]
    gases = [_ for _ in gases if _ not in suppress]

    return elements, aqueous_sp, solids, solid_solutions, gases


def determine_loaded_sp(path=''):
    """
    Use the verbose test.3o file run by the huffer to determine the loaded species,
        which includes all non-basis blocks from the data0 (aq solids, gases, etc.)
        :param path: campaign huffer path to test.3o file
        :return: list of loaded species

    """
    loaded_sp = []
    with open('{}test.3o'.format(path), 'r') as f:
        lines = f.readlines()
        grab_loaded_sp = False
        for _ in range(len(lines)):
            # ## search for loaded species.
            # These only appear if verbose 'v' is set with local_3i.write() above
            if ' --- Listing of Species and Reactions ---' in lines[_]:
                grab_loaded_sp = True
            elif ' - - BEGIN ITERATIVE CALCULATIONS  - - - ' in lines[_]:
                break
            elif grab_loaded_sp and '------------------' in lines[_]:
                # ## the two options below avoid the 'BEGIN ITERATIVE . .'
                # ## which is also caught with the above string.
                if '1.000' in lines[_ + 2]:
                    # ## exclude basis species
                    # ## grab full string (with spaces) after the stochiometry
                    # ## this correctly differentiates solid solution endmemebrs
                    # ## fromt their stand alone counterparts ie: 'CA-SAPONITE'
                    # ## vs 'CA-SAPONITE (SAPONITE)'
                    loaded_sp.append(lines[_ + 2].split('1.000  ')[-1].strip())
                elif 'is a strict' in lines[_ + 2]:
                    # ## grabs basis species
                    loaded_sp.append(
                        lines[_ + 2].split(' is a strict ')[0].strip())

        # ## O2(g) shows up as a strict basis species, and again with the gasses
        # ## so its basis form is removed here. Also, H2O shows up 2 times, and
        # ## regardless is separately tracked via the aH2O variable.
        loaded_sp = [_ for _ in loaded_sp if _ != 'H2O' and _ != 'O2(g)']

        # ## alter loaded_sp to reflect correct search names required for 6o
        aq_and_s = [_ for _ in loaded_sp if ' (' not in _]
        ss_and_gas = [_ for _ in loaded_sp if ' (' in _]
        gas = [_.split(' (')[0] for _ in ss_and_gas if '(Gas)' in _]
        ss = [_.split(' (')[1].strip(')(') for _ in ss_and_gas if '(Gas)' not in _]

        sp_names = aq_and_s + gas + list(set(ss))

    return sp_names

def determine_T_P_coverage(data0_dir):
    """
    (1) Check if data0 data1 pairs exists for supplied data0/s
        (1.1) if yes, then hash data1's to make sure they are unchanged
            (1.1.1) if hashes dont match, re-run eqpt on data0's to rebuild data1/data1f
            (1.1.2) if hashes match, calculate T/P region of all supplied files
    (2) If no data1's exists, run eqpt on data0.
        (2.1) Calculate T/P region of all supplied files

    Check user supplies data0. look for T/P grid

    note:  We simply adopt the user-supplied suffix naming scheme, and
              notify them if there are overlaps.

    """

    print('w')
    return []

###############   old piecies to be removed  ####################

def data0_suffix(T, P):
    """
    organizes the construction of multiple data0 files, each with a small t range, at constant
    pressure. The family of data0s this function refers to, are built one at a time by graysons
    worm code, and then stored appropriately in the the db folder. They are intended for spot
    calculations, and not sutiable for 6i runs which explore dT, as each only covers a small T
    range.

    T, P = 3i/6i file T and P
    return appropriate data0 suffix

    T is indicated by the first of the 3 suffix characters.
    P is indicated by the second two
    """

    char = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b',
            'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
            'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.os.path.join([i, j]))
    # ## by using 'floor' below. the correct file is returned for T near the file cutoffs
    # ## for example, T = 7.99 (P=1), does in fact call the data0.002 file. The data0 files
    # ## themselves overlap in their lowest and highest values for consecutive files.
    t_char = char[math.floor(T / data0_system_T_interval)]
    tp_char = '{}{}'.format(t_char, dualchar[math.floor(P / data0_system_P_interval)])

    return tp_char


def data0_TP(suffix):
    """
    reutrn T/P rangte of a data0 file given its suffix
    """
    t = suffix[0]
    p = suffix[1:]
    char = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b',
            'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
            'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

    data0_system_T_interval = 7
    data0_system_P_interval = 0.5
    t_pos = char.index(t)
    t_rng = [t_pos * data0_system_T_interval, t_pos * data0_system_T_interval + 7]
    dualchar = []
    for i in char:
        for j in char:
            dualchar.append(''.os.path.join([i, j]))

    p_pos = dualchar.index(p)
    p_val = p_pos * data0_system_P_interval

    return t_rng, p_val

def check_data0s_loaded():
    """
    what data1 files are currently active in eq3_68.0a/db
    """
    file_name, file_list = read_inputs('data1', 'EQ3_6v8.0a/db', str_loc='prefix')

    suf_list = [_[-3:] for _ in file_list if _.startswith('EQ3_6v8.0a/db/data1')]

    # for _ in suf_list

    plt.figure()
    plt.subplot(111)

    for _ in suf_list:
        t_rng, p_val = data0_TP(_)
        plt.plot(t_rng, [p_val, p_val], color='black', linewidth=0.1)

    plt.xlabel('T (˚C)')
    plt.ylabel('P (bars)')

    plt.title('data0 family coverage\n(∆P = descrete 0.5 bars)\n∆T = 7C contineuous')

    plt.show()

def convert_to_d1(src, dst):
    def run_eqpt(data0):
        data0copy = os.path.basename(canonical_d0_name(data0))
        shutil.copyfile(data0, data0copy)
        eqpt(data0copy)
        os.remove(data0copy)

    src = os.path.os.path.realpath(src)
    dst = os.path.os.path.realpath(dst)

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
                        run_eqpt(os.path.join(root, data0))
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


mw = {
    'O': 15.99940,
    'Ag': 107.86820,
    'Al': 26.98154,
    'Am': 243.00000,
    'Ar': 39.94800,
    'Au': 196.96654,
    'B': 10.81100,
    'Ba': 137.32700,
    'Be': 9.01218,
    'Bi': 208.98000,
    'Br': 79.90400,
    'Ca': 40.07800,
    'Cd': 112.41100,
    'Ce': 140.11500,
    'Cl': 35.45270,
    'Co': 58.93320,
    'Cr': 51.99610,
    'Cs': 132.90543,
    'Cu': 63.54600,
    'Dy': 162.50000,
    'Er': 167.26000,
    'Eu': 151.96500,
    'F': 18.99840,
    'Fe': 55.84700,
    'Fr': 223.00000,
    'Ga': 69.72300,
    'Gd': 157.25000,
    'H': 1.00794,
    'As': 74.92159,
    'C': 12.01100,
    'P': 30.97362,
    'He': 4.00206,
    'Hf': 178.49000,
    'Hg': 200.59000,
    'Ho': 164.93032,
    'I': 126.90447,
    'In': 114.82000,
    'K': 39.09830,
    'Kr': 83.80000,
    'La': 138.90550,
    'Li': 6.94100,
    'Lu': 174.96700,
    'Mg': 24.30500,
    'Mn': 54.93085,
    'Mo': 95.94000,
    'N': 14.00674,
    'Na': 22.98977,
    'Nb': 92.90600,
    'Nd': 144.24000,
    'Ne': 20.17970,
    'Ni': 58.69000,
    'Pb': 207.20000,
    'Pd': 106.42000,
    'Pm': 145.00000,
    'Pr': 140.90765,
    'Pt': 195.08000,
    'Ra': 226.02500,
    'Rb': 85.46780,
    'Re': 186.20700,
    'Rh': 102.90600,
    'Rn': 222.00000,
    'Ru': 101.07000,
    'S': 32.06600,
    'Sb': 127.76000,
    'Sc': 44.95591,
    'Se': 78.96000,
    'Si': 28.08550,
    'Sm': 150.36000,
    'Sn': 118.71000,
    'Sr': 87.62000,
    'Tb': 158.92534,
    'Tc': 98.00000,
    'Th': 232.03800,
    'Ti': 47.88000,
    'Tl': 204.38330,
    'Tm': 168.93421,
    'U': 238.02890,
    'V': 50.94150,
    'W': 183.85000,
    'Xe': 131.29000,
    'Y': 88.90585,
    'Yb': 173.04000,
    'Zn': 65.39000,
    'Zr': 91.22400}

class TPCurve(object):
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
        left = np.dot(coeff_left, self.T['mid'] ** np.arange(len(coeff_left)))
        right = np.dot(coeff_right, self.T['mid'] ** np.arange(len(coeff_right)))

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
        return np.dot(coefficients, T ** np.arange(len(coefficients)))

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
                raise Exception('expected to find intersections or both points inside/outside region')
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
                          if Tmin <= T and T <= Tmax
                          and (i == 0 and self.T['min'] <= T and T <= self.T['mid'])
                          or (i == 1 and self.T['mid'] <= T and T <= self.T['max'])]
                intersections.extend(points)

        return sorted(set(intersections))

    @classmethod
    def from_data0(cls, filename):
        def read_coefficients(line, chars=16):
            line = line.rstrip()
            if len(line) % chars == 0:
                raise Exception('the precision is not what was expected')
            return np.asarray([float(line[i:i + chars]) for i in range(0, len(line), chars)])

        P, T = [], {}

        lines = grab_lines(filename)
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

        return cls(T, P)

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

        return Ts, Ps
