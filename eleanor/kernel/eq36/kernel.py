import io
import os
import sys
from datetime import datetime
from pathlib import Path
from shutil import copyfile
from typing import TextIO, Unpack, cast, override

import numpy as np

import eleanor.equilibrium_space as es
import eleanor.util as tool_room
import eleanor.variable_space as vs
from eleanor.constraints.point_builder import PointBuilder
from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.constraints import TemperatureRangeConstraint, TPCurveConstraint
from eleanor.kernel.eq36.data1 import Data1
from eleanor.kernel.eq36.exec import eq3, eq6
from eleanor.kernel.eq36.parsers import OutputParser3, OutputParser6
from eleanor.kernel.eq36.settings import IOPT_1, IOPT_4, Eq3Settings, Eq6Settings, Eq36Settings
from eleanor.kernel.eq36.util import read_pickup_lines
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.interface import AbstractKernel
from eleanor.order import Order
from eleanor.typing import EleanorKwargs, StrPath
from eleanor.util import NumberFormat, guard_is_instance, guard_is_path


class Eq36Kernel(AbstractKernel):
    _setup: bool
    _data1s: list[Data1]

    def __init__(self) -> None:
        self._setup = False
        self._data1s = []

    @override
    def is_soft_exit(self, code: int) -> bool:
        return code in {0, 60}

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
        dir: StrPath = ".",
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        dir = Path(dir)
        verbose = kwargs.get("verbose", False)
        settings = self.resolve_kernel_settings(vs_point)
        if settings.data1_file is None:
            data1 = self.find_data1(vs_point, verbose=verbose)
            settings.data1_file = data1.filename
        _ = copyfile(settings.data1_file, dir / settings.data1_file.name)

    @override
    def get_atomic_weight(self, element: str) -> np.float64 | None:
        if not self._setup or len(self._data1s) == 0:
            raise EleanorException("cannot get atomic masses until the kernel is setup")
        return self._data1s[0].elements.get(element)

    @override
    def get_molar_mass(
        self,
        species_name: str,
        mole_fractions: dict[str, np.float64] | None = None,
    ) -> np.float64 | None:
        if not self._setup or len(self._data1s) == 0:
            raise EleanorException("cannot get molar masses until the kernel is setup")
        try:
            return self._data1s[0].molar_mass(species_name, mole_fractions)
        except KeyError:
            return None

    @override
    def prepare_setup_args(self, *args: object) -> dict[str, object]:
        if not args:
            raise EleanorException("data1_dir argument is required")

        data1_dir, *_ = args
        guard_is_path(data1_dir, "data1_dir argument")

        return {"data1_dir": data1_dir}

    @override
    def setup(
        self,
        order: Order,
        *,
        data1_dir: object,
        **kwargs: object,
    ) -> None:
        guard_is_instance(order, Order, f"order provided to {type(self).__name__}.setup")

        if not isinstance(order.kernel.settings, Eq36Settings):
            msg = f"order is not configured for the eq36 kernel, got {type(order.kernel.settings).__name__}"
            raise EleanorKernelException(msg)

        if not isinstance(data1_dir, (str, Path)):
            msg = f"data1_dir must be a str or Path, got {type(data1_dir).__name__}"
            raise EleanorException(msg)
        data1_dir = Path(data1_dir)

        if not data1_dir.is_absolute():
            global_data1_dir = os.environ.get("ELEANOR_EQ36_DATA1_DIR")
            if not data1_dir.exists() and global_data1_dir is not None:
                data1_dir = Path(global_data1_dir) / data1_dir

        self._setup = False
        self._data1s = []

        Trange = order.temperature.range()
        Prange = order.pressure.range()

        with tool_room.WorkingDirectory(data1_dir):
            _, data1_files, *_ = tool_room.find_files(".d1")
            for file in data1_files:
                data1 = Data1.from_file(file.resolve())
                if data1.tp_curve is not None and data1.tp_curve.set_domain(Trange, Prange):
                    self._data1s.append(data1)

        self._setup = True

    def resolve_kernel_settings(self, vs_point: vs.Point) -> Eq36Settings:
        if not isinstance(vs_point.kernel.settings, Eq36Settings):
            raise TypeError(
                f"the provided problem.kernel has type {type(vs_point.kernel.settings)} expected {Eq36Settings}",
            )

        settings = vs_point.kernel.settings

        suppress_all_solid_solutions = False
        suppress_named_solid_solutions = False
        for suppression in vs_point.suppressions:
            if suppression.type in ["solid solution", "solid solutions"]:
                if len(suppression.exceptions) != 0:
                    raise NotImplementedError("solid solution exemptions are not yet supported")
                if suppression.name is None:
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
    def constrain(self, point_builder: PointBuilder) -> PointBuilder:
        if not self._setup:
            raise EleanorKernelException("kernel is not setup; cannot constraint orders")

        point_builder.constraints.append(
            TemperatureRangeConstraint(
                point_builder.order.temperature,
                self._data1s,
            ),
        )

        point_builder.constraints.append(
            TPCurveConstraint(
                point_builder.order.temperature,
                point_builder.order.pressure,
                self._data1s,
            ),
        )

        return point_builder

    def find_data1(self, vs_point: vs.Point, verbose: bool = False) -> Data1:
        T: np.float64 = vs_point.temperature
        P: np.float64 = vs_point.pressure

        d1s: list[Data1] = []
        for data1 in self._data1s:
            curve = data1.tp_curve
            if curve is not None and curve.temperature_in_domain(T) and curve(T) == P:
                d1s.append(data1)

        if len(d1s) == 0:
            raise EleanorKernelException(f"failed to find a data1 file with temperature {T} and pressure {P}")
        if len(d1s) > 1 and verbose:
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
            eq3_results = self.read_eq3_output()
            complete_date = datetime.now()
            eq3_results.start_date, eq3_results.complete_date = start_date, complete_date

            if settings.eq6_config is None:
                eq6_results: list[es.Point] = []
            else:
                start_date = datetime.now()
                pickup_lines = read_pickup_lines()
                eq6_input_path = self.write_eq6_input(vs_point, pickup_lines=pickup_lines, verbose=verbose)
                _ = eq6(settings.data1_file, eq6_input_path, timeout=settings.timeout)
                eq6_results = self.read_eq6_output(track_path=settings.track_path)
                complete_date = datetime.now()
                for point in eq6_results:
                    point.start_date, point.complete_date = start_date, complete_date

            return [eq3_results, *eq6_results]
        except EleanorException:
            raise
        except Exception as e:
            raise EleanorException("an unexpected error occurred") from e

    def write_eq3_input(
        self,
        vs_point: vs.Point,
        data1: Data1,
        file: StrPath | TextIO | None = None,
        verbose: bool = False,
    ) -> str:
        if not self._setup:
            raise EleanorKernelException("kernel is not setup; cannot write eq3 input file")

        settings = cast(Eq36Settings, vs_point.kernel.settings)
        if not vs_point.has_species_constraint(settings.redox_species):
            if settings.redox_species == "fO2" and vs_point.has_species_constraint("O2(g)"):
                pass
            else:
                raise EleanorKernelException(f"eq3/6 redox species ({settings.redox_species}) is unconstrained")

        if file is None:
            file = Path("problem.3i")

        if isinstance(file, (str, Path)):
            with Path(file).open("w") as handle:
                return self.write_eq3_input(vs_point, data1, file=handle, verbose=verbose)

        # Write header
        print(f"EQ3NR input file name= {Path(file.name).name}", file=file)
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

        if settings.redox_species in {"fO2", "O2(g)"}:
            use_other_species = 0
            fO2 = vs_point.get_species("O2(g)")
            if fO2 is None:
                raise EleanorKernelException(f'cannot find redox species "{settings.redox_species}"')

            value = NumberFormat.SCIENTIFIC.fmt(fO2.value, precision=5)
            redox_species = "None"
        else:
            use_other_species = 1
            value = NumberFormat.SCIENTIFIC.fmt(np.float64(0), precision=5)
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
        file: StrPath | TextIO | None = None,
        pickup_lines: list[str] | None = None,
        verbose: bool = False,
    ) -> str:
        settings = cast(Eq36Settings, vs_point.kernel.settings)
        if settings.eq6_config is None:
            raise ValueError("no eq6_config provided")

        if not vs_point.has_species_constraint(settings.redox_species):
            if settings.redox_species == "fO2" and vs_point.has_species_constraint("O2(g)"):
                pass
            else:
                raise EleanorKernelException(f"eq3/6 redox species ({settings.redox_species}) is unconstrained")

        if file is None:
            file = Path("problem.6i")

        if isinstance(file, (str, Path)):
            with Path(file).open("w") as handle:
                return self.write_eq6_input(vs_point, file=handle, pickup_lines=pickup_lines, verbose=verbose)

        # Write Header
        jtemp = settings.eq6_config.jtemp
        ttk1 = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ttk1, precision=5)
        ttk2 = NumberFormat.SCIENTIFIC.fmt(settings.eq6_config.ttk2, precision=5)

        T = NumberFormat.SCIENTIFIC.fmt(vs_point.temperature, precision=5)

        nrct = vs_point.reactant_count() - len(vs_point.fixed_gas_reactants)

        print(f"EQ3NR input file name= {Path(file.name).name}", file=file)
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
                print(f"   {name: <28}          {frac}", file=file)

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
                c = NumberFormat.SCIENTIFIC.fmt(np.float64(count), precision=5)
                print(f"   {element: <2}          {c}", file=file)

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
            print(f"   {er.name: <2}          1.00000E+00", file=file)
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

    def write_switch_grid(self, file: TextIO, c: Eq3Settings | Eq6Settings, verbose: bool = False) -> None:
        if isinstance(c, Eq3Settings) and verbose:
            c = c.make_verbose()

        print("*               1    2    3    4    5    6    7    8    9   10", file=file)
        print(
            "  iopt1-10= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iopt[:10]),
            file=file,
        )
        print(
            " iopt11-20= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iopt[10:]),
            file=file,
        )
        if isinstance(c, Eq3Settings):
            line = "  iopg1-10= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(
                *c.iopg[:10],
            )
            print(line, file=file)

            line = " iopg11-20= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(
                *c.iopg[10:],
            )
            print(line, file=file)
        print(
            "  iopr1-10= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iopr[:10]),
            file=file,
        )
        print(
            " iopr11-20= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iopr[10:]),
            file=file,
        )
        print(
            "  iodb1-10= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iodb[:10]),
            file=file,
        )
        print(
            " iodb11-20= {: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}{: >5}".format(*c.iodb[10:]),
            file=file,
        )

    @staticmethod
    def read_eq3_output(file: StrPath | io.TextIOWrapper | None = None) -> es.Point:
        parser = OutputParser3(file=file).parse()
        assert parser.point is not None
        return parser.point

    @staticmethod
    def read_eq6_output(file: StrPath | io.TextIOWrapper | None = None, track_path: bool = False) -> list[es.Point]:
        path = OutputParser6(file=file).parse().path
        return path if track_path else path[-1:]


_ = AbstractKernel.register(Eq36Kernel)
