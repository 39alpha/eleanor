import json
import os.path
from dataclasses import dataclass

from eleanor.config.parameter import Parameter
from eleanor.exceptions import EleanorException, EleanorParserException
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.eq36.settings import *
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.problem import AbstractConstraint
from eleanor.typing import Number, Optional, Self

from .data0_tools import TPCurve

EQ36_MODEL_EXTENSIONS: dict[str, str] = {
    'dav': 'davies',
    'com': 'b-dot',
    'cmp': 'b-dot',
    'ymp': 'b-dot',
    'cm1': 'b-dot',
    'cm2': 'b-dot',
    'cm3': 'b-dot',
    'alt': 'b-dot',
    'sup': 'b-dot',
    'nea': 'b-dot',
    'cod': 'b-dot',
    'chv': 'b-dot',
    'cv1': 'b-dot',
    'cv2': 'b-dot',
    'cv3': 'b-dot',
    'phr': 'b-dot',
    'skb': 'b-dot',
    'wat': 'b-dot',
    'bdt': 'b-dot',
    'pit': 'pitzer',
    'pt1': 'pitzer',
    'pt2': 'pitzer',
    'pt3': 'pitzer',
    'hmw': 'pitzer',
    'ypf': 'pitzer',
    'fmt': 'pitzer',
    'ppz': 'pitzer',
    'pze': 'pitzer',
    'fwe': 'pitzer',
    'gmo': 'pitzer',
    'smw': 'pitzer',
    'ub0': 'pitzer',
    'ubr': 'pitzer'
}


@dataclass(init=False)
class Eq3Config(object):
    iopt: list[int]
    iopg: list[int]
    iopr: list[int]
    iodb: list[int]

    def __init__(self, iopt_4: IOPT_4, iopt_11: IOPT_11, iopt_17: IOPT_17, iopt_19: IOPT_19, iopg_1: IOPG_1,
                 iopg_2: IOPG_2, iopr_1: IOPR_1, iopr_2: IOPR_2, iopr_3: IOPR_3, iopr_4: IOPR_4, iopr_5: IOPR_5,
                 iopr_6: IOPR_6, iopr_7: IOPR_7, iopr_8: IOPR_8, iopr_9: IOPR_9, iopr_10: IOPR_10, iopr_17: IOPR_17,
                 iodb_1: IODB_1, iodb_3: IODB_3, iodb_4: IODB_4, iodb_6: IODB_6):

        self.iopt = [0, 0, 0, iopt_4, 0, 0, 0, 0, 0, 0, iopt_11, 0, 0, 0, 0, 0, iopt_17, 0, iopt_19, 0]

        self.iopg = [iopg_1, iopg_2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        self.iopr = [
            iopr_1, iopr_2, iopr_3, iopr_4, iopr_5, iopr_6, iopr_7, iopr_8, iopr_9, iopr_10, 0, 0, 0, 0, 0, 0, iopr_17,
            0, 0, 0
        ]

        self.iodb = [iodb_1, 0, iodb_3, iodb_4, 0, iodb_6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    def get_iopt(self, n: int) -> int:
        try:
            return self.iopt[n - 1]
        except IndexError:
            raise IndexError(f'iopt_{n} is undefined')

    def set_iopt(self, n: int, value: IntEnum):
        try:
            self.iopt[n - 1] = value
        except IndexError:
            raise IndexError(f'iopt_{n} is undefined')

    def get_iopg(self, n: int) -> int:
        try:
            return self.iopg[n - 1]
        except IndexError:
            raise IndexError(f'iopg_{n} is undefined')

    def set_iopg(self, n: int, value: IntEnum):
        try:
            self.iopg[n - 1] = value
        except IndexError:
            raise IndexError(f'iopg_{n} is undefined')

    def get_iopr(self, n: int) -> int:
        try:
            return self.iopr[n - 1]
        except IndexError:
            raise IndexError(f'iopr_{n} is undefined')

    def set_iopr(self, n: int, value: IntEnum):
        try:
            self.iopr[n - 1] = value
        except IndexError:
            raise IndexError(f'iopr_{n} is undefined')

    def get_iodb(self, n: int) -> int:
        try:
            return self.iodb[n - 1]
        except IndexError:
            raise IndexError(f'iodb_{n} is undefined')

    def set_iodb(self, n: int, value: IntEnum):
        try:
            self.iodb[n - 1] = value
        except IndexError:
            raise IndexError(f'iodb_{n} is undefined')

    def to_row(self) -> dict:
        d = {}
        for i in range(1, 21):
            d[f'iopt_{i}'] = self.get_iopt(i)
        for i in range(1, 21):
            d[f'iopg_{i}'] = self.get_iopg(i)
        for i in range(1, 21):
            d[f'iopr_{i}'] = self.get_iopr(i)
        for i in range(1, 21):
            d[f'iodb_{i}'] = self.get_iodb(i)
        return d

    def make_verbose(self) -> Self:
        return type(self)(iopt_4=IOPT_4.PERMIT_SS,
                          iopt_11=IOPT_11(self.get_iopt(11)),
                          iopt_17=IOPT_17(self.get_iopt(17)),
                          iopt_19=IOPT_19(self.get_iopt(19)),
                          iopg_1=IOPG_1(self.get_iopg(1)),
                          iopg_2=IOPG_2(self.get_iopg(2)),
                          iopr_1=IOPR_1.PRINT_DATA_FILE_SP,
                          iopr_2=IOPR_2.PRINT_RXNS_LOGK_DATA,
                          iopr_3=IOPR_3(self.get_iopr(3)),
                          iopr_4=IOPR_4.INCLUDE_ALL_AQ,
                          iopr_5=IOPR_5.PRINT_CAT_AN_NU_RATIOS,
                          iopr_6=IOPR_6.PRINT_ALL_SP_MASS_BAL,
                          iopr_7=IOPR_7.PRINT_ALL_AFFINITIES,
                          iopr_8=IOPR_8(self.get_iopr(8)),
                          iopr_9=IOPR_9.PRINT_MEAN_ACTIVITY_COE,
                          iopr_10=IOPR_10(self.get_iopr(10)),
                          iopr_17=IOPR_17(self.get_iopr(17)),
                          iodb_1=IODB_1.PRINT_LEVEL_1_2_DIAG,
                          iodb_3=IODB_3.MOST_DETAILED_PRE_NR_DIAG,
                          iodb_4=IODB_4.MOST_DETAILED_NR_INFO,
                          iodb_6=IODB_6.DETAILED_AFFINITY_CALC)


@dataclass(init=False)
class Eq6Config(object):
    jtemp: JTEMP
    xi_max: Number
    iopt: list[int]
    iopr: list[int]
    iodb: list[int]

    def __init__(self, jtemp: JTEMP, xi_max: Number, iopt_1: IOPT_1, iopt_2: IOPT_2, iopt_3: IOPT_3, iopt_4: IOPT_4,
                 iopt_5: IOPT_5, iopt_6: IOPT_6, iopt_7: IOPT_7, iopt_9: IOPT_9, iopt_10: IOPT_10, iopt_11: IOPT_11,
                 iopt_12: IOPT_12, iopt_13: IOPT_13, iopt_14: IOPT_14, iopt_15: IOPT_15, iopt_16: IOPT_16,
                 iopt_17: IOPT_17, iopt_18: IOPT_18, iopt_20: IOPT_20, iopr_1: IOPR_1, iopr_2: IOPR_2, iopr_3: IOPR_3,
                 iopr_4: IOPR_4, iopr_5: IOPR_5, iopr_6: IOPR_6, iopr_7: IOPR_7, iopr_8: IOPR_8, iopr_9: IOPR_9,
                 iopr_10: IOPR_10, iopr_17: IOPR_17, iodb_1: IODB_1, iodb_2: IODB_2, iodb_3: IODB_3, iodb_4: IODB_4,
                 iodb_5: IODB_5, iodb_6: IODB_6, iodb_7: IODB_7, iodb_8: IODB_8):
        self.jtemp = jtemp
        self.xi_max = xi_max

        self.iopt = [
            iopt_1, iopt_2, iopt_3, iopt_4, iopt_5, iopt_6, iopt_7, 0, iopt_9, iopt_10, iopt_11, iopt_12, iopt_13,
            iopt_14, iopt_15, iopt_16, iopt_17, iopt_18, 0, iopt_20
        ]

        self.iopr = [
            iopr_1, iopr_2, iopr_3, iopr_4, iopr_5, iopr_6, iopr_7, iopr_8, iopr_9, iopr_10, 0, 0, 0, 0, 0, 0, iopr_17,
            0, 0, 0
        ]

        self.iodb = [iodb_1, iodb_2, iodb_3, iodb_4, iodb_5, iodb_6, iodb_7, iodb_8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    def get_iopt(self, n: int) -> int:
        try:
            return self.iopt[n - 1]
        except IndexError:
            raise IndexError(f'iopt_{n} is undefined')

    def set_iopt(self, n: int, value: IntEnum):
        try:
            self.iopt[n - 1] = value
        except IndexError:
            raise IndexError(f'iopt_{n} is undefined')

    def get_iopr(self, n: int) -> int:
        try:
            return self.iopr[n - 1]
        except IndexError:
            raise IndexError(f'iopr_{n} is undefined')

    def set_iopr(self, n: int, value: IntEnum):
        try:
            self.iopr[n - 1] = value
        except IndexError:
            raise IndexError(f'iopr_{n} is undefined')

    def get_iodb(self, n: int) -> int:
        try:
            return self.iodb[n - 1]
        except IndexError:
            raise IndexError(f'iodb_{n} is undefined')

    def set_iodb(self, n: int, value: IntEnum):
        try:
            self.iodb[n - 1] = value
        except IndexError:
            raise IndexError(f'iodb_{n} is undefined')

    def to_row(self) -> dict:
        d = {}
        for i in range(1, 21):
            d[f'iopt_{i}'] = self.get_iopt(i)
        for i in range(1, 21):
            d[f'iopr_{i}'] = self.get_iopr(i)
        for i in range(1, 21):
            d[f'iodb_{i}'] = self.get_iodb(i)
        return d


@dataclass(init=False)
class Config(KernelConfig):
    model: str
    charge_balance: str
    basis_map: dict[str, str]
    eq3_config: Eq3Config
    eq6_config: Eq6Config
    redox_species: str
    data1_file: Optional[str]

    def __init__(self,
                 model: str,
                 charge_balance: str,
                 basis_map: dict[str, str],
                 eq3_config: Eq3Config,
                 eq6_config: Eq6Config,
                 redox_species: Optional[str] = None,
                 data1_file: Optional[str] = None):
        super().__init__(type='eq36')
        self.model = model
        self.charge_balance = charge_balance
        self.basis_map = {} if basis_map is None else basis_map
        self.eq3_config = eq3_config
        self.eq6_config = eq6_config
        self.redox_species = 'fO2' if redox_species is None else redox_species
        self.data1_file = data1_file

    @property
    def is_fully_specified(self) -> bool:
        return self.data1_file is not None

    def to_row(self) -> dict:
        d = super().to_row()
        d['model'] = self.model
        d['charge_balance'] = self.charge_balance
        d['redox_species'] = self.redox_species
        d['data1_file'] = os.path.basename(self.data1_file)
        d['basis_map'] = json.dumps(self.basis_map)
        for key, value in self.eq3_config.to_row().items():
            d[f'eq3_{key}'] = value
        for key, value in self.eq6_config.to_row().items():
            d[f'eq6_{key}'] = value

        return d

    @staticmethod
    def from_dict(raw: dict):
        model = raw['model']
        if not isinstance(model, str):
            raise EleanorParserException('kernel.model must be a string')

        model = EQ36_MODEL_EXTENSIONS.get(model, model)
        if model not in ['pitzer', 'davies', 'b-dot']:
            raise EleanorParserException(
                'kernel.model must be "pitzer", "davies", "b-dot" or a standard EQ3/6 file extension')

        charge_balance = raw['charge_balance']
        if not isinstance(charge_balance, str):
            raise EleanorParserException('kernel.charge_balance must be a string')

        basis_map = raw.get('basis_map', {})
        if not isinstance(basis_map, dict):
            raise EleanorParserException('kernel.basis_map must be a dict')

        raw_eq3_config: dict[str, int] = raw.get('eq3_config', dict())
        eq3_config = Eq3Config(
            iopt_4=IOPT_4(raw_eq3_config.get('iopt_4', 0)),
            iopt_11=IOPT_11(raw_eq3_config.get('iopt_11', 0)),
            iopt_17=IOPT_17(raw_eq3_config.get('iopt_17', 0)),
            iopt_19=IOPT_19(raw_eq3_config.get('iopt_19', 3)),
            iopg_1=IOPG_1(-1 if model == 'davies' else 0 if model == 'b-dot' else 1),
            iopg_2=IOPG_2(raw_eq3_config.get('iopg_2', 0)),
            iopr_1=IOPR_1(raw_eq3_config.get('iopr_1', 0)),
            iopr_2=IOPR_2(raw_eq3_config.get('iopr_2', 0)),
            iopr_3=IOPR_3(raw_eq3_config.get('iopr_3', 0)),
            iopr_4=IOPR_4(raw_eq3_config.get('iopr_4', 1)),
            iopr_5=IOPR_5(raw_eq3_config.get('iopr_5', 0)),
            iopr_6=IOPR_6(raw_eq3_config.get('iopr_6', -1)),
            iopr_7=IOPR_7(raw_eq3_config.get('iopr_7', 1)),
            iopr_8=IOPR_8(raw_eq3_config.get('iopr_8', 0)),
            iopr_9=IOPR_9(raw_eq3_config.get('iopr_9', 0)),
            iopr_10=IOPR_10(raw_eq3_config.get('iopr_10', 0)),
            iopr_17=IOPR_17(raw_eq3_config.get('iopr_17', 0)),
            iodb_1=IODB_1(raw_eq3_config.get('iodb_1', 0)),
            iodb_3=IODB_3(raw_eq3_config.get('iodb_3', 0)),
            iodb_4=IODB_4(raw_eq3_config.get('iodb_4', 0)),
            iodb_6=IODB_6(raw_eq3_config.get('iodb_6', 0)),
        )

        if eq3_config.get_iopt(19) != IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX:
            msg = f'kernel.eq3_config.iopt_19 value ({eq3_config.get_iopt(19)}) is unsupported'
            raise EleanorParserException(msg)

        raw_eq6_config: dict[str, int] = raw.get('eq6_config', dict())
        eq6_config = Eq6Config(
            jtemp=JTEMP.CONSTANT_T,
            xi_max=float(raw_eq6_config.get('xi_max', 100)),
            iopt_1=IOPT_1(raw_eq6_config.get('iopt_1', 0)),
            iopt_2=IOPT_2(raw_eq6_config.get('iopt_2', 0)),
            iopt_3=IOPT_3(raw_eq6_config.get('iopt_3', 0)),
            iopt_4=IOPT_4(raw_eq6_config.get('iopt_4', 0)),
            iopt_5=IOPT_5(raw_eq6_config.get('iopt_5', 0)),
            iopt_6=IOPT_6(raw_eq6_config.get('iopt_6', 0)),
            iopt_7=IOPT_7(raw_eq6_config.get('iopt_7', 0)),
            iopt_9=IOPT_9(raw_eq6_config.get('iopt_9', 0)),
            iopt_10=IOPT_10(raw_eq6_config.get('iopt_10', 0)),
            iopt_11=IOPT_11(raw_eq6_config.get('iopt_11', 0)),
            iopt_12=IOPT_12(raw_eq6_config.get('iopt_12', 0)),
            iopt_13=IOPT_13(raw_eq6_config.get('iopt_13', 0)),
            iopt_14=IOPT_14(raw_eq6_config.get('iopt_14', 0)),
            iopt_15=IOPT_15(raw_eq6_config.get('iopt_15', 0)),
            iopt_16=IOPT_16(raw_eq6_config.get('iopt_16', -1)),
            iopt_17=IOPT_17(raw_eq6_config.get('iopt_17', 0)),
            iopt_18=IOPT_18(raw_eq6_config.get('iopt_18', -1)),
            iopt_20=IOPT_20(raw_eq6_config.get('iopt_20', 0)),
            iopr_1=IOPR_1(raw_eq6_config.get('iopr_1', 0)),
            iopr_2=IOPR_2(raw_eq6_config.get('iopr_2', 0)),
            iopr_3=IOPR_3(raw_eq6_config.get('iopr_3', 0)),
            iopr_4=IOPR_4(raw_eq6_config.get('iopr_4', 1)),
            iopr_5=IOPR_5(raw_eq6_config.get('iopr_5', 0)),
            iopr_6=IOPR_6(raw_eq6_config.get('iopr_6', -1)),
            iopr_7=IOPR_7(raw_eq6_config.get('iopr_7', 1)),
            iopr_8=IOPR_8(raw_eq6_config.get('iopr_8', 0)),
            iopr_9=IOPR_9(raw_eq6_config.get('iopr_9', 0)),
            iopr_10=IOPR_10(raw_eq6_config.get('iopr_10', 0)),
            iopr_17=IOPR_17(raw_eq6_config.get('iopr_17', 1)),
            iodb_1=IODB_1(raw_eq6_config.get('iodb_1', 0)),
            iodb_2=IODB_2(raw_eq6_config.get('iodb_2', 0)),
            iodb_3=IODB_3(raw_eq6_config.get('iodb_3', 0)),
            iodb_4=IODB_4(raw_eq6_config.get('iodb_4', 0)),
            iodb_5=IODB_5(raw_eq6_config.get('iodb_5', 0)),
            iodb_6=IODB_6(raw_eq6_config.get('iodb_6', 0)),
            iodb_7=IODB_7(raw_eq6_config.get('iodb_7', 0)),
            iodb_8=IODB_8(raw_eq6_config.get('iodb_8', 0)),
        )

        if eq6_config.xi_max < 0:
            msg = f'kernel.eq6_config.xi_max value ({eq6_config.xi_max}) is must be positive'
            raise EleanorParserException(msg)

        return Config(model, charge_balance, basis_map, eq3_config, eq6_config)


class TPCurveConstraint(AbstractConstraint):
    temperature: Parameter
    pressure: Parameter
    curves: list[TPCurve]
    _is_resolved: bool

    def __init__(self, temperature: Parameter, pressure: Parameter, curves: list[TPCurve]):
        super().__init__()

        self.temperature = temperature
        self.pressure = pressure
        self.curves = curves
        self._is_resolved = False

    @property
    def independent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    @property
    def dependent_parameters(self) -> list[Parameter]:
        return [self.pressure]

    @property
    def is_resolved(self) -> bool:
        return self._is_resolved

    def resolve(self) -> list[Parameter]:
        for parameter, domain in self.apply():
            if isinstance(domain, list):
                parameter.constrain_by_list(domain)
            elif isinstance(domain, tuple):
                parameter.constrain_by_range(*domain)
            else:
                parameter.constrain_by_value(domain)

        return self.dependent_parameters

    def apply(self) -> list[tuple[Parameter, Number | tuple[Number, Number] | list[Number]]]:
        if not self.temperature.is_fully_specified:
            return []

        T = self.temperature.value

        values: list[Number] = []
        for curve in self.curves:
            if curve.temperature_in_domain(T):
                P = curve(T)
                if self.pressure.value is not None:
                    if P != self.pressure.value:
                        continue
                elif self.pressure.min is not None and self.pressure.max is not None:
                    if P < self.pressure.min or P > self.pressure.max:
                        continue
                elif self.pressure.values is not None:
                    if P not in self.pressure.values:
                        continue
                else:
                    raise EleanorException('problem.pressure is invalid')

                values.append(curve(T))

        self._is_resolved = True

        return [(self.pressure, values)]


AbstractConstraint.register(TPCurveConstraint)
