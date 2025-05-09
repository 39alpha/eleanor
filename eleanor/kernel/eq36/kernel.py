import io
import os.path
import sys
from datetime import datetime

import numpy as np

import eleanor.equilibrium_space as es
import eleanor.util as tool_room
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.exceptions import EleanorException, EleanorFileException
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.interface import AbstractKernel
from eleanor.order import Order
from eleanor.reactants import *
from eleanor.typing import Number, Optional, Species, cast
from eleanor.util import NumberFormat

from . import util
from .codes import RunCode
from .config import Config, Eq3Config, Eq6Config
from .constraints import TPCurveConstraint
from .data1 import Data1
from .exec import eq3, eq6
from .settings import IOPT_1, IOPT_4


class Kernel(AbstractKernel):
    config: Config
    data1_dir: str

    _setup: bool
    _data1s: list[Data1]

    def __init__(self, config: Config, data1_dir: str, *args, **kwargs):
        self.data1_dir = data1_dir

        self._setup = False
        self._data1s = []

    def is_soft_exit(self, code: int) -> bool:
        return code in [0, 60]

    # TODO: Return basic setup information, e.g. species, etc...
    def setup(self, order: Order, *args, verbose: bool = False, **kwargs):
        Trange = order.temperature.range()
        Prange = order.pressure.range()
        with tool_room.WorkingDirectory(self.data1_dir):
            _, data1_files, *_ = tool_room.find_files('.d1')
            for file in data1_files:
                file = os.path.realpath(file)
                data1 = Data1.from_file(file)
                if data1.tp_curve.set_domain(Trange, Prange):
                    self._data1s.append(data1)

        if len(self._data1s) == 0:
            raise EleanorException('''The temperature and pressure ranges provided in the problem specification do not
                overlap with any of the temperature-pressure curves specified in the provided data1 files.''')

        self._setup = True

    def resolve_kernel_config(self, vs_point: vs.Point) -> Config:
        if not isinstance(vs_point.kernel, Config):
            raise TypeError(f'the provided problem.kernel has type {type(vs_point.kernel)} expected {Config}')

        config = cast(Config, vs_point.kernel)

        suppress_all_solid_solutions = False
        suppress_named_solid_solutions = False
        for suppression in vs_point.suppressions:
            if suppression.type in ['solid solution', 'solid solutions']:
                if len(suppression.exceptions) != 0:
                    raise NotImplementedError('solid solution exemptions are not yet supported')
                elif suppression.name is None:
                    suppress_all_solid_solutions = True
                elif suppress_all_solid_solutions:
                    suppress_named_solid_solutions = True

        if suppress_all_solid_solutions and suppress_named_solid_solutions:
            print('warning: all solid solutions are suppressed some are suppressed by name', file=sys.stderr)

        if not suppress_all_solid_solutions:
            config.eq3_config.iopt_4 = IOPT_4.PERMIT_SS
            config.eq6_config.iopt_4 = IOPT_4.PERMIT_SS

        if len(vs_point.reactants) != 0:
            config.eq6_config.iopt_1 = IOPT_1.TITRATION_SYS

        vs_point.kernel = config

        return vs_point.kernel

    def constrain(self, boatswain: Boatswain) -> Boatswain:
        constraint = TPCurveConstraint(boatswain.order.temperature, boatswain.order.pressure, self._data1s)
        boatswain.constraints.append(constraint)
        return boatswain

    def find_data1(self, vs_point: vs.Point, verbose: bool = False) -> Data1:
        T: Number = vs_point.temperature
        P: Number = vs_point.pressure

        d1s: list[Data1] = []
        for data1 in self._data1s:
            curve = data1.tp_curve
            if curve is not None and curve.temperature_in_domain(T):
                if curve(T) == P:
                    d1s.append(data1)

        if len(d1s) == 0:
            raise EleanorKernelException(f'failed to find a data1 file with temperature {T} and pressure {P}')
        elif len(d1s) > 1 and verbose:
            # DGM: For now we just take the first data1, but we could randomly choose. Ideally, all of the thermodynamic
            #      parameters in the files should be identical.
            print('warning: multiple data1 files pass through temperature {T} and pressure {P}; choosing first')

        return d1s[0]

    def run(self, vs_point: vs.Point, *args, verbose: bool = False, **kwargs) -> list[es.Point]:
        config = self.resolve_kernel_config(vs_point)
        if config.data1_file is None:
            data1 = self.find_data1(vs_point, verbose=verbose)
            config.data1_file = data1.filename

        start_date = datetime.now()
        eq3_input_path = self.write_eq3_input(vs_point, data1, verbose=verbose)
        eq3(config.data1_file, eq3_input_path, timeout=config.timeout)
        eq3_results = util.read_eq3_output()
        complete_date = datetime.now()
        eq3_results.start_date, eq3_results.complete_date = start_date, complete_date

        start_date = datetime.now()
        pickup_lines = util.read_pickup_lines()
        eq6_input_path = self.write_eq6_input(vs_point, pickup_lines=pickup_lines, verbose=verbose)
        eq6(config.data1_file, eq6_input_path, timeout=config.timeout)
        eq6_results = util.read_eq6_output()
        complete_date = datetime.now()
        eq6_results.start_date, eq6_results.complete_date = start_date, complete_date

        return [eq3_results, eq6_results]

    def write_eq3_input(
        self,
        vs_point: vs.Point,
        data1: Data1,
        file: Optional[str | io.TextIOWrapper] = None,
        verbose: bool = False,
    ) -> str:
        if not self._setup:
            raise EleanorKernelException('kernel is not setup; cannot write eq3 input file')

        config = cast(Config, vs_point.kernel)
        if not vs_point.has_species_constraint(config.redox_species):
            if config.redox_species == 'fO2' and vs_point.has_species_constraint('O2(g)'):
                pass
            else:
                raise EleanorKernelException(f'eq3/6 redox species ({config.redox_species}) is unconstrained')

        if file is None:
            file = 'problem.3i'

        if isinstance(file, str):
            with open(file, 'w') as handle:
                return self.write_eq3_input(vs_point, data1, file=handle, verbose=verbose)

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
        T = NumberFormat.SCIENTIFIC.fmt(vs_point.temperature, precision=5)
        P = NumberFormat.SCIENTIFIC.fmt(vs_point.pressure, precision=5)
        charge_balance = config.charge_balance

        if config.redox_species == 'fO2' or config.redox_species == 'O2(g)':
            use_other_species = 0
            fO2 = vs_point.get_species('O2(g)')
            if fO2 is None:
                raise EleanorKernelException(f'cannot find redox species "{config.redox_species}"')

            value = NumberFormat.SCIENTIFIC.fmt(fO2.value, precision=5)
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
        H = vs_point.get_species('H+')
        if H is not None:
            print(f'species= {H.name}', file=file)
            if H.value < 0:
                # This branch should always be taken, but you never know...
                print(f'   jflgi= 16    covali= {NumberFormat.SCIENTIFIC.fmt(H.value, precision=5)}', file=file)
            else:
                print(f'   jflgi= 16    covali=  {NumberFormat.SCIENTIFIC.fmt(H.value, precision=5)}', file=file)

        for element in vs_point.elements:
            value = NumberFormat.SCIENTIFIC.fmt(10**element.log_molality, precision=5)

            basis_species = data1.get_basis_species(element.name)
            if basis_species is None:
                raise Exception(f'no basis species found for {element.name}')

            print(f'species= {basis_species.name}', file=file)
            print(f'   jflgi=  0    covali=  {value}', file=file)
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
        suppressed = [x.name for x in filter(lambda x: x.name is not None, vs_point.suppressions)]
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

    def write_eq6_input(
        self,
        vs_point: vs.Point,
        file: Optional[str | io.TextIOWrapper] = None,
        pickup_lines: Optional[list[str]] = None,
        verbose: bool = False,
    ) -> str:
        config = cast(Config, vs_point.kernel)
        if not vs_point.has_species_constraint(config.redox_species):
            if config.redox_species == 'fO2' and vs_point.has_species_constraint('O2(g)'):
                pass
            else:
                raise EleanorKernelException(f'eq3/6 redox species ({config.redox_species}) is unconstrained')

        if file is None:
            file = 'problem.6i'

        if isinstance(file, str):
            with open(file, 'w') as handle:
                return self.write_eq6_input(vs_point, file=handle, pickup_lines=pickup_lines, verbose=verbose)

        # Write Header
        jtemp = config.eq6_config.jtemp
        xi_max = config.eq6_config.xi_max
        T = NumberFormat.SCIENTIFIC.fmt(vs_point.temperature, precision=5)

        reactants: dict[ReactantType, list[vs.Reactant]] = {}
        for reactant in vs_point.reactants:
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
        print(f'      nrct={ncrt: >3}', file=file)

        # Write Mineral Reactants
        for reactant in reactants.get(ReactantType.MINERAL, []):
            if not isinstance(reactant, vs.MineralReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in mineral block')
            morr = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(reactant.titration_rate, precision=5)

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
            if not isinstance(reactant, vs.GasReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in gas block')
            morr = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(reactant.titration_rate, precision=5)

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
            if not isinstance(reactant, vs.SpecialReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in special reactant block')
            morr = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(reactant.titration_rate, precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant=  {reactant.name}', file=file)
            print(f'     jcode=  2               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)
            print(f'     vreac=  0.00000E+00', file=file)

            for component in reactant.composition:
                element, count = component.element, component.count
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
            if not isinstance(reactant, vs.ElementReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in element reactant block')
            morr = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(reactant.titration_rate, precision=5)

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

        # Write Solid Solution Reactants
        for reactant in reactants.get(ReactantType.SOLID_SOLUTION, []):
            if not isinstance(reactant, vs.SolidSolutionReactant):
                raise EleanorKernelException(f'attempted to write {type(reactant)} reactant in solid solution block')
            morr = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(reactant.titration_rate, precision=5)

            print(f'*-----------------------------------------------------------------------------', file=file)
            print(f'  reactant= {reactant.name}', file=file)
            print(f'     jcode=  1               jreac=  0', file=file)
            print(f'      morr=  {morr}      modr=  0.00000E+00', file=file)

            for end_member in reactant.end_members:
                name, fraction = end_member.name, end_member.fraction
                fraction = NumberFormat.SCIENTIFIC.fmt(fraction, precision=5)
                print('   {name: <28}          {fraction}'.format(name=name, fraction=fraction), file=file)

            print(f'   endit.', file=file)
            print(f'       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00', file=file)
            print(f'      fkrc=  0.00000E+00', file=file)
            print(f'      nrk1=  1', file=file)
            print(f'       rk1=  {rk1}       rk2=  0.00000E+00       rk3=  0.00000E+00', file=file)

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
        exceptions: list[vs.SuppressionException] = []
        suppressions: list[vs.Suppression] = []
        suppress_minerals = False
        for suppression in vs_point.suppressions:
            if suppression.type is None:
                suppressions.append(suppression)
            elif suppression.type in ['mineral', 'minerals']:
                if suppression.name is None:
                    suppress_minerals = True
                else:
                    suppressions.append(suppression)
                exceptions.extend(suppression.exceptions)
            elif suppression.type in ['solid solution', 'solid solutions']:
                pass
            else:
                raise EleanorKernelException(f'unsupported suppression type {suppression.type}')

        if suppress_minerals:
            print('     nxopt=  1', file=file)
            print('    option= All', file=file)
        else:
            print('     nxopt=  0', file=file)

        if exceptions:
            print(f'    nxopex={len(exceptions): >3}', file=file)
            for species in exceptions:
                print(f'   species= {species.name}', file=file)
        elif suppress_minerals:
            print(f'    nxopex={len(exceptions): >3}', file=file)

        # Write fixed gases
        print(f'      nffg=  {len(reactants.get(ReactantType.FIXED_GAS, []))}', file=file)
        for reactant in reactants.get(ReactantType.FIXED_GAS, []):
            if not isinstance(reactant, vs.FixedGasReactant):
                raise EleanorKernelException(
                    f'attempted to write {type(reactant)} reactant in fixed gas reactant block')
            moffg = NumberFormat.SCIENTIFIC.fmt(10**reactant.log_moles, precision=5)
            xlkffg = NumberFormat.SCIENTIFIC.fmt(reactant.log_fugacity, precision=5)

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
