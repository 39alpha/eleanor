import io
import os.path
import sys

import numpy as np

import eleanor.hanger.tool_room as tool_room
import eleanor.kernel.eq36.data0_tools as tools
from eleanor.config import (ElementReactant, FixedGasReactant, GasReactant, MineralReactant, Reactant, ReactantType,
                            SpecialReactant)
from eleanor.exceptions import EleanorException, EleanorFileException
from eleanor.hanger.tool_room import NumberFormat
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.interface import AbstractKernel
from eleanor.problem import Problem
from eleanor.typing import Callable, Float, Optional, Species, cast

from . import util
from .codes import RunCode
from .config import Config, Eq3Config, Eq6Config, TPCurveConstraint
from .data0 import Data0
from .exec import eq3, eq6
from .settings import IOPT_1, IOPT_4


class Kernel(AbstractKernel):
    config: Config
    data0_dir: str
    data1_dir: str

    _setup: bool
    _data0_hash: Optional[str]
    _tp_curves: list[tools.TPCurve]
    _representative_data0_fname: Optional[str]
    _representative_data0: Optional[Data0]

    def __init__(self, config: Config, data0_dir: str, data1_dir: Optional[str] = None, *args, **kwargs):
        self.data0_dir = data0_dir
        self.data1_dir = data1_dir if data1_dir is not None else os.path.realpath("data1")

        self._setup = False
        self._data0_hash = None
        self._tp_curves = []
        self._representative_data0_fname = None
        self._representative_data0 = None

    # TODO: Return basic setup information, e.g. species, etc...
    def setup(self, problem: Problem, verbose: bool = False):
        self._data0_hash, unhashed = tools.hash_data0s(self.data0_dir)
        if verbose and len(unhashed) != 0:
            msg = f'The following files in the data0 directory "{self.data0_dir}" do not appear to be valid data0 files'
            print(msg)
            for file in unhashed:
                print(f'  {os.path.relpath(file, self.data0_dir)}')

        # TODO: We should do something a bit more sophisticated: hash each data0 and process the converted files in
        #       parallel
        if not os.path.isdir(self.data1_dir):
            tool_room.ensure_directory(self.data1_dir)
            tools.convert_to_data1s(self.data0_dir, self.data1_dir)

        with tool_room.WorkingDirectory(self.data1_dir):
            _, data1f_files, *_ = tool_room.find_files('.d1f')
            tp_curves = [tools.TPCurve.from_data1f(file) for file in data1f_files]

        Trange = problem.temperature.range
        Prange = problem.pressure.range
        for curve in tp_curves:
            if curve.set_domain(Trange, Prange):
                self._tp_curves.append(curve)

        if len(self._tp_curves) == 0:
            raise EleanorException('''The temperature and pressure ranges provided in the problem specification do not
                overlap with any of the temperature-pressure curves specified in the provided data0 files.''')

        for fname in os.listdir(self.data0_dir):
            fname = os.path.join(self.data0_dir, fname)
            if os.path.isfile(fname):
                self._representative_data0_fname = fname
                break

        if self._representative_data0_fname is None:
            raise EleanorException('Could not choose a representative data0 file.')

        self._setup = True

    @property
    def representative_data0(self):
        if not self._setup:
            raise EleanorException('requested representative data0 before setting up kernel')

        if self._representative_data0 is None:
            if self._representative_data0_fname is None:
                raise EleanorException('no representative data0 file selected during setup')
            self._representative_data0 = Data0.from_file(self._representative_data0_fname, permissive=True)

        return self._representative_data0

    def get_species(self) -> Species:
        elements, aqueous_species, solids, solid_solutions, gases = tools.determine_species()
        end_members = self.representative_data0.solid_solution_end_members(solid_solutions, solids)

        return elements, aqueous_species, solids, solid_solutions, end_members, gases

    def resolve_kernel_config(self, problem: Problem) -> Config:
        if not isinstance(problem.kernel, Config):
            raise TypeError(f'the provided problem.kernel has type {type(problem.kernel)} expected {Config}')

        config = cast(Config, problem.kernel)

        suppress_all_solid_solutions = False
        suppress_named_solid_solutions = False
        for suppression in problem.suppressions:
            if suppression.type == 'solid solution':
                if len(suppression.exceptions) != 0:
                    raise NotImplementedError('solid solution exemptions are not yet supported')
                elif suppression.name is None:
                    suppress_all_solid_solutions = True
                elif suppress_all_solid_solutions:
                    suppress_named_solid_solutions = True

        if suppress_all_solid_solutions and suppress_named_solid_solutions:
            print('warning: all solid solutions are suppressed some are suppressed by name', file=sys.stderr)

        if not suppress_all_solid_solutions:
            config.eq3_config.set_iopt(4, IOPT_4.PERMIT_SS)
            config.eq6_config.set_iopt(4, IOPT_4.PERMIT_SS)

        if len(problem.reactants) != 0:
            config.eq6_config.set_iopt(1, IOPT_1.TITRATION_SYS)

        return problem.kernel

    def constrain(self, problem: Problem) -> Problem:
        constraint = TPCurveConstraint(problem.temperature, problem.pressure, self._tp_curves)
        return problem.add_constraint(constraint)

    def find_data1_file(self, problem: Problem, verbose: bool = False) -> str:
        if not problem.temperature.is_fully_specified or not problem.pressure.is_fully_specified:
            raise EleanorKernelException('temperature and pressure are not fixed; cannot choose data1 file')

        T = problem.temperature.value
        P = problem.pressure.value

        curves: list[tools.TPCurve] = []
        for curve in self._tp_curves:
            if curve.temperature_in_domain(T):
                if curve(T) == P:
                    curves.append(curve)

        if len(curves) == 0:
            raise EleanorKernelException(f'failed to find a data1 file with temperature {T} and pressure {P}')
        elif len(curves) > 1 and verbose:
            print('warning: multiple data1 files pass through temperature {T} and pressure {P}; choosing first')

        return os.path.join(self.data1_dir, curves[0].data1file)

    def run(self, problem: Problem, verbose: bool = False) -> tuple[dict[str, Float], dict[str, Float]]:
        config = self.resolve_kernel_config(problem)
        if config.data1_file is None:
            config.data1_file = self.find_data1_file(problem, verbose=verbose)

        if not problem.is_fully_specified:
            raise EleanorKernelException('cannot run kernel on an underspecified problem')

        eq3_input_path = self.write_eq3_input(problem, verbose=verbose)

        eq3(config.data1_file, eq3_input_path)
        eq3_results = util.read_eq3_output()

        pickup_lines = util.read_pickup_lines()

        eq6_input_path = self.write_eq6_input(problem, pickup_lines=pickup_lines, verbose=verbose)
        eq6(config.data1_file, eq6_input_path)
        eq6_results = util.read_eq6_output()

        return eq3_results, eq6_results

    def write_eq3_input(self,
                        problem: Problem,
                        file: Optional[str | io.TextIOWrapper] = None,
                        verbose: bool = False) -> str:
        if not problem.is_fully_specified:
            raise EleanorKernelException('cannot write an underspecified problem as eq3 input')

        config = cast(Config, problem.kernel)
        if not problem.has_species_constraint(config.redox_species):
            if config.redox_species == 'fO2' and problem.has_species_constraint('O2(g)'):
                pass
            else:
                raise EleanorKernelException(f'eq3/6 redox species ({config.redox_species}) is unconstrained')

        if file is None:
            file = 'problem.3i'

        if isinstance(file, str):
            with open(file, 'w') as handle:
                return self.write_eq3_input(problem, file=handle, verbose=verbose)

        # Write header
        print(f'EQ3NR input file name= {os.path.basename(file.name)}', file=file)
        print('endit.', file=file)

        # Write basis switches
        print(f'* Special basis switches', file=file)
        print(f'    nsbswt=   {len(config.basis_map)}', file=file)
        for old, new in config.basis_map.items():
            print(f'species= {old}', file=file)
            print(f'  switch with= {new}', file=file)

        # Write general settings
        T = problem.temperature.format(precision=5, formatter=NumberFormat.SCIENTIFIC)
        P = problem.pressure.format(precision=5, formatter=NumberFormat.SCIENTIFIC)
        charge_balance = config.charge_balance

        if config.redox_species == 'fO2':
            use_other_species = 0
            if 'fO2' in problem.species:
                value = problem.species['fO2'].format(precision=5)
            else:
                value = problem.species['O2(g)'].format(precision=5)
            redox_species = 'None'
        elif config.redox_species == 'O2(g)':
            use_other_species = 0
            value = problem.species['O2(g)'].format(precision=5)
            redox_species = 'None'
        else:
            use_other_species = 1
            value = NumberFormat.SCIENTIFIC.fmt(0, precision=5)
            redox_species = config.redox_species

        print(f'* General', file=file)
        print(f'     tempc=  {T}', file=file)
        print(f'    jpres3=   0', file=file)
        print(f'     press=  {P}', file=file)
        print(f'       rho=  1.00000E+00', file=file)
        print(f'    itdsf3=   0', file=file)
        print(f'    tdspkg=  0.00000E+00     tdspl=  0.00000E+00', file=file)
        print(f'    iebal3=   1', file=file)
        print(f'     uebal= {charge_balance}', file=file)
        print(f'    irdxc3=   {use_other_species}', file=file)
        print(f'    fo2lgi= {value}       ehi=  0.00000E+00', file=file)
        print(f'       pei=  0.00000E+00    uredox= {redox_species}', file=file)

        # Write species
        print('* Aqueous basis species', file=file)
        H = problem.species.get('H+')
        if H is not None:
            print(f'species= {H.name}', file=file)
            print(f'   jflgi= 16    covali=  {H.format(precision=5)}', file=file)

        for element in problem.elements.values():
            if element.value is None:
                raise EleanorKernelException('cannot write an underspecified problem as eq3 input')

            if element.unit == 'log molality':
                value = 10**element.value
            else:
                value = element.value

            basis_species = self.representative_data0.get_basis_species(element.name)
            if basis_species is None:
                raise Exception(f'no basis species found for {element.name}')

            print(f'species= {basis_species.name}', file=file)
            print(f'   jflgi=  0    covali=  {NumberFormat.SCIENTIFIC.fmt(value, precision=5)}', file=file)
        print('endit.', file=file)

        # Write ion exchangers
        print('* Ion exchangers', file=file)
        print('    qgexsh=        F', file=file)
        print('       net=   0', file=file)
        print('* Ion exchanger compositions', file=file)
        print('      neti=   0', file=file)

        # Write solid solution compositions
        print('* Solid solution compositions', file=file)
        print('      nxti=   0', file=file)

        # Write suppressions
        suppressed = [x.name for x in filter(lambda x: x.name is not None, problem.suppressions)]
        print(f'* Alter/suppress options', file=file)
        print(f'     nxmod=   {len(suppressed)}', file=file)
        for species in suppressed:
            print(f'   species= {species}', file=file)
            print(f'    option= -1              xlkmod=  0.00000E+00', file=file)

        # Write switches
        self.write_switch_grid(file, config.eq3_config, verbose=verbose)

        # Write numeric parameters
        print('* Numerical parameters', file=file)
        print('     tolbt=  0.00000E+00     toldl=  0.00000E+00', file=file)
        print('    itermx=   0', file=file)

        # Write ordinary basis switches
        print('* Ordinary basis switches', file=file)
        print('    nobswt=   0', file=file)

        # Write saturation tolerance
        print('* Saturation flag tolerance', file=file)
        print('    tolspf=  0.00000E+00', file=file)

        # Write saturation tolerance
        print('* Aqueous phase scale factor', file=file)
        print('    scamas=  1.00000E+00', file=file)

        return file.name

    def write_eq6_input(self,
                        problem: Problem,
                        file: Optional[str | io.TextIOWrapper] = None,
                        pickup_lines: Optional[list[str]] = None,
                        verbose: bool = False) -> str:
        if not problem.is_fully_specified:
            raise EleanorKernelException('cannot write an underspecified problem as eq6 input')

        config = cast(Config, problem.kernel)
        if not problem.has_species_constraint(config.redox_species):
            if config.redox_species == 'fO2' and problem.has_species_constraint('O2(g)'):
                pass
            else:
                raise EleanorKernelException(f'eq3/6 redox species ({config.redox_species}) is unconstrained')

        if file is None:
            file = 'problem.6i'

        if isinstance(file, str):
            with open(file, 'w') as handle:
                return self.write_eq6_input(problem, file=handle, pickup_lines=pickup_lines, verbose=verbose)

        # Write Header
        jtemp = config.eq6_config.jtemp
        xi_max = config.eq6_config.xi_max
        T = problem.temperature.format(precision=5, formatter=NumberFormat.SCIENTIFIC)

        reactants: dict[ReactantType, list[Reactant]] = {}
        for reactant in problem.reactants:
            if reactant.type not in reactants:
                reactants[reactant.type] = []
            reactants[reactant.type].append(reactant)

        ncrt = sum(len(r) for t, r in reactants.items() if t is not ReactantType.FIXED_GAS)

        print(f'EQ3NR input file name= {os.path.basename(file.name)}', file=file)
        print(f'endit.', file=file)
        print(f'     jtemp=  {config.eq6_config.jtemp}', file=file)
        print(f'    tempcb=  {T}', file=file)
        print(f'      ttk1=  0.00000E+00      ttk2=  0.00000E+00', file=file)
        print(f'    jpress=  0', file=file)
        print(f'    pressb=  0.00000E+00', file=file)
        print(f'      ptk1=  0.00000E+00      ptk2=  0.00000E+00', file=file)
        print(f'      nrct=  {ncrt}', file=file)

        # Write Mineral Reactants
        for reactant in reactants.get(ReactantType.MINERAL, []):
            if not isinstance(reactant, MineralReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in mineral block')
            morr = reactant.amount.format(precision=5)
            rk1 = reactant.titration_rate.format(precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant= {reactant.name}', file=file)
            print(f'     jcode=  0               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)
            print(f'       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', file=file)
            print(f'      fkrc=  0.00000E+00', file=file)
            print(f'      nrk1=  1', file=file)
            print(f'       rk1=  {rk1}       rk2=  0.00000E+00       rk3=  0.00000E+00', file=file)

        # Write Gas Reactants
        for reactant in reactants.get(ReactantType.GAS, []):
            if not isinstance(reactant, GasReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in gas block')
            morr = reactant.amount.format(precision=5)
            rk1 = reactant.titration_rate.format(precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant= {reactant.name}', file=file)
            print(f'     jcode=  4               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)
            print(f'       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', file=file)
            print(f'      fkrc=  0.00000E+00', file=file)
            print(f'      nrk1=  1', file=file)
            print(f'       rk1=  {rk1}       rk2=  0.00000E+00       rk3=  0.00000E+00', file=file)

        # Write Special Reactants
        for reactant in reactants.get(ReactantType.SPECIAL, []):
            if not isinstance(reactant, SpecialReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in special reactant block')
            morr = reactant.amount.format(precision=5)
            rk1 = reactant.titration_rate.format(precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant=  {reactant.name}', file=file)
            print(f'     jcode=  2               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)
            print(f'     vreac=  0.00000E+00', file=file)

            for element, count in reactant.composition.items():
                c = NumberFormat.SCIENTIFIC.fmt(count, precision=5)
                print('   {element: <2}          {count}'.format(element=element, count=c), file=file)

            print(f'   endit.', file=file)
            print(f'* Reaction', file=file)
            print(f'   endit.', file=file)
            print(f'       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', file=file)
            print(f'      fkrc=  0.00000E+00', file=file)
            print(f'      nrk1=  1                nrk2=  0', file=file)
            print(f'      rkb1=  {rk1}      rkb2=  0.00000E+00      rkb3=  0.00000E+00', file=file)

        # Write Element Reactants
        for reactant in reactants.get(ReactantType.ELEMENT, []):
            if not isinstance(reactant, ElementReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in element reactant block')
            morr = reactant.amount.format(precision=5)
            rk1 = reactant.titration_rate.format(precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant=  {reactant.name}', file=file)
            print(f'     jcode=  2               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)
            print(f'     vreac=  0.00000E+00', file=file)
            print(f'   {0: <2}          1.00000E+00'.format(reactant.name), file=file)
            print(f'   endit.', file=file)
            print(f'* Reaction', file=file)
            print(f'   endit.', file=file)
            print(f'       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', file=file)
            print(f'      fkrc=  0.00000E+00', file=file)
            print(f'      nrk1=  1                nrk2=  0', file=file)
            print(f'      rkb1=  {rk1}      rkb2=  0.00000E+00      rkb3=  0.00000E+00', file=file)

        # Write limits
        print(f'*-----------------------------------------------------------------------------', file=file)
        print(f'    xistti=  0.00000E+00    ximaxi=  {NumberFormat.SCIENTIFIC.fmt(xi_max, precision=5)}', file=file)
        print(f'    tistti=  0.00000E+00    timmxi=  1.00000E+38', file=file)
        print(f'    phmini= -1.00000E+38    phmaxi=  1.00000E+38', file=file)
        print(f'    ehmini= -1.00000E+38    ehmaxi=  1.00000E+38', file=file)
        print(f'    o2mini= -1.00000E+38    o2maxi=  1.00000E+38', file=file)
        print(f'    awmini= -1.00000E+38    awmaxi=  1.00000E+38', file=file)
        print(f'    kstpmx=        10000', file=file)
        print(f'    dlxprn=  1.00000E+38    dlxprl=  1.00000E+38', file=file)
        print(f'    dltprn=  1.00000E+38    dltprl=  1.00000E+38', file=file)
        print(f'    dlhprn=  1.00000E+38    dleprn=  1.00000E+38', file=file)
        print(f'    dloprn=  1.00000E+38    dlaprn=  1.00000E+38', file=file)
        print(f'    ksppmx=          999', file=file)
        print(f'    dlxplo=  1.00000E+38    dlxpll=  1.00000E+38', file=file)
        print(f'    dltplo=  1.00000E+38    dltpll=  1.00000E+38', file=file)
        print(f'    dlhplo=  1.00000E+38    dleplo=  1.00000E+38', file=file)
        print(f'    dloplo=  1.00000E+38    dlaplo=  1.00000E+38', file=file)
        print(f'    ksplmx=        10000', file=file)

        # Write the switch grid
        self.write_switch_grid(file, config.eq6_config, verbose=verbose)

        # Write mineral suppressions
        exemptions = []
        suppressions = []
        suppress_minerals = False
        for suppression in problem.suppressions:
            if suppression.type is None:
                suppressions.append(suppression)
            elif suppression.type == 'mineral':
                if suppression.name is None:
                    supress_minerals = True
                else:
                    suppressions.append(suppression)
                exemptions.extend(suppression.exceptions)
            else:
                raise EleanorKernelException(f'unsupported suppression type {suppression.type}')

        if suppress_minerals:
            print('     nxopt=  1', file=file)
            print('    option= All', file=file)
        else:
            print('     nxopt=  0', file=file)

        if exemptions:
            print(f'    nxopex=  {len(exemptions)}', file=file)
            for species in exemptions:
                print(f'   species= {species}', file=file)

        # Write fixed gases
        print(f'      nffg=  {len(reactants.get(ReactantType.FIXED_GAS, []))}', file=file)
        for reactant in reactants.get(ReactantType.FIXED_GAS, []):
            if not isinstance(reactant, FixedGasReactant):
                raise EleanorKernelException(
                    f'attempted to write {type(reactant)} reactant in fixed gas reactant block')
            moffg = reactant.amount.format(precision=5)
            xlkffg = reactant.fugacity.format(precision=5)

            print(f'   species= {reactant.name}', file=file)
            print(f'     moffg=  {moffg}', file=file)
            print(f'    xlkffg= {xlkffg}', file=file)

        # Write the rest
        print('    nordmx=   6', file=file)
        print('     tolbt=  0.00000E+00     toldl=  0.00000E+00', file=file)
        print('    itermx=   0', file=file)
        print('    tolxsf=  0.00000E+00', file=file)
        print('    tolsat=  0.00000E+00', file=file)
        print('    ntrymx=   0', file=file)
        print('    dlxmx0=  0.00000E+00', file=file)
        print('    dlxdmp=  0.00000E+00', file=file)
        print('*-----------------------------------------------------------------------------', file=file)

        if pickup_lines is not None:
            # These lines already include a newline, so we cannot use `print`
            for line in pickup_lines:
                file.write(line)

        return file.name

    def write_switch_grid(self, file: io.TextIOWrapper, c: Eq3Config | Eq6Config, verbose: bool = False):
        if isinstance(c, Eq3Config) and verbose:
            c = c.make_verbose()

        print('*               1    2    3    4    5    6    7    8    9   10', file=file)
        print('  iopt1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iopt[:10]),
              file=file)
        print(' iopt11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iopt[10:]),
              file=file)
        if isinstance(c, Eq3Config):
            line = '  iopg1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(
                *c.iopg[:10])
            print(line, file=file)

            line = ' iopg11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(
                *c.iopg[10:])
            print(line, file=file)
        print('  iopr1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iopr[:10]),
              file=file)
        print(' iopr11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iopr[10:]),
              file=file)
        print('  iodb1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iodb[:10]),
              file=file)
        print(' iodb11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}'.format(*c.iodb[10:]),
              file=file)


AbstractKernel.register(Kernel)
