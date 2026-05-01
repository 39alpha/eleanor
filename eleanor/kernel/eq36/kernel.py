import io
import math
import os.path
import sys
from datetime import datetime
from shutil import copyfile
from typing import override

import numpy as np

import eleanor.equilibrium_space as es
import eleanor.util as tool_room
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.exceptions import EleanorException
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.interface import AbstractKernel
from eleanor.order import Order
from eleanor.typing import EleanorKwargs, Number, Unpack, cast
from eleanor.util import NumberFormat

from .constraints import TemperatureRangeConstraint, TPCurveConstraint
from .data1 import Data1
from .exec import eq3, eq6
from .parsers import OutputParser3, OutputParser6
from .settings import IOPT_1, IOPT_4, Eq3Config, Eq6Config, Settings
from .util import read_pickup_lines

type ParsedMap = dict[str, object]
type ParsedTable = dict[str, ParsedMap]


class Kernel(AbstractKernel):
    settings: Settings
    data1_dir: str

    _setup: bool
    _data1s: list[Data1]

    def __init__(self, settings: Settings, data1_dir: str, *args: object, **kwargs: object):
        self.data1_dir = data1_dir

        self._setup = False
        self._data1s = []

    @override
    def is_soft_exit(self, code: int) -> bool:
        return code in [0, 60]

    @override
    def validate_order(self, order: Order) -> None:
        if not self._setup:
            raise EleanorKernelException("eleanor.kernel.eq36.Kernel must be setup before validating order")

        if len(self._data1s) == 0:
            raise EleanorException("""The temperature and pressure ranges provided in the problem specification do not
                overlap with any of the temperature-pressure curves specified in the provided data1 files.""")

    @override
    def copy_data(
        self,
        vs_point: vs.Point,
        *args: object,
        dir: str = ".",
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        verbose = kwargs.get("verbose", False)
        settings = self.resolve_kernel_settings(vs_point)
        if settings.data1_file is None:
            data1 = self.find_data1(vs_point, verbose=verbose)
            settings.data1_file = data1.filename
        _ = copyfile(settings.data1_file, os.path.join(dir, os.path.basename(settings.data1_file)))

    @override
    def get_atomic_weight(self, element: str) -> float | None:
        if not self._setup or len(self._data1s) == 0:
            raise EleanorException("cannot get atomic masses untilt the kernel is setup")
        return self._data1s[0].elements.get(element)

    # TODO: Return basic setup information, e.g. species, etc...
    @override
    def setup(
        self,
        order: Order | None = None,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        _ = kwargs
        if order is None:
            raise EleanorException("order is required")
        Tmin, Tmax = order.temperature.range()
        Trange = (np.float64(Tmin), np.float64(Tmax))

        Pmin, Pmax = order.pressure.range()
        Prange = (np.float64(Pmin), np.float64(Pmax))

        with tool_room.WorkingDirectory(self.data1_dir):
            _, data1_files, *_ = tool_room.find_files(".d1")
            for file in data1_files:
                file = os.path.realpath(file)
                data1 = Data1.from_file(file)
                if data1.tp_curve is not None and data1.tp_curve.set_domain(Trange, Prange):
                    self._data1s.append(data1)

        self._setup = True

    def resolve_kernel_settings(self, vs_point: vs.Point) -> Settings:
        if not isinstance(vs_point.kernel.settings, Settings):
            raise TypeError(
                f"the provided problem.kernel has type {type(vs_point.kernel.settings)} expected {Settings}"
            )

        settings = vs_point.kernel.settings

        suppress_all_solid_solutions = False
        suppress_named_solid_solutions = False
        for suppression in vs_point.suppressions:
            if suppression.type in ["solid solution", "solid solutions"]:
                if len(suppression.exceptions) != 0:
                    raise NotImplementedError("solid solution exemptions are not yet supported")
                elif suppression.name is None:
                    suppress_all_solid_solutions = True
                elif suppress_all_solid_solutions:
                    suppress_named_solid_solutions = True

        if suppress_all_solid_solutions and suppress_named_solid_solutions:
            print("warning: all solid solutions are suppressed some are suppressed by name", file=sys.stderr)

        if not suppress_all_solid_solutions:
            settings.eq3_config.iopt_4 = IOPT_4.PERMIT_SOLID_SOLUTIONS
            if settings.eq6_config is not None:
                settings.eq6_config.iopt_4 = IOPT_4.PERMIT_SOLID_SOLUTIONS

        if vs_point.has_reactants() and settings.eq6_config is not None:
            settings.eq6_config.iopt_1 = IOPT_1.TITRATION_SYS

        vs_point.kernel.settings = settings

        return vs_point.kernel.settings

    @override
    def constrain(self, boatswain: Boatswain) -> Boatswain:
        boatswain.constraints.append(
            TemperatureRangeConstraint(
                boatswain.order.temperature,
                self._data1s,
            )
        )

        boatswain.constraints.append(
            TPCurveConstraint(
                boatswain.order.temperature,
                boatswain.order.pressure,
                self._data1s,
            )
        )

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
            raise EleanorKernelException(f"failed to find a data1 file with temperature {T} and pressure {P}")
        elif len(d1s) > 1 and verbose:
            # DGM: For now we just take the first data1, but we could randomly choose. Ideally, all of the thermodynamic
            #      parameters in the files should be identical.
            print(f"warning: multiple data1 files pass through temperature {T} and pressure {P}; choosing first")

        return d1s[0]

    @override
    def run(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[es.Point]:
        verbose = kwargs.get("verbose", False)
        try:
            settings = self.resolve_kernel_settings(vs_point)
            if settings.data1_file is None:
                data1 = self.find_data1(vs_point, verbose=verbose)
                settings.data1_file = data1.filename
            else:
                data1 = Data1.from_file(settings.data1_file)

            start_date = datetime.now()
            eq3_input_path = self.write_eq3_input(vs_point, data1, verbose=verbose)
            _ = eq3(settings.data1_file, eq3_input_path, timeout=settings.timeout)
            eq3_results = Kernel.read_eq3_output()
            complete_date = datetime.now()
            eq3_results.start_date, eq3_results.complete_date = start_date, complete_date

            if settings.eq6_config is None:
                eq6_results: list[es.Point] = []
            else:
                start_date = datetime.now()
                pickup_lines = read_pickup_lines()
                eq6_input_path = self.write_eq6_input(vs_point, pickup_lines=pickup_lines, verbose=verbose)
                _ = eq6(settings.data1_file, eq6_input_path, timeout=settings.timeout)
                eq6_results = Kernel.read_eq6_output(track_path=settings.track_path)
                complete_date = datetime.now()
                for point in eq6_results:
                    point.start_date, point.complete_date = start_date, complete_date

            return [eq3_results, *eq6_results]
        except EleanorException:
            raise
        except Exception as e:
            raise EleanorException("an unexpected error occured") from e

    def write_eq3_input(
        self,
        vs_point: vs.Point,
        data1: Data1,
        file: str | io.TextIOWrapper | None = None,
        verbose: bool = False,
    ) -> str:
        if not self._setup:
            raise EleanorKernelException("kernel is not setup; cannot write eq3 input file")

        settings = cast(Settings, vs_point.kernel.settings)
        if not vs_point.has_species_constraint(settings.redox_species):
            if settings.redox_species == "fO2" and vs_point.has_species_constraint("O2(g)"):
                pass
            else:
                raise EleanorKernelException(f"eq3/6 redox species ({settings.redox_species}) is unconstrained")

        if file is None:
            file = "problem.3i"

        if isinstance(file, str):
            with open(file, "w") as handle:
                return self.write_eq3_input(vs_point, data1, file=handle, verbose=verbose)

        # Write header
        print(f"EQ3NR input file name= {os.path.basename(file.name)}", file=file)
        print("endit.", file=file)

        # Write basis switches
        print("* Special basis switches", file=file)
        print(f"    nsbswt=   {len(settings.basis_map)}", file=file)
        for old, new in settings.basis_map.items():
            print(f"species= {old}", file=file)
            print(f"  switch with= {new}", file=file)

        # Write general settings
        T = NumberFormat.SCIENTIFIC.fmt(vs_point.temperature, precision=5)
        P = NumberFormat.SCIENTIFIC.fmt(vs_point.pressure, precision=5)
        charge_balance = settings.charge_balance

        if settings.redox_species == "fO2" or settings.redox_species == "O2(g)":
            use_other_species = 0
            fO2 = vs_point.get_species("O2(g)")
            if fO2 is None:
                raise EleanorKernelException(f'cannot find redox species "{settings.redox_species}"')

            value = NumberFormat.SCIENTIFIC.fmt(fO2.value, precision=5)
            redox_species = "None"
        else:
            use_other_species = 1
            value = NumberFormat.SCIENTIFIC.fmt(0, precision=5)
            redox_species = settings.redox_species

        print("* General", file=file)
        print(f"     tempc=  {T}", file=file)
        print("    jpres3=   0", file=file)
        print(f"     press=  {P}", file=file)
        print("       rho=  1.00000E+00", file=file)
        print("    itdsf3=   0", file=file)
        print("    tdspkg=  0.00000E+00     tdspl=  0.00000E+00", file=file)
        print("    iebal3=   1", file=file)
        print(f"     uebal= {charge_balance}", file=file)
        print(f"    irdxc3=   {use_other_species}", file=file)
        print(f"    fo2lgi= {value}       ehi=  0.00000E+00", file=file)
        print(f"       pei=  0.00000E+00    uredox= {redox_species}", file=file)

        # Write species
        print("* Aqueous basis species", file=file)
        H = vs_point.get_species("H+")
        if H is not None:
            print(f"species= {H.name}", file=file)
            if H.value < 0:
                # This branch should always be taken, but you never know...
                print(f"   jflgi= 16    covali= {NumberFormat.SCIENTIFIC.fmt(H.value, precision=5)}", file=file)
            else:
                print(f"   jflgi= 16    covali=  {NumberFormat.SCIENTIFIC.fmt(H.value, precision=5)}", file=file)

        for element in vs_point.elements:
            value = NumberFormat.SCIENTIFIC.fmt(10**element.log_molality, precision=5)

            basis_species = data1.get_basis_species(element.name)
            if basis_species is None:
                raise Exception(f"no basis species found for {element.name}")

            print(f"species= {basis_species.name}", file=file)
            print(f"   jflgi=  0    covali=  {value}", file=file)
        print("endit.", file=file)

        # Write ion exchangers
        print("* Ion exchangers", file=file)
        print("    qgexsh=        F", file=file)
        print("       net=   0", file=file)
        print("* Ion exchanger compositions", file=file)
        print("      neti=   0", file=file)

        # Write solid solution compositions
        print("* Solid solution compositions", file=file)
        print("      nxti=   0", file=file)

        # Write suppressions
        suppressed = [x.name for x in filter(lambda x: x.name is not None, vs_point.suppressions)]
        print("* Alter/suppress options", file=file)
        print(f"     nxmod=   {len(suppressed)}", file=file)
        for species in suppressed:
            print(f"   species= {species}", file=file)
            print("    option= -1              xlkmod=  0.00000E+00", file=file)

        # Write switches
        self.write_switch_grid(file, settings.eq3_config, verbose=verbose)

        # Write numeric parameters
        print("* Numerical parameters", file=file)
        print("     tolbt=  0.00000E+00     toldl=  0.00000E+00", file=file)
        print("    itermx=   0", file=file)

        # Write ordinary basis switches
        print("* Ordinary basis switches", file=file)
        print("    nobswt=   0", file=file)

        # Write saturation tolerance
        print("* Saturation flag tolerance", file=file)
        print("    tolspf=  0.00000E+00", file=file)

        # Write aqueous phase scale factor (the mass of water, default: 1kg)
        scamas = NumberFormat.SCIENTIFIC.fmt(vs_point.water_mass, precision=5)
        print("* Aqueous phase scale factor", file=file)
        print(f"    scamas=  {scamas}", file=file)

        return file.name

    def write_eq6_input(
        self,
        vs_point: vs.Point,
        file: str | io.TextIOWrapper | None = None,
        pickup_lines: list[str] | None = None,
        verbose: bool = False,
    ) -> str:
        settings = cast(Settings, vs_point.kernel.settings)
        if settings.eq6_config is None:
            raise ValueError("no eq6_config provided")

        if not vs_point.has_species_constraint(settings.redox_species):
            if settings.redox_species == "fO2" and vs_point.has_species_constraint("O2(g)"):
                pass
            else:
                raise EleanorKernelException(f"eq3/6 redox species ({settings.redox_species}) is unconstrained")

        if file is None:
            file = "problem.6i"

        if isinstance(file, str):
            with open(file, "w") as handle:
                return self.write_eq6_input(vs_point, file=handle, pickup_lines=pickup_lines, verbose=verbose)

        # Write Header
        jtemp = settings.eq6_config.jtemp
        ttk1 = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ttk1, precision=5)
        ttk2 = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ttk2, precision=5)

        T = NumberFormat.SCIENTIFIC.fmt(vs_point.temperature, precision=5)

        nrct = vs_point.reactant_count() - len(vs_point.fixed_gas_reactants)

        print(f"EQ3NR input file name= {os.path.basename(file.name)}", file=file)
        print("endit.", file=file)
        print(f"     jtemp=  {jtemp}", file=file)
        print(f"    tempcb=  {T}", file=file)
        print(f"      ttk1={ttk1: >13}      ttk2={ttk2: >13}", file=file)
        print("    jpress=  0", file=file)
        print("    pressb=  0.00000E+00", file=file)
        print("      ptk1=  0.00000E+00      ptk2=  0.00000E+00", file=file)
        print(f"      nrct={nrct: >3}", file=file)

        # Write Mineral Reactants
        for mr in vs_point.mineral_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**mr.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(mr.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant= {mr.name}", file=file)
            print("     jcode=  0               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1", file=file)
            print(f"       rk1={rk1: >13}       rk2=  0.00000E+00       rk3=  0.00000E+00", file=file)

        # Write Solid Solution Reactants
        for ssr in vs_point.solid_solution_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**ssr.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(ssr.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant= {ssr.name}", file=file)
            print("     jcode=  1               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)

            for end_member in ssr.end_members:
                name, fraction = end_member.name, end_member.fraction
                frac = NumberFormat.SCIENTIFIC.fmt(fraction, precision=5)
                print("   {name: <28}          {frac}".format(name=name, frac=frac), file=file)

            print("   endit.", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1", file=file)
            print(f"       rk1={rk1: >13}       rk2=  0.00000E+00       rk3=  0.00000E+00", file=file)

        # Write Special Reactants
        for sr in vs_point.special_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**sr.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(sr.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant=  {sr.name}", file=file)
            print("     jcode=  2               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
            print("     vreac=  0.00000E+00", file=file)

            for component in sr.composition:
                element, count = component.element, component.count
                c = NumberFormat.SCIENTIFIC.fmt(count, precision=5)
                print("   {element: <2}          {count}".format(element=element, count=c), file=file)

            print("   endit.", file=file)
            print("* Reaction", file=file)
            print("   endit.", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1                nrk2=  0", file=file)
            print(f"      rkb1={rk1: >13}      rkb2=  0.00000E+00      rkb3=  0.00000E+00", file=file)

        for gl in vs_point.glass_reactants:
            for oxide in gl.oxides:
                morr = NumberFormat.SCIENTIFIC.fmt(10**oxide.log_moles, precision=5)
                rk1 = NumberFormat.SCIENTIFIC.fmt(oxide.titration_rate, precision=5)

                print("*-----------------------------------------------------------------------------", file=file)
                print(f"  reactant=  {oxide.name}", file=file)
                print("     jcode=  2               jreac=  0", file=file)
                print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
                print("     vreac=  0.00000E+00", file=file)

                for component in oxide.composition:
                    element, count = component.element, component.count
                    c = NumberFormat.SCIENTIFIC.fmt(count, precision=5)
                    print("   {element: <2}          {count}".format(element=element, count=c), file=file)

                print("   endit.", file=file)
                print("* Reaction", file=file)
                print("   endit.", file=file)
                print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
                print("      fkrc=  0.00000E+00", file=file)
                print("      nrk1=  1                nrk2=  0", file=file)
                print(f"      rkb1={rk1: >13}      rkb2=  0.00000E+00      rkb3=  0.00000E+00", file=file)

        # Write Element Reactants
        for er in vs_point.element_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**er.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(er.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant=  {er.name}", file=file)
            print("     jcode=  2               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
            print("     vreac=  0.00000E+00", file=file)
            print("   {element: <2}          1.00000E+00".format(element=er.name), file=file)
            print("   endit.", file=file)
            print("* Reaction", file=file)
            print("   endit.", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1                nrk2=  0", file=file)
            print(f"      rkb1={rk1: >13}      rkb2=  0.00000E+00      rkb3=  0.00000E+00", file=file)

        # Write Aqueous Species Reactants
        for ar in vs_point.aqueous_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**ar.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(ar.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant= {ar.name}", file=file)
            print("     jcode=  3               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1", file=file)
            print(f"       rk1={rk1: >13}       rk2=  0.00000E+00       rk3=  0.00000E+00", file=file)

        # Write Gas Reactants
        for gr in vs_point.gas_reactants:
            morr = NumberFormat.SCIENTIFIC.fmt(10**gr.log_moles, precision=5)
            rk1 = NumberFormat.SCIENTIFIC.fmt(gr.titration_rate, precision=5)

            print("*-----------------------------------------------------------------------------", file=file)
            print(f"  reactant= {gr.name}", file=file)
            print("     jcode=  4               jreac=  0", file=file)
            print(f"      morr={morr: >13}      modr=  0.00000E+00", file=file)
            print("       nsk=  0               sfcar=  0.00000E+00    ssfcar=  0.00000E+00", file=file)
            print("      fkrc=  0.00000E+00", file=file)
            print("      nrk1=  1", file=file)
            print(f"       rk1={rk1: >13}       rk2=  0.00000E+00       rk3=  0.00000E+00", file=file)

        # Write limits
        xi_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.xi_min, precision=5)
        time_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.time_min, precision=5)
        ph_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ph_min, precision=5)
        eh_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.eh_min, precision=5)
        log_fO2_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.log_fO2_min, precision=5)
        aw_min = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.aw_min, precision=5)

        xi_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.xi_max, precision=5)
        time_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.time_max, precision=5)
        ph_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ph_max, precision=5)
        eh_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.eh_max, precision=5)
        log_fO2_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.log_fO2_max, precision=5)
        aw_max = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.aw_max, precision=5)

        xi_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.xi_print_interval, precision=5)
        log_xi_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.log_xi_print_interval, precision=5)
        time_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.time_print_interval, precision=5)
        log_time_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.log_time_print_interval, precision=5)
        ph_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ph_print_interval, precision=5)
        eh_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.eh_print_interval, precision=5)
        log_fO2_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.log_fO2_print_interval, precision=5)
        aw_print_interval = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.aw_print_interval, precision=5)
        steps_print_interval = settings.eq6_config.steps_print_interval

        print("*-----------------------------------------------------------------------------", file=file)
        print(f"    xistti={xi_min: >13}    ximaxi={xi_max: >13}", file=file)
        print(f"    tistti={time_min: >13}    timmxi={time_max: >13}", file=file)
        print(f"    phmini={ph_min: >13}    phmaxi={ph_max: >13}", file=file)
        print(f"    ehmini={eh_min: >13}    ehmaxi={eh_max: >13}", file=file)
        print(f"    o2mini={log_fO2_min: >13}    o2maxi={log_fO2_max: >13}", file=file)
        print(f"    awmini={aw_min: >13}    awmaxi={aw_max: >13}", file=file)
        print("    kstpmx=        10000", file=file)
        print(f"    dlxprn={xi_print_interval: >13}    dlxprl={log_xi_print_interval: >13}", file=file)
        print(f"    dltprn={time_print_interval: >13}    dltprl={log_time_print_interval: >13}", file=file)
        print(f"    dlhprn={ph_print_interval: >13}    dleprn={eh_print_interval: >13}", file=file)
        print(f"    dloprn={log_fO2_print_interval: >13}    dlaprn={aw_print_interval: >13}", file=file)
        print(f"    ksppmx={steps_print_interval: >13}", file=file)
        print("    dlxplo=  1.00000E+38    dlxpll=  1.00000E+38", file=file)
        print("    dltplo=  1.00000E+38    dltpll=  1.00000E+38", file=file)
        print("    dlhplo=  1.00000E+38    dleplo=  1.00000E+38", file=file)
        print("    dloplo=  1.00000E+38    dlaplo=  1.00000E+38", file=file)
        print("    ksplmx=        10000", file=file)

        # Write the switch grid
        self.write_switch_grid(file, settings.eq6_config, verbose=verbose)

        # Write mineral suppressions
        exceptions: list[vs.SuppressionException] = []
        suppress_all_minerals = False
        for suppression in vs_point.suppressions:
            if suppression.type is None and suppression.name is None:
                raise EleanorKernelException("suppressions must have a type, a name or both")

            if suppression.name is not None and suppression.exceptions:
                raise EleanorKernelException("cannot add suppression exceptions for a named suppression")

            if suppression.type is None:
                pass
            elif suppression.type in ["mineral", "minerals"]:
                if suppression.name is None:
                    suppress_all_minerals = True
                exceptions.extend(suppression.exceptions)
            elif suppression.type in ["solid solution", "solid solutions"]:
                pass
            else:
                raise EleanorKernelException(f"unsupported suppression type {suppression.type}")

        if suppress_all_minerals:
            print("     nxopt=  1", file=file)
            print("    option= All", file=file)
        else:
            print("     nxopt=  0", file=file)

        if exceptions:
            print(f"    nxopex={len(exceptions): >3}", file=file)
            for species in exceptions:
                print(f"   species= {species.name}", file=file)
        elif suppress_all_minerals:
            print(f"    nxopex={len(exceptions): >3}", file=file)

        # Write fixed gases
        print(f"      nffg={len(vs_point.fixed_gas_reactants): >3}", file=file)
        for fgr in vs_point.fixed_gas_reactants:
            moffg = NumberFormat.SCIENTIFIC.fmt(10**fgr.log_moles, precision=5)
            xlkffg = NumberFormat.SCIENTIFIC.fmt(fgr.log_fugacity, precision=5)

            print(f"   species= {fgr.name}", file=file)
            print(f"     moffg={moffg: >13}    xlkffg={xlkffg: >13}", file=file)

        # Write the rest
        print("    nordmx=   6", file=file)
        print("     tolbt=  0.00000E+00     toldl=  0.00000E+00", file=file)
        print("    itermx=   0", file=file)
        print("    tolxsf=  0.00000E+00", file=file)
        print("    tolsat=  0.00000E+00", file=file)
        print("    ntrymx=   0", file=file)
        print("    dlxmx0=  0.00000E+00", file=file)
        print("    dlxdmp=  0.00000E+00", file=file)
        print("*-----------------------------------------------------------------------------", file=file)

        if pickup_lines is not None:
            # These lines already include a newline, so we cannot use `print`
            for line in pickup_lines:
                _ = file.write(line)

        return file.name

    def write_switch_grid(self, file: io.TextIOWrapper, c: Eq3Config | Eq6Config, verbose: bool = False) -> None:
        if isinstance(c, Eq3Config) and verbose:
            c = c.make_verbose()

        print("*               1    2    3    4    5    6    7    8    9   10", file=file)
        print(
            "  iopt1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iopt[:10]),
            file=file,
        )
        print(
            " iopt11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iopt[10:]),
            file=file,
        )
        if isinstance(c, Eq3Config):
            line = "  iopg1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(
                *c.iopg[:10]
            )
            print(line, file=file)

            line = " iopg11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(
                *c.iopg[10:]
            )
            print(line, file=file)
        print(
            "  iopr1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iopr[:10]),
            file=file,
        )
        print(
            " iopr11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iopr[10:]),
            file=file,
        )
        print(
            "  iodb1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iodb[:10]),
            file=file,
        )
        print(
            " iodb11-20= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(*c.iodb[10:]),
            file=file,
        )

    @staticmethod
    def _as_map(value: object) -> ParsedMap:
        return cast(ParsedMap, value)

    @staticmethod
    def _as_table(value: object) -> ParsedTable:
        table = cast(ParsedTable, value)
        return {name: Kernel._as_map(props) for name, props in table.items()}

    @staticmethod
    def _as_float(value: object) -> float:
        return float(cast(float | int, value))

    @staticmethod
    def _as_opt_float(value: object) -> float | None:
        if value is None:
            return None
        return Kernel._as_float(value)

    @staticmethod
    def _build_pure_solid(
        name: str,
        log_qk: float,
        affinity: float,
        log_moles: float | None,
        log_mass: float | None,
        log_volume: float | None,
    ) -> es.PureSolid:
        return es.PureSolid(
            name=name,
            log_qk=log_qk,
            affinity=affinity,
            log_moles=log_moles,
            log_mass=log_mass,
            log_volume=log_volume,
        )

    @staticmethod
    def read_eq3_output(file: str | io.TextIOWrapper | None = None) -> es.Point:
        parser = OutputParser3(file=file).parse()
        raw = Kernel._as_map(parser.data)

        ph_scales = Kernel._as_table(raw["pH"])
        nbs_pH_scale = Kernel._as_map(ph_scales["NBS pH scale"])
        alkalinity = Kernel._as_map(raw.get("alkalinity", {}))
        extended_alkalinity = Kernel._as_opt_float(Kernel._as_map(alkalinity.get("Extended", {})).get("Total"))

        elements: list[es.Element] = []
        for name, props in Kernel._as_table(raw["elements"]).items():
            elements.append(
                es.Element(
                    name=name,
                    log_molality=Kernel._as_float(props["log_molality"]),
                    mass_fraction=Kernel._as_float(props["mass_fraction"]),
                )
            )

        aqueous_species: list[es.AqueousSpecies] = []
        for name, props in Kernel._as_table(raw["aqueous"]).items():
            molality = Kernel._as_float(props["molality"])
            log_activity = Kernel._as_float(props["log_activity"])
            aqueous_species.append(
                es.AqueousSpecies(
                    name=name,
                    log_molality=-math.inf if molality == 0 else Kernel._as_float(props["log_molality"]),
                    log_activity=-math.inf if log_activity == -99999 else log_activity,
                    log_gamma=Kernel._as_float(props["log_gamma"]),
                )
            )

        solids = Kernel._as_map(raw["solids"])
        pure_solids: list[es.PureSolid] = []
        for name, props in Kernel._as_table(solids["pure_solids"]).items():
            moles = Kernel._as_opt_float(props.get("moles"))
            mass = Kernel._as_opt_float(props.get("mass"))
            volume = Kernel._as_opt_float(props.get("volume"))
            pure_solids.append(
                Kernel._build_pure_solid(
                    name=name,
                    log_qk=Kernel._as_float(props["log_qk"]),
                    affinity=Kernel._as_float(props["affinity"]),
                    log_moles=-math.inf if moles == -99999 else Kernel._as_opt_float(props.get("log_moles")),
                    log_mass=-math.inf if mass == -99999 else Kernel._as_opt_float(props.get("log_mass")),
                    log_volume=-math.inf if volume == -99999 else Kernel._as_opt_float(props.get("log_volume")),
                )
            )

        solid_solutions: list[es.SolidSolution] = []
        for name, props in Kernel._as_table(solids["solid_solutions"]).items():
            end_members: list[es.EndMember] = []
            for em_name, em_props in Kernel._as_table(props.get("end_members", {})).items():
                end_members.append(
                    es.EndMember(
                        name=em_name,
                        log_qk=Kernel._as_float(em_props["log_qk"]),
                        affinity=Kernel._as_float(em_props["affinity"]),
                        log_moles=Kernel._as_opt_float(em_props.get("log_moles")),
                        log_mass=Kernel._as_opt_float(em_props.get("log_mass")),
                        log_volume=Kernel._as_opt_float(em_props.get("log_volume")),
                    )
                )

            solid_solutions.append(
                es.SolidSolution(
                    name=name,
                    log_qk=Kernel._as_float(props["log_qk"]),
                    affinity=Kernel._as_float(props["affinity"]),
                    log_moles=Kernel._as_opt_float(props.get("log_moles")),
                    log_mass=Kernel._as_opt_float(props.get("log_mass")),
                    log_volume=Kernel._as_opt_float(props.get("log_volume")),
                    end_members=end_members,
                )
            )

        gases: list[es.Gas] = []
        for name, props in Kernel._as_table(raw["gases"]).items():
            gases.append(es.Gas(name=name, log_fugacity=Kernel._as_float(props["log_fugacity"])))

        redox_reactions: list[es.RedoxReaction] = []
        for couple, props in Kernel._as_table(raw["redox"]).items():
            redox_reactions.append(
                es.RedoxReaction(
                    couple=couple,
                    Eh=Kernel._as_float(props["Eh"]),
                    pe=Kernel._as_float(props["pe-"]),
                    log_fO2=Kernel._as_float(props["log_fO2"]),
                    Ah=Kernel._as_float(props["Ah"]),
                )
            )

        return es.Point(
            stage="eq3",
            temperature=Kernel._as_float(raw["temperature"]),
            pressure=Kernel._as_float(raw["pressure"]),
            pH=Kernel._as_float(nbs_pH_scale["pH"]),
            log_fO2=Kernel._as_float(raw["log_fO2"]),
            log_activity_water=Kernel._as_float(raw["log_activity_water"]),
            mole_fraction_water=Kernel._as_float(raw["mole_fraction_water"]),
            log_gamma_water=Kernel._as_float(raw["log_activity_coefficient_water"]),
            Eh=Kernel._as_float(nbs_pH_scale["Eh"]),
            pe=Kernel._as_float(nbs_pH_scale["pe-"]),
            Ah=Kernel._as_float(nbs_pH_scale["Ah"]),
            pcH=Kernel._as_opt_float(raw.get("pcH")),
            pHCl=Kernel._as_opt_float(raw.get("pHCl")),
            log_ionic_strength=Kernel._as_float(raw["log_ionic_strength"]),
            log_stoichiometric_ionic_strength=Kernel._as_float(raw["log_stoichiometric_ionic_strength"]),
            log_ionic_asymmetry=Kernel._as_float(raw["log_ionic_asymmetry"]),
            log_stoichiometric_ionic_asymmetry=Kernel._as_float(raw["log_stoichiometric_ionic_asymmetry"]),
            osmotic_coefficient=Kernel._as_float(raw["osmotic_coefficient"]),
            stoichiometric_osmotic_coefficient=Kernel._as_float(raw["stoichiometric_osmotic_coefficient"]),
            log_sum_molalities=Kernel._as_float(raw["log_sum_molalities"]),
            log_sum_stoichiometric_molalities=Kernel._as_float(raw["log_sum_stoichiometric_molalities"]),
            charge_imbalance=Kernel._as_float(raw["charge_imbalance"]),
            anions=Kernel._as_opt_float(raw.get("anions")),
            cations=Kernel._as_opt_float(raw.get("cations")),
            total_charge=Kernel._as_opt_float(raw.get("total_charge")),
            mean_charge=Kernel._as_opt_float(raw.get("mean_charge")),
            solute_mass=Kernel._as_float(raw["solute_mass"]),
            solvent_mass=Kernel._as_float(raw["solvent_mass"]),
            solution_mass=Kernel._as_float(raw["solution_mass"]),
            solution_volume=Kernel._as_opt_float(raw.get("solution_volume")),
            tds=Kernel._as_float(raw["tds"]),
            solute_fraction=Kernel._as_float(raw["solute_fraction"]),
            solvent_fraction=Kernel._as_float(raw["solvent_fraction"]),
            extended_alkalinity=extended_alkalinity,
            elements=elements,
            aqueous_species=aqueous_species,
            pure_solids=pure_solids,
            solid_solutions=solid_solutions,
            gases=gases,
            redox_reactions=redox_reactions,
        )

    @staticmethod
    def read_eq6_output(file: str | io.TextIOWrapper | None = None, track_path: bool = False) -> list[es.Point]:
        path: list[es.Point] = []

        steps = [Kernel._as_map(step) for step in OutputParser6(file=file).parse().path]
        if not track_path:
            steps = steps[-1:]

        for step in steps:
            ph_scales = Kernel._as_table(step["pH"])
            nbs_pH_scale = Kernel._as_map(ph_scales["NBS pH scale"])
            solids = Kernel._as_map(step["solids"])

            reactant_summary = Kernel._as_map(step.get("reactants", {}))
            alkalinity = Kernel._as_map(step.get("alkalinity", {}))
            extended_alkalinity = Kernel._as_opt_float(Kernel._as_map(alkalinity.get("Extended", {})).get("Total"))

            created_solids = Kernel._as_map(solids.get("created", {}))
            destroyed_solids = Kernel._as_map(solids.get("destroyed", {}))
            net_solids = Kernel._as_map(solids.get("net", {}))

            elements: list[es.Element] = []
            for name, props in Kernel._as_table(step["elements"]).items():
                elements.append(
                    es.Element(
                        name=name,
                        log_molality=Kernel._as_float(props["log_molality"]),
                        mass_fraction=Kernel._as_float(props["mass_fraction"]),
                    )
                )

            aqueous_species: list[es.AqueousSpecies] = []
            for name, props in Kernel._as_table(step["aqueous"]).items():
                if name == "O2(g)":
                    continue
                molality = Kernel._as_float(props["molality"])
                log_activity = Kernel._as_float(props["log_activity"])
                aqueous_species.append(
                    es.AqueousSpecies(
                        name=name,
                        log_molality=-math.inf if molality == 0 else Kernel._as_float(props["log_molality"]),
                        log_activity=-math.inf if log_activity == -99999 else log_activity,
                        log_gamma=Kernel._as_float(props["log_gamma"]),
                    )
                )

            pure_solids: list[es.PureSolid] = []
            for name, props in Kernel._as_table(solids["pure_solids"]).items():
                moles = Kernel._as_opt_float(props.get("moles"))
                pure_solids.append(
                    Kernel._build_pure_solid(
                        name=name,
                        log_qk=Kernel._as_float(props["log_qk"]),
                        affinity=Kernel._as_float(props["affinity"]),
                        log_moles=-math.inf if moles == 0 else Kernel._as_opt_float(props.get("log_moles")),
                        log_mass=Kernel._as_opt_float(props.get("log_mass")),
                        log_volume=Kernel._as_opt_float(props.get("log_volume")),
                    )
                )

            solid_solutions: list[es.SolidSolution] = []
            for name, props in Kernel._as_table(solids["solid_solutions"]).items():
                end_members: list[es.EndMember] = []
                for em_name, em_props in Kernel._as_table(props.get("end_members", {})).items():
                    end_members.append(
                        es.EndMember(
                            name=em_name,
                            log_qk=Kernel._as_float(em_props["log_qk"]),
                            affinity=Kernel._as_float(em_props["affinity"]),
                            log_moles=Kernel._as_opt_float(em_props.get("log_moles")),
                            log_mass=Kernel._as_opt_float(em_props.get("log_mass")),
                            log_volume=Kernel._as_opt_float(em_props.get("log_volume")),
                        )
                    )

                solid_solutions.append(
                    es.SolidSolution(
                        name=name,
                        log_qk=Kernel._as_float(props["log_qk"]),
                        affinity=Kernel._as_float(props["affinity"]),
                        log_moles=Kernel._as_opt_float(props.get("log_moles")),
                        log_mass=Kernel._as_opt_float(props.get("log_mass")),
                        log_volume=Kernel._as_opt_float(props.get("log_volume")),
                        end_members=end_members,
                    )
                )

            gases: list[es.Gas] = []
            for name, props in Kernel._as_table(step["gases"]).items():
                gases.append(es.Gas(name=name, log_fugacity=Kernel._as_float(props["log_fugacity"])))

            reactants: list[es.Reactant] = []
            for name, props in Kernel._as_table(reactant_summary.get("reactants", {})).items():
                reactants.append(
                    es.Reactant(
                        name=name,
                        affinity=Kernel._as_float(props["affinity"]),
                        relative_rate=Kernel._as_float(props["relative_rate"]),
                        log_moles_reacted=Kernel._as_float(props["log_moles_reacted"]),
                        log_moles_remaining=Kernel._as_float(props["log_moles_remaining"]),
                        log_mass_reacted=Kernel._as_float(props["log_mass_reacted"]),
                        log_mass_remaining=Kernel._as_float(props["log_mass_remaining"]),
                    )
                )

            redox_reactions: list[es.RedoxReaction] = []
            for couple, props in Kernel._as_table(step["redox"]).items():
                redox_reactions.append(
                    es.RedoxReaction(
                        couple=couple,
                        Eh=Kernel._as_float(props["Eh"]),
                        pe=Kernel._as_float(props["pe-"]),
                        log_fO2=Kernel._as_float(props["log_fO2"]),
                        Ah=Kernel._as_float(props["Ah"]),
                    )
                )

            path.append(
                es.Point(
                    stage="eq6",
                    log_xi=Kernel._as_float(step["log_xi"]),
                    temperature=Kernel._as_float(step["temperature"]),
                    pressure=Kernel._as_float(step["pressure"]),
                    pH=Kernel._as_float(nbs_pH_scale["pH"]),
                    Eh=Kernel._as_float(nbs_pH_scale["Eh"]),
                    pe=Kernel._as_float(nbs_pH_scale["pe-"]),
                    Ah=Kernel._as_float(nbs_pH_scale["Ah"]),
                    pHCl=Kernel._as_opt_float(step.get("pHCl")),
                    log_fO2=Kernel._as_float(step["log_fO2"]),
                    log_activity_water=Kernel._as_float(step["log_activity_water"]),
                    mole_fraction_water=Kernel._as_float(step["mole_fraction_water"]),
                    log_gamma_water=Kernel._as_float(step["log_activity_coefficient_water"]),
                    osmotic_coefficient=Kernel._as_float(step["osmotic_coefficient"]),
                    stoichiometric_osmotic_coefficient=Kernel._as_float(step["stoichiometric_osmotic_coefficient"]),
                    log_sum_molalities=Kernel._as_float(step["log_sum_molalities"]),
                    log_sum_stoichiometric_molalities=Kernel._as_float(step["log_sum_stoichiometric_molalities"]),
                    log_ionic_strength=Kernel._as_float(step["log_ionic_strength"]),
                    log_stoichiometric_ionic_strength=Kernel._as_float(step["log_stoichiometric_ionic_strength"]),
                    log_ionic_asymmetry=Kernel._as_float(step["log_ionic_asymmetry"]),
                    log_stoichiometric_ionic_asymmetry=Kernel._as_float(step["log_stoichiometric_ionic_asymmetry"]),
                    solute_mass=Kernel._as_float(step["solute_mass"]),
                    solvent_mass=Kernel._as_float(step["solvent_mass"]),
                    solution_mass=Kernel._as_float(step["solution_mass"]),
                    tds=Kernel._as_float(step["tds"]),
                    solute_fraction=Kernel._as_float(step["solute_fraction"]),
                    solvent_fraction=Kernel._as_float(step["solvent_fraction"]),
                    charge_imbalance=Kernel._as_float(step["charge_imbalance"]),
                    expected_charge_imbalance=Kernel._as_opt_float(step.get("expected_charge_imbalance")),
                    charge_discrepancy=Kernel._as_opt_float(step.get("charge_discrepancy")),
                    sigma=Kernel._as_opt_float(step.get("sigma")),
                    extended_alkalinity=extended_alkalinity,
                    overall_affinity=Kernel._as_opt_float(reactant_summary.get("overall_affinity")),
                    reactant_mass_reacted=Kernel._as_float(reactant_summary.get("mass_reacted", 0.0)),
                    reactant_mass_remaining=Kernel._as_float(reactant_summary.get("mass_remaining", 0.0)),
                    solid_mass_created=Kernel._as_float(created_solids.get("mass", 0.0)),
                    solid_mass_destroyed=Kernel._as_float(destroyed_solids.get("mass", 0.0)),
                    solid_mass_change=Kernel._as_float(net_solids.get("mass", 0.0)),
                    solid_volume_created=Kernel._as_float(created_solids.get("volume", 0.0)),
                    solid_volume_destroyed=Kernel._as_float(destroyed_solids.get("volume", 0.0)),
                    solid_volume_change=Kernel._as_float(net_solids.get("volume", 0.0)),
                    elements=elements,
                    aqueous_species=aqueous_species,
                    pure_solids=pure_solids,
                    solid_solutions=solid_solutions,
                    gases=gases,
                    reactants=reactants,
                    redox_reactions=redox_reactions,
                )
            )

        return path


_ = AbstractKernel.register(Kernel)
