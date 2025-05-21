from copy import copy
from dataclasses import dataclass, field

from eleanor.exceptions import EleanorException
from eleanor.kernel.config import Config as KernelConfig
from eleanor.typing import Number, Optional, Self
from eleanor.yeoman import JSONDict, yeoman_registry
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from .settings import *

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


@yeoman_registry.mapped
@dataclass
class Eq3Config(object):
    __table__ = Table(
        'eq3_config',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('eq36_config.id'), primary_key=True),
        Column('iopt_1', Eq36SettingField(IOPT_1), nullable=False),
        Column('iopt_2', Eq36SettingField(IOPT_2), nullable=False),
        Column('iopt_3', Eq36SettingField(IOPT_3), nullable=False),
        Column('iopt_4', Eq36SettingField(IOPT_4), nullable=False),
        Column('iopt_5', Eq36SettingField(IOPT_5), nullable=False),
        Column('iopt_6', Eq36SettingField(IOPT_6), nullable=False),
        Column('iopt_7', Eq36SettingField(IOPT_7), nullable=False),
        Column('iopt_9', Eq36SettingField(IOPT_9), nullable=False),
        Column('iopt_10', Eq36SettingField(IOPT_10), nullable=False),
        Column('iopt_11', Eq36SettingField(IOPT_11), nullable=False),
        Column('iopt_12', Eq36SettingField(IOPT_12), nullable=False),
        Column('iopt_13', Eq36SettingField(IOPT_13), nullable=False),
        Column('iopt_14', Eq36SettingField(IOPT_14), nullable=False),
        Column('iopt_15', Eq36SettingField(IOPT_15), nullable=False),
        Column('iopt_16', Eq36SettingField(IOPT_16), nullable=False),
        Column('iopt_17', Eq36SettingField(IOPT_17), nullable=False),
        Column('iopt_18', Eq36SettingField(IOPT_18), nullable=False),
        Column('iopt_19', Eq36SettingField(IOPT_19), nullable=False),
        Column('iopt_20', Eq36SettingField(IOPT_20), nullable=False),
        Column('iopg_1', Eq36SettingField(IOPG_1), nullable=False),
        Column('iopg_2', Eq36SettingField(IOPG_2), nullable=False),
        Column('iopr_1', Eq36SettingField(IOPR_1), nullable=False),
        Column('iopr_2', Eq36SettingField(IOPR_2), nullable=False),
        Column('iopr_3', Eq36SettingField(IOPR_3), nullable=False),
        Column('iopr_4', Eq36SettingField(IOPR_4), nullable=False),
        Column('iopr_5', Eq36SettingField(IOPR_5), nullable=False),
        Column('iopr_6', Eq36SettingField(IOPR_6), nullable=False),
        Column('iopr_7', Eq36SettingField(IOPR_7), nullable=False),
        Column('iopr_8', Eq36SettingField(IOPR_8), nullable=False),
        Column('iopr_9', Eq36SettingField(IOPR_9), nullable=False),
        Column('iopr_10', Eq36SettingField(IOPR_10), nullable=False),
        Column('iopr_17', Eq36SettingField(IOPR_17), nullable=False),
        Column('iodb_1', Eq36SettingField(IODB_1), nullable=False),
        Column('iodb_2', Eq36SettingField(IODB_2), nullable=False),
        Column('iodb_3', Eq36SettingField(IODB_3), nullable=False),
        Column('iodb_4', Eq36SettingField(IODB_4), nullable=False),
        Column('iodb_5', Eq36SettingField(IODB_5), nullable=False),
        Column('iodb_6', Eq36SettingField(IODB_6), nullable=False),
        Column('iodb_7', Eq36SettingField(IODB_7), nullable=False),
        Column('iodb_8', Eq36SettingField(IODB_8), nullable=False),
    )

    id: Optional[int] = None
    iopt_1: IOPT_1 = IOPT_1(0)
    iopt_2: IOPT_2 = IOPT_2(0)
    iopt_3: IOPT_3 = IOPT_3(0)
    iopt_4: IOPT_4 = IOPT_4(0)
    iopt_5: IOPT_5 = IOPT_5(0)
    iopt_6: IOPT_6 = IOPT_6(0)
    iopt_7: IOPT_7 = IOPT_7(0)
    iopt_9: IOPT_9 = IOPT_9(0)
    iopt_10: IOPT_10 = IOPT_10(0)
    iopt_11: IOPT_11 = IOPT_11(0)
    iopt_12: IOPT_12 = IOPT_12(0)
    iopt_13: IOPT_13 = IOPT_13(0)
    iopt_14: IOPT_14 = IOPT_14(0)
    iopt_15: IOPT_15 = IOPT_15(0)
    iopt_16: IOPT_16 = IOPT_16(0)
    iopt_17: IOPT_17 = IOPT_17(0)
    iopt_18: IOPT_18 = IOPT_18(0)
    iopt_19: IOPT_19 = IOPT_19(3)
    iopt_20: IOPT_20 = IOPT_20(0)
    iopg_1: IOPG_1 = IOPG_1(1)
    iopg_2: IOPG_2 = IOPG_2(0)
    iopr_1: IOPR_1 = IOPR_1(0)
    iopr_2: IOPR_2 = IOPR_2(0)
    iopr_3: IOPR_3 = IOPR_3(0)
    iopr_4: IOPR_4 = IOPR_4(1)
    iopr_5: IOPR_5 = IOPR_5(0)
    iopr_6: IOPR_6 = IOPR_6(-1)
    iopr_7: IOPR_7 = IOPR_7(1)
    iopr_8: IOPR_8 = IOPR_8(0)
    iopr_9: IOPR_9 = IOPR_9(0)
    iopr_10: IOPR_10 = IOPR_10(0)
    iopr_17: IOPR_17 = IOPR_17(0)
    iodb_1: IODB_1 = IODB_1(0)
    iodb_2: IODB_2 = IODB_2(0)
    iodb_3: IODB_3 = IODB_3(0)
    iodb_4: IODB_4 = IODB_4(0)
    iodb_5: IODB_5 = IODB_5(0)
    iodb_6: IODB_6 = IODB_6(0)
    iodb_7: IODB_7 = IODB_7(0)
    iodb_8: IODB_8 = IODB_8(0)

    @property
    def iopt(self) -> list[int]:
        return [
            self.iopt_1, self.iopt_2, self.iopt_3, self.iopt_4, self.iopt_5, self.iopt_6, self.iopt_7, self.iopt_9, 0,
            self.iopt_10, self.iopt_11, self.iopt_12, self.iopt_13, self.iopt_14, self.iopt_15, self.iopt_16,
            self.iopt_17, self.iopt_18, self.iopt_19, self.iopt_20
        ]

    @property
    def iopg(self) -> list[int]:
        return [self.iopg_1, self.iopg_2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    @property
    def iopr(self) -> list[int]:
        return [
            self.iopr_1, self.iopr_2, self.iopr_3, self.iopr_4, self.iopr_5, self.iopr_6, self.iopr_7, self.iopr_8,
            self.iopr_9, self.iopr_10, 0, 0, 0, 0, 0, 0, self.iopr_17, 0, 0, 0
        ]

    @property
    def iodb(self) -> list[int]:
        return [
            self.iodb_1, self.iodb_2, self.iodb_3, self.iodb_4, self.iodb_5, self.iodb_6, self.iodb_7, self.iodb_8, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        ]

    def make_verbose(self) -> Self:
        verbose = copy(self)

        verbose.iopt_4 = IOPT_4.PERMIT_SOLID_SOLUTIONS
        verbose.iopr_1 = IOPR_1.PRINT_DATA_FILE_SP
        verbose.iopr_2 = IOPR_2.PRINT_RXNS_LOGK_DATA
        verbose.iopr_4 = IOPR_4.INCLUDE_ALL_AQ
        verbose.iopr_5 = IOPR_5.PRINT_CAT_AN_NU_RATIOS
        verbose.iopr_6 = IOPR_6.PRINT_ALL_SP_MASS_BAL
        verbose.iopr_7 = IOPR_7.PRINT_ALL_AFFINITIES
        verbose.iopr_9 = IOPR_9.PRINT_MEAN_ACTIVITY_COE
        verbose.iodb_1 = IODB_1.PRINT_LEVEL_1_2_DIAG
        verbose.iodb_3 = IODB_3.MOST_DETAILED_PRE_NR_DIAG
        verbose.iodb_4 = IODB_4.MOST_DETAILED_NR_INFO
        verbose.iodb_6 = IODB_6.DETAILED_AFFINITY_CALC

        return verbose


@yeoman_registry.mapped
@dataclass
class Eq6Config(object):
    __table__ = Table(
        'eq6_config',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('eq36_config.id'), primary_key=True),
        Column('jtemp', Eq36SettingField(JTEMP), nullable=False),
        Column('xi_max', Integer, nullable=False),
        Column('iopt_1', Eq36SettingField(IOPT_1), nullable=False),
        Column('iopt_2', Eq36SettingField(IOPT_2), nullable=False),
        Column('iopt_3', Eq36SettingField(IOPT_3), nullable=False),
        Column('iopt_4', Eq36SettingField(IOPT_4), nullable=False),
        Column('iopt_5', Eq36SettingField(IOPT_5), nullable=False),
        Column('iopt_6', Eq36SettingField(IOPT_6), nullable=False),
        Column('iopt_7', Eq36SettingField(IOPT_7), nullable=False),
        Column('iopt_9', Eq36SettingField(IOPT_9), nullable=False),
        Column('iopt_10', Eq36SettingField(IOPT_10), nullable=False),
        Column('iopt_11', Eq36SettingField(IOPT_11), nullable=False),
        Column('iopt_12', Eq36SettingField(IOPT_12), nullable=False),
        Column('iopt_13', Eq36SettingField(IOPT_13), nullable=False),
        Column('iopt_14', Eq36SettingField(IOPT_14), nullable=False),
        Column('iopt_15', Eq36SettingField(IOPT_15), nullable=False),
        Column('iopt_16', Eq36SettingField(IOPT_16), nullable=False),
        Column('iopt_17', Eq36SettingField(IOPT_17), nullable=False),
        Column('iopt_18', Eq36SettingField(IOPT_18), nullable=False),
        Column('iopt_19', Eq36SettingField(IOPT_19), nullable=False),
        Column('iopt_20', Eq36SettingField(IOPT_20), nullable=False),
        Column('iopg_1', Eq36SettingField(IOPG_1), nullable=False),
        Column('iopg_2', Eq36SettingField(IOPG_2), nullable=False),
        Column('iopr_1', Eq36SettingField(IOPR_1), nullable=False),
        Column('iopr_2', Eq36SettingField(IOPR_2), nullable=False),
        Column('iopr_3', Eq36SettingField(IOPR_3), nullable=False),
        Column('iopr_4', Eq36SettingField(IOPR_4), nullable=False),
        Column('iopr_5', Eq36SettingField(IOPR_5), nullable=False),
        Column('iopr_6', Eq36SettingField(IOPR_6), nullable=False),
        Column('iopr_7', Eq36SettingField(IOPR_7), nullable=False),
        Column('iopr_8', Eq36SettingField(IOPR_8), nullable=False),
        Column('iopr_9', Eq36SettingField(IOPR_9), nullable=False),
        Column('iopr_10', Eq36SettingField(IOPR_10), nullable=False),
        Column('iopr_17', Eq36SettingField(IOPR_17), nullable=False),
        Column('iodb_1', Eq36SettingField(IODB_1), nullable=False),
        Column('iodb_2', Eq36SettingField(IODB_2), nullable=False),
        Column('iodb_3', Eq36SettingField(IODB_3), nullable=False),
        Column('iodb_4', Eq36SettingField(IODB_4), nullable=False),
        Column('iodb_5', Eq36SettingField(IODB_5), nullable=False),
        Column('iodb_6', Eq36SettingField(IODB_6), nullable=False),
        Column('iodb_7', Eq36SettingField(IODB_7), nullable=False),
        Column('iodb_8', Eq36SettingField(IODB_8), nullable=False),
    )

    id: Optional[int] = None
    jtemp: JTEMP = JTEMP.CONSTANT_T
    xi_max: Number = 100
    iopt_1: IOPT_1 = IOPT_1(0)
    iopt_2: IOPT_2 = IOPT_2(0)
    iopt_3: IOPT_3 = IOPT_3(0)
    iopt_4: IOPT_4 = IOPT_4(0)
    iopt_5: IOPT_5 = IOPT_5(0)
    iopt_6: IOPT_6 = IOPT_6(0)
    iopt_7: IOPT_7 = IOPT_7(0)
    iopt_9: IOPT_9 = IOPT_9(0)
    iopt_10: IOPT_10 = IOPT_10(0)
    iopt_11: IOPT_11 = IOPT_11(0)
    iopt_12: IOPT_12 = IOPT_12(0)
    iopt_13: IOPT_13 = IOPT_13(0)
    iopt_14: IOPT_14 = IOPT_14(0)
    iopt_15: IOPT_15 = IOPT_15(0)
    iopt_16: IOPT_16 = IOPT_16(-1)
    iopt_17: IOPT_17 = IOPT_17(0)
    iopt_18: IOPT_18 = IOPT_18(-1)
    iopt_19: IOPT_19 = IOPT_19(0)
    iopt_20: IOPT_20 = IOPT_20(0)
    iopg_1: IOPG_1 = IOPG_1(0)
    iopg_2: IOPG_2 = IOPG_2(0)
    iopr_1: IOPR_1 = IOPR_1(0)
    iopr_2: IOPR_2 = IOPR_2(0)
    iopr_3: IOPR_3 = IOPR_3(0)
    iopr_4: IOPR_4 = IOPR_4(1)
    iopr_5: IOPR_5 = IOPR_5(0)
    iopr_6: IOPR_6 = IOPR_6(-1)
    iopr_7: IOPR_7 = IOPR_7(1)
    iopr_8: IOPR_8 = IOPR_8(0)
    iopr_9: IOPR_9 = IOPR_9(0)
    iopr_10: IOPR_10 = IOPR_10(0)
    iopr_17: IOPR_17 = IOPR_17(1)
    iodb_1: IODB_1 = IODB_1(0)
    iodb_2: IODB_2 = IODB_2(0)
    iodb_3: IODB_3 = IODB_3(0)
    iodb_4: IODB_4 = IODB_4(0)
    iodb_5: IODB_5 = IODB_5(0)
    iodb_6: IODB_6 = IODB_6(0)
    iodb_7: IODB_7 = IODB_7(0)
    iodb_8: IODB_8 = IODB_8(0)

    @property
    def iopt(self) -> list[int]:
        return [
            self.iopt_1, self.iopt_2, self.iopt_3, self.iopt_4, self.iopt_5, self.iopt_6, self.iopt_7, self.iopt_9, 0,
            self.iopt_10, self.iopt_11, self.iopt_12, self.iopt_13, self.iopt_14, self.iopt_15, self.iopt_16,
            self.iopt_17, self.iopt_18, self.iopt_19, self.iopt_20
        ]

    @property
    def iopg(self) -> list[int]:
        return [self.iopg_1, self.iopg_2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    @property
    def iopr(self) -> list[int]:
        return [
            self.iopr_1, self.iopr_2, self.iopr_3, self.iopr_4, self.iopr_5, self.iopr_6, self.iopr_7, self.iopr_8,
            self.iopr_9, self.iopr_10, 0, 0, 0, 0, 0, 0, self.iopr_17, 0, 0, 0
        ]

    @property
    def iodb(self) -> list[int]:
        return [
            self.iodb_1, self.iodb_2, self.iodb_3, self.iodb_4, self.iodb_5, self.iodb_6, self.iodb_7, self.iodb_8, 0,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        ]


@yeoman_registry.mapped_as_dataclass(kw_only=True)
class Config(KernelConfig):
    __table__ = Table(
        'eq36_config',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('kernel.id'), primary_key=True),
        Column('model', String, nullable=False),
        Column('charge_balance', String, nullable=False),
        Column('redox_species', String, nullable=False),
        Column('basis_map', JSONDict, nullable=False),
        Column('data1_file', String, nullable=False),
    )

    __mapper_args__ = {
        'polymorphic_identity': 'eq36',
        'properties': {
            'eq3_config': relationship('Eq3Config', uselist=False),
            'eq6_config': relationship('Eq6Config', uselist=False),
        },
    }

    model: str
    charge_balance: str
    eq3_config: Eq3Config
    eq6_config: Eq6Config
    data1_file: Optional[str] = None
    basis_map: dict[str, str] = field(default_factory=dict)
    redox_species: str = 'fO2'

    @staticmethod
    def from_dict(raw: dict):
        model = raw['model']
        if not isinstance(model, str):
            raise EleanorException('kernel.model must be a string')

        model = EQ36_MODEL_EXTENSIONS.get(model, model)
        if model not in ['pitzer', 'davies', 'b-dot']:
            raise EleanorException(
                'kernel.model must be "pitzer", "davies", "b-dot" or a standard EQ3/6 file extension')

        charge_balance = raw['charge_balance']
        if not isinstance(charge_balance, str):
            raise EleanorException('kernel.charge_balance must be a string')

        basis_map = raw.get('basis_map', {})
        if not isinstance(basis_map, dict):
            raise EleanorException('kernel.basis_map must be a dict')

        redox_species = raw.get('redox_species', 'fO2')
        if not isinstance(redox_species, str):
            raise EleanorException('kernel.redox_species must be a str')

        timeout = raw.get('timeout', 0)
        if not isinstance(timeout, int):
            raise EleanorException('kernel.timeout must be an integer')
        elif timeout == 0:
            timeout = None

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

        if eq3_config.iopt_19 != IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX:
            msg = f'kernel.eq3_config.iopt_19 value ({eq3_config.iopt_19}) is unsupported'
            raise EleanorException(msg)

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
            raise EleanorException(msg)

        return Config(
            id=None,
            type='eq36',
            model=model,
            timeout=timeout,
            charge_balance=charge_balance,
            eq3_config=eq3_config,
            eq6_config=eq6_config,
            basis_map=basis_map,
            redox_species=redox_species,
        )
