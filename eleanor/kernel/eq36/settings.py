from copy import copy
from dataclasses import dataclass, field
from enum import IntEnum

from eleanor.exceptions import EleanorException
from eleanor.kernel.config import Settings as KernelSettings
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.typing import Number, Optional, Self


def get_setting(cfg: dict[str, int], setting, default=None):
    key: str = setting.__name__.lower()
    value: Optional[Number | str] = cfg.get(key, default)
    if value is None:
        raise EleanorKernelException(f'config option {key} is required')

    try:
        if isinstance(value, str):
            return setting[value]
        else:
            return setting(value)
    except Exception as e:
        raise EleanorKernelException(f'unexpected value for option {key}') from e


class JTEMP(IntEnum):
    """
    Temperature option (jtemp). This feature in eq3/6 can take on one of 4 settings,
    which correspond to 4 different treatments of temperature.
    For Eleanor version  1, we only use jtemp = 0 (constant Temperature)
    We plan to add jtemp = 3 (fluid mixing, for Eleanor version 1.1)
    """
    CONSTANT_T = 0
    LINEAR_WITH_XI = 1
    LINEAR_WITH_TIME = 2
    FLUID_MIXING = 3


class IOPT_1(IntEnum):
    """
    Physical System Model Selection:
    """
    CLOSED_SYS = 0  # Closed system
    TITRATION_SYS = 1  # Titration system
    FLOW_THROUGH_SYS = 2  # Fluid-centered flow-through open system


class IOPT_2(IntEnum):
    """
    Kinetic Mode Selection:
    """
    ARBITRARY_KINETICS = 0  # Reaction progress mode (arbitrary kinetics)
    TRUE_KINETICS = 1  # Reaction progress/time mode (true kinetics)


class IOPT_3(IntEnum):
    """
    Phase Boundary Searches:
    """
    STEP_SIZE_BY_PHASE_BOUNDARIES = 0  # Search for phase boundaries and constrain the step size to match
    SEARCH_PHASE_BOUNDARIES = 1  # Search for phase boundaries and print their locations
    DONT_SEARCH_PHASE_BOUNDARIES = 2  # Don't search for phase boundaries


class IOPT_4(IntEnum):
    """
    Solid Solutions
    """
    IGNORE_SOLID_SOLUTIONS = 0
    PERMIT_SOLID_SOLUTIONS = 1


class IOPT_5(IntEnum):
    """
    Clear the ES Solids Read from the INPUT File:
    """
    DONT_CLEAR_SOLIDS = 0
    CLEAR_SOLIDS = 1


class IOPT_6(IntEnum):
    """
    Clear the ES Solids at the Initial Value of Reaction Progress:
    """
    DONT_CLEAR_SOLIDS_AT_INITIAL = 0
    CLEAR_SOLIDS_AT_INITIAL = 1


class IOPT_7(IntEnum):
    """
    Clear the ES Solids at the End of the Run:
    """
    DONT_CLEAR_SOLIDS_AT_END = 0
    CLEAR_SOLIDS_AT_END = 1


class IOPT_9(IntEnum):
    """
    Clear the PRS Solids Read from the INPUT file:
    """
    DONT_CLEAR_PRS_SOLIDS_FROM_INPUT = 0
    CLEAR_PRS_SOLIDS_FROM_INPUT = 1


class IOPT_10(IntEnum):
    """
    Clear the PRS Solids at the End of the Run:
    """
    DONT_CLEAR_PRS_SOLIDS_AT_END = 0
    CLEAR_PRS_SOLIDS_AT_END = 1  # Do it, unless numerical problems cause early termination


class IOPT_11(IntEnum):
    """
    Auto Basis Switching in pre-N-R Optimization
    """
    DONT_PRE_NR_AUTO_BASIS_SWITCH = 0
    PRE_NR_BASIS_SWITCH = 1


class IOPT_12(IntEnum):
    """
    Auto Basis Switching after Newton-Raphson Iteration
    """
    DONT_POST_NR_AUTO_BASIS_SWITCH = 0
    POST_NR_BASIS_SWITCH = 1


class IOPT_13(IntEnum):
    """
    Calculational Mode Selection
    """
    PATH_TRACE = 0  # Normal path tracing
    ECONOMY = 1  # Economy mode (if permissible)
    SUPER_ECONOMY = 2  # Super economy mode (if permissible)


class IOPT_14(IntEnum):
    """
    ODE Integrator Corrector Mode Selection
    """
    STIFF_SIMPLE_CORRECTORS = 0  # Allow Stiff and Simple Correctors
    SIMPLE_CORRECTORS = 1  # Allow Only the Simple Corrector
    STIFF_CORRECTORS = 2  # Allow Only the Stiff Corrector
    NO_CORRECTORS = 3  # Allow No Correctors


class IOPT_15(IntEnum):
    """
    Force the Suppression of All Redox Reactions (NOT IN USE)
    """
    DONT_SUPPRESS_REDOX = 0
    SUPPRESS_REDOX = 1


class IOPT_16(IntEnum):
    """
    BACKUP File Options
    """
    NO_BACKUP_FILE = -1
    WRITE_BACKUP_FILE = 0
    WRITE_SEQUENTIAL_BACKUP_FILE = 1


class IOPT_17(IntEnum):
    """
    PICKUP File Options
    """
    DONT_WRITE_PICKUP = -1
    WRITE_PICKUP = 0


class IOPT_18(IntEnum):
    """
    TAB File Options
    """
    DONT_WRITE_TAB = -1
    WRITE_TAB = 0
    PREPEND_TAB = 1  # Write a TAB file, prepending TABX file data from a previous run


class IOPT_19(IntEnum):
    """
    Advanced EQ3NR PICKUP File Options
    """
    NORMAL_PICKUP = 0
    QZ_DISSOLVE_PICKUP = 1  # Write an EQ6 INPUT file with Quartz dissolving, relative rate law
    ALBITE_DISSOLVE_PICKUP = 2  # Write an EQ6 INPUT file with Albite dissolving, TST rate law
    SIXI_FLUID_1_AS_FLUID_MIX = 3  # default for eleanor


class IOPT_20(IntEnum):
    """
    Advanced EQ6 PICKUP File Options:
    """
    NORMAL_PICKUP = 0
    FLUID_MIXING_PICKUP = 1  # Write an EQ6 INPUT file with Fluid 1 set up for fluid mixing


class IOPG_1(IntEnum):
    """
    Aqueous Species Activity Coefficient Model
    """
    DAVIES = -1
    B_DOT = 0
    PITZER = 1
    HC_DH = 2


class IOPG_2(IntEnum):
    """
    Choice of pH Scale (Rescales Activity Coefficients)
    """
    INTERNAL_PH = -1  # no rescaling
    NBS_PH = 0  # uses the Bates-Guggenheim equation
    MESMER_PH = 1  # numerically, pH = -log m(H+)


class IOPR_1(IntEnum):
    """
    Print All Species Read from the Data File
    """
    DONT_PRINT_DATA_FILE_SP = 0
    PRINT_DATA_FILE_SP = 1


class IOPR_2(IntEnum):
    """
    Print All Reactions:
    """
    DONT_PRINT_RXNS = 0  # Don't print
    PRINT_ALL_RXNS = 1  # Print the reactions
    PRINT_RXNS_LOGK = 2  # Print the reactions and log K values
    PRINT_RXNS_LOGK_DATA = 3  # Print the reactions, log K values, and associated data


class IOPR_3(IntEnum):
    """
    Print the Aqueous Species Hard Core Diameters
    """
    DONT_PRINT_HARD_DIAMETERS = 0
    PRINT_HARD_DIAMETERS = 1


class IOPR_4(IntEnum):
    """
    Print a Table of Aqueous Species Concentrations, Activities, etc.
    """
    CUT_NEG8 = -3  # Omit species with molalities < 1.e-8
    CUT_NEG12 = -2  # Omit species with molalities < 1.e-12
    CUT_NEG20 = -1  # Omit species with molalities < 1.e-20
    CUT_NEG100 = 0  # Omit species with molalities < 1.e-100
    INCLUDE_ALL_AQ = 1


class IOPR_5(IntEnum):
    """
    Print a Table of Aqueous Species/H+ Activity Ratios
    """
    DONT_PRINT_AQ_OVER_H = 0
    PRINT_CAT_RATIOS = 1  # Print cation/H+ activity ratios only
    PRINT_CAT_AN_RATIOS = 2  # Print cation/H+ and anion/H+ activity ratios
    PRINT_CAT_AN_NU_RATIOS = 3  # Print ion/H+ activity ratios and neutral species activities


class IOPR_6(IntEnum):
    """
    Print a Table of Aqueous Mass Balance Percentages
    """
    DONT_PRINT_AQ_MASS_BAL = -1
    NINTY_NINE_AQ_MASS_BAL = 0  # Print species comprising 99% of mass balance
    PRINT_ALL_SP_MASS_BAL = 1


class IOPR_7(IntEnum):
    """
    Print Tables of Saturation Indices and Affinities
    """
    DONT_PRINT_AFFINITIES = -1
    RID_UNDER_10KCAL_AFFINITIES = 0  # omit phases undersaturated by more than 10 kcal
    PRINT_ALL_AFFINITIES = 1


class IOPR_8(IntEnum):
    """
    Print a Table of Fugacities:
    """
    DONT_PRINT_FUGACITIES = -1
    PRINT_FUGACITIES = 0


class IOPR_9(IntEnum):
    """
    Print a Table of Mean Molal Activity Coefficients
    """
    DONT_PRINT_MEAN_ACTIVITY_COE = 0
    PRINT_MEAN_ACTIVITY_COE = 1


class IOPR_10(IntEnum):
    """
    Print a Tabulation of the Pitzer Interaction Coefficients
    """
    DONT_PRINT_PITZER_INTERACT_COE = 0
    SUMMARY_PITZER_INTERACT_COE = 1
    DETAILED_PITZER_INTERACT_COE = 2


class IOPR_17(IntEnum):
    """
    PICKUP file format ("W" or "D")
    """
    PICKUP_IS_INPUT_FORMAT = 0
    W_FORMAT = 1
    D_FORMAT = 2


class IODB_1(IntEnum):
    """
    Print General Diagnostic Messages:
    """
    DONT_PRINT_DIAG = 0
    PRINT_LEVEL_1_DIAG = 1  # Print Level 1 diagnostic messages
    PRINT_LEVEL_1_2_DIAG = 2  # Print Level 1 and Level 2 diagnostic messages


class IODB_2(IntEnum):
    """
    Kinetics Related Diagnostic Messages:
    """
    DONT_PRINT_KINETIC_DIAG = 0
    PRINT_LEVEL_1_KINETIC_DIAG = 1  # Print Level 1 kinetics diagnostic messages
    PRINT_LEVEL_1_2_KINETIC_DIAG = 2  # Print Level 1 and Level 2 kinetics diagnostic messages


class IODB_3(IntEnum):
    """
    Print Pre-Newton-Raphson Optimization Information:
    """
    DONT_PRINT_PRE_NR_DIAG = 0
    SUMMARY_PRE_NR_DIAG = 1  # Print summary information
    DETAILED_PRE_NR_DIAG = 2  # Print detailed information (including the beta and del vectors)
    MORE_DETAILED_PRE_NR_DIAG = 3  # Print more detailed information (including matrix equations)
    MOST_DETAILED_PRE_NR_DIAG = 4  # Print most detailed information (including activity coefficients)


class IODB_4(IntEnum):
    """
    Print Newton-Raphson Iteration Information:
    """
    DONT_PRINT_NR_INFO = 0
    SUMMARY_NR_INFO = 1  # Print summary information
    DETAILED_NR_INFO = 2  # Print detailed information (including the beta and del vectors)
    MORE_DETAILED_NR_INFO = 3  # Print more detailed information (including the Jacobian)
    MOST_DETAILED_NR_INFO = 4  # Print most detailed information (including activity coefficients)


class IODB_5(IntEnum):
    """
    Print Step-Size and Order Selection:
    """
    DONT_PRINT_STEP_SELECT_INFO = 0  # Don't print
    SUMMARY_STEP_SELECT_INFO = 1  # Print summary information
    DETAILED_STEP_SELECT_INFO = 2  # Print detailed information


class IODB_6(IntEnum):
    """
    Print Details of Hypothetical Affinity Calculations:
    """
    DONT_PRINT_AFFINITY_CALC = 0  # Don't print
    SUMMARY_AFFINITY_CALC = 1  # Print summary information
    DETAILED_AFFINITY_CALC = 2  # Print detailed information


class IODB_7(IntEnum):
    """
    Print General Search (e.g., for a phase boundary) Information:
    """
    DONT_PRINT_PHASE_BOUNDARY_INFO = 0
    SUMMARY_PHASE_BOUNDRY_INFO = 1  # Print summary information


class IODB_8(IntEnum):
    """
    Print ODE Corrector Iteration Information:
    """
    DONT_PRINT_ODE_CORRECTOR = 0
    SUMMARY_ODE_CORRECTOR = 1  # Print summary information
    DETAILED_ODE_CORRECTOR = 2  # Print detailed information (including the betar and delvcr vectors)|


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


@dataclass
class Eq3Config(object):
    id: Optional[int] = None
    iopt_1: IOPT_1 = IOPT_1.CLOSED_SYS
    iopt_2: IOPT_2 = IOPT_2.ARBITRARY_KINETICS
    iopt_3: IOPT_3 = IOPT_3.STEP_SIZE_BY_PHASE_BOUNDARIES
    iopt_4: IOPT_4 = IOPT_4.IGNORE_SOLID_SOLUTIONS
    iopt_5: IOPT_5 = IOPT_5.DONT_CLEAR_SOLIDS
    iopt_6: IOPT_6 = IOPT_6.DONT_CLEAR_SOLIDS_AT_INITIAL
    iopt_7: IOPT_7 = IOPT_7.DONT_CLEAR_SOLIDS_AT_END
    iopt_9: IOPT_9 = IOPT_9.DONT_CLEAR_PRS_SOLIDS_FROM_INPUT
    iopt_10: IOPT_10 = IOPT_10.DONT_CLEAR_PRS_SOLIDS_AT_END
    iopt_11: IOPT_11 = IOPT_11.DONT_PRE_NR_AUTO_BASIS_SWITCH
    iopt_12: IOPT_12 = IOPT_12.DONT_POST_NR_AUTO_BASIS_SWITCH
    iopt_13: IOPT_13 = IOPT_13.PATH_TRACE
    iopt_14: IOPT_14 = IOPT_14.STIFF_SIMPLE_CORRECTORS
    iopt_15: IOPT_15 = IOPT_15.DONT_SUPPRESS_REDOX
    iopt_16: IOPT_16 = IOPT_16.NO_BACKUP_FILE
    iopt_17: IOPT_17 = IOPT_17.WRITE_PICKUP
    iopt_18: IOPT_18 = IOPT_18.DONT_WRITE_TAB
    iopt_19: IOPT_19 = IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX
    iopt_20: IOPT_20 = IOPT_20.NORMAL_PICKUP
    iopg_1: IOPG_1 = IOPG_1.B_DOT
    iopg_2: IOPG_2 = IOPG_2.NBS_PH
    iopr_1: IOPR_1 = IOPR_1.DONT_PRINT_DATA_FILE_SP
    iopr_2: IOPR_2 = IOPR_2.DONT_PRINT_RXNS
    iopr_3: IOPR_3 = IOPR_3.DONT_PRINT_HARD_DIAMETERS
    iopr_4: IOPR_4 = IOPR_4.INCLUDE_ALL_AQ
    iopr_5: IOPR_5 = IOPR_5.DONT_PRINT_AQ_OVER_H
    iopr_6: IOPR_6 = IOPR_6.DONT_PRINT_AQ_MASS_BAL
    iopr_7: IOPR_7 = IOPR_7.PRINT_ALL_AFFINITIES
    iopr_8: IOPR_8 = IOPR_8.DONT_PRINT_FUGACITIES
    iopr_9: IOPR_9 = IOPR_9.DONT_PRINT_MEAN_ACTIVITY_COE
    iopr_10: IOPR_10 = IOPR_10.DONT_PRINT_PITZER_INTERACT_COE
    iopr_17: IOPR_17 = IOPR_17.PICKUP_IS_INPUT_FORMAT
    iodb_1: IODB_1 = IODB_1.DONT_PRINT_DIAG
    iodb_2: IODB_2 = IODB_2.DONT_PRINT_KINETIC_DIAG
    iodb_3: IODB_3 = IODB_3.DONT_PRINT_PRE_NR_DIAG
    iodb_4: IODB_4 = IODB_4.DONT_PRINT_NR_INFO
    iodb_5: IODB_5 = IODB_5.DONT_PRINT_STEP_SELECT_INFO
    iodb_6: IODB_6 = IODB_6.DONT_PRINT_AFFINITY_CALC
    iodb_7: IODB_7 = IODB_7.DONT_PRINT_PHASE_BOUNDARY_INFO
    iodb_8: IODB_8 = IODB_8.DONT_PRINT_ODE_CORRECTOR

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


@dataclass
class Eq6Config(object):
    id: Optional[int] = None
    jtemp: JTEMP = JTEMP.CONSTANT_T
    ttk1: float = 0
    ttk2: float = 0
    xi_min: float = 0
    xi_max: float = 100
    time_min: float = 0
    time_max: float = 1e38
    ph_min: float = -1e38
    ph_max: float = 1e38
    eh_min: float = -1e38
    eh_max: float = 1e38
    log_fO2_min: float = -1e38
    log_fO2_max: float = 1e38
    aw_min: float = -1e38
    aw_max: float = 1e38
    xi_print_interval: float = 1e0
    log_xi_print_interval: float = 1e0
    time_print_interval: float = 1e38
    log_time_print_interval: float = 1e38
    ph_print_interval: float = 1e38
    eh_print_interval: float = 1e38
    log_fO2_print_interval: float = 1e38
    aw_print_interval: float = 1e38
    steps_print_interval: int = 10000
    iopt_1: IOPT_1 = IOPT_1.CLOSED_SYS
    iopt_2: IOPT_2 = IOPT_2.ARBITRARY_KINETICS
    iopt_3: IOPT_3 = IOPT_3.STEP_SIZE_BY_PHASE_BOUNDARIES
    iopt_4: IOPT_4 = IOPT_4.IGNORE_SOLID_SOLUTIONS
    iopt_5: IOPT_5 = IOPT_5.DONT_CLEAR_SOLIDS
    iopt_6: IOPT_6 = IOPT_6.DONT_CLEAR_SOLIDS_AT_INITIAL
    iopt_7: IOPT_7 = IOPT_7.DONT_CLEAR_SOLIDS_AT_END
    iopt_9: IOPT_9 = IOPT_9.DONT_CLEAR_PRS_SOLIDS_FROM_INPUT
    iopt_10: IOPT_10 = IOPT_10.DONT_CLEAR_PRS_SOLIDS_AT_END
    iopt_11: IOPT_11 = IOPT_11.DONT_PRE_NR_AUTO_BASIS_SWITCH
    iopt_12: IOPT_12 = IOPT_12.DONT_POST_NR_AUTO_BASIS_SWITCH
    iopt_13: IOPT_13 = IOPT_13.PATH_TRACE
    iopt_14: IOPT_14 = IOPT_14.STIFF_SIMPLE_CORRECTORS
    iopt_15: IOPT_15 = IOPT_15.DONT_SUPPRESS_REDOX
    iopt_16: IOPT_16 = IOPT_16.NO_BACKUP_FILE
    iopt_17: IOPT_17 = IOPT_17.WRITE_PICKUP
    iopt_18: IOPT_18 = IOPT_18.DONT_WRITE_TAB
    iopt_19: IOPT_19 = IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX
    iopt_20: IOPT_20 = IOPT_20.NORMAL_PICKUP
    iopg_1: IOPG_1 = IOPG_1.B_DOT
    iopg_2: IOPG_2 = IOPG_2.NBS_PH
    iopr_1: IOPR_1 = IOPR_1.DONT_PRINT_DATA_FILE_SP
    iopr_2: IOPR_2 = IOPR_2.DONT_PRINT_RXNS
    iopr_3: IOPR_3 = IOPR_3.DONT_PRINT_HARD_DIAMETERS
    iopr_4: IOPR_4 = IOPR_4.CUT_NEG100
    iopr_5: IOPR_5 = IOPR_5.DONT_PRINT_AQ_OVER_H
    iopr_6: IOPR_6 = IOPR_6.DONT_PRINT_AQ_MASS_BAL
    iopr_7: IOPR_7 = IOPR_7.PRINT_ALL_AFFINITIES
    iopr_8: IOPR_8 = IOPR_8.PRINT_FUGACITIES
    iopr_9: IOPR_9 = IOPR_9.PRINT_MEAN_ACTIVITY_COE
    iopr_10: IOPR_10 = IOPR_10.DONT_PRINT_PITZER_INTERACT_COE
    iopr_17: IOPR_17 = IOPR_17.PICKUP_IS_INPUT_FORMAT
    iodb_1: IODB_1 = IODB_1.DONT_PRINT_DIAG
    iodb_2: IODB_2 = IODB_2.DONT_PRINT_KINETIC_DIAG
    iodb_3: IODB_3 = IODB_3.DONT_PRINT_PRE_NR_DIAG
    iodb_4: IODB_4 = IODB_4.DONT_PRINT_NR_INFO
    iodb_5: IODB_5 = IODB_5.DONT_PRINT_STEP_SELECT_INFO
    iodb_6: IODB_6 = IODB_6.DONT_PRINT_AFFINITY_CALC
    iodb_7: IODB_7 = IODB_7.DONT_PRINT_PHASE_BOUNDARY_INFO
    iodb_8: IODB_8 = IODB_8.DONT_PRINT_ODE_CORRECTOR

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


@dataclass(kw_only=True)
class Settings(KernelSettings):
    model: str
    charge_balance: str
    eq3_config: Eq3Config
    eq6_config: Optional[Eq6Config] = None
    data1_file: Optional[str] = None
    track_path: bool = False
    basis_map: dict[str, str] = field(default_factory=dict)
    redox_species: str = 'fO2'

    @classmethod
    def from_dict(cls, raw: dict):
        model = raw['model']
        if isinstance(model, int):
            model = IOPG_1(model)
        elif isinstance(model, str):
            model = EQ36_MODEL_EXTENSIONS.get(model, model)
            if model not in ['pitzer', 'davies', 'b-dot']:
                raise EleanorException(
                    'kernel.model must be "pitzer", "davies", "b-dot" or a standard EQ3/6 file extension')

            match model:
                case "davies":
                    model = IOPG_1.DAVIES
                case "b-dot":
                    model = IOPG_1.B_DOT
                case "hc_dh":
                    model = IOPG_1.HC_DH
                case "pitzer":
                    model = IOPG_1.PITZER
                case _:
                    model = IOPG_1.B_DOT
        else:
            raise EleanorException('kernel.model must be a string or integer')

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
        if timeout is not None and not isinstance(timeout, int):
            raise EleanorException('kernel.timeout must be an integer or None')
        elif timeout == 0:
            timeout = None

        track_path = raw.get('track_path', False)
        if not isinstance(track_path, bool):
            raise EleanorException('kernel.track_path must be a boolean')

        raw_eq3_config: dict[str, int] = raw.get('eq3_config', dict())

        eq3_config = Eq3Config(
            iopt_2=get_setting(raw_eq3_config, IOPT_2, IOPT_2.ARBITRARY_KINETICS),
            iopt_4=get_setting(raw_eq3_config, IOPT_4, IOPT_4.IGNORE_SOLID_SOLUTIONS),
            iopt_11=get_setting(raw_eq3_config, IOPT_11, IOPT_11.DONT_PRE_NR_AUTO_BASIS_SWITCH),
            iopt_16=get_setting(raw_eq3_config, IOPT_16, IOPT_16.NO_BACKUP_FILE),
            iopt_17=get_setting(raw_eq3_config, IOPT_17, IOPT_17.WRITE_PICKUP),
            iopt_19=get_setting(raw_eq3_config, IOPT_19, IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX),
            iopg_1=model,
            iopg_2=get_setting(raw_eq3_config, IOPG_2, IOPG_2.NBS_PH),
            iopr_1=get_setting(raw_eq3_config, IOPR_1, IOPR_1.DONT_PRINT_DATA_FILE_SP),
            iopr_2=get_setting(raw_eq3_config, IOPR_2, IOPR_2.DONT_PRINT_RXNS),
            iopr_3=get_setting(raw_eq3_config, IOPR_3, IOPR_3.DONT_PRINT_HARD_DIAMETERS),
            iopr_4=get_setting(raw_eq3_config, IOPR_4, IOPR_4.INCLUDE_ALL_AQ),
            iopr_5=get_setting(raw_eq3_config, IOPR_5, IOPR_5.DONT_PRINT_AQ_OVER_H),
            iopr_6=get_setting(raw_eq3_config, IOPR_6, IOPR_6.DONT_PRINT_AQ_MASS_BAL),
            iopr_7=get_setting(raw_eq3_config, IOPR_7, IOPR_7.PRINT_ALL_AFFINITIES),
            iopr_8=get_setting(raw_eq3_config, IOPR_8, IOPR_8.DONT_PRINT_FUGACITIES),
            iopr_9=get_setting(raw_eq3_config, IOPR_9, IOPR_9.DONT_PRINT_MEAN_ACTIVITY_COE),
            iopr_10=get_setting(raw_eq3_config, IOPR_10, IOPR_10.DONT_PRINT_PITZER_INTERACT_COE),
            iopr_17=get_setting(raw_eq3_config, IOPR_17, IOPR_17.PICKUP_IS_INPUT_FORMAT),
            iodb_1=get_setting(raw_eq3_config, IODB_1, IODB_1.DONT_PRINT_DIAG),
            iodb_3=get_setting(raw_eq3_config, IODB_3, IODB_3.DONT_PRINT_PRE_NR_DIAG),
            iodb_4=get_setting(raw_eq3_config, IODB_4, IODB_4.DONT_PRINT_NR_INFO),
            iodb_6=get_setting(raw_eq3_config, IODB_6, IODB_6.DONT_PRINT_AFFINITY_CALC),
        )

        if eq3_config.iopt_19 != IOPT_19.SIXI_FLUID_1_AS_FLUID_MIX:
            msg = f'kernel.eq3_config.iopt_19 value ({eq3_config.iopt_19}) is unsupported'
            raise EleanorException(msg)

        if not raw.get('eq6_config', True):
            eq6_config = None
        else:
            raw_eq6_config: dict[str, int] = raw.get('eq6_config', dict())
            eq6_config = Eq6Config(
                jtemp=get_setting(raw_eq6_config, JTEMP, JTEMP.CONSTANT_T),
                ttk1=float(raw_eq6_config.get('ttk1', 0)),
                ttk2=float(raw_eq6_config.get('ttk2', 0)),
                xi_min=float(raw_eq6_config.get('xi_min', 0)),
                xi_max=float(raw_eq6_config.get('xi_max', 100)),
                time_min=float(raw_eq6_config.get('time_min', 0)),
                time_max=float(raw_eq6_config.get('time_max', 1e38)),
                ph_min=float(raw_eq6_config.get('pH_min', -1e38)),
                ph_max=float(raw_eq6_config.get('pH_max', 1e38)),
                eh_min=float(raw_eq6_config.get('Eh_min', -1e38)),
                eh_max=float(raw_eq6_config.get('Eh_max', 1e38)),
                log_fO2_min=float(raw_eq6_config.get('log_fO2_min', -1e38)),
                log_fO2_max=float(raw_eq6_config.get('log_fO2_max', 1e38)),
                aw_min=float(raw_eq6_config.get('aw_min', -1e38)),
                aw_max=float(raw_eq6_config.get('aw_max', 1e38)),
                xi_print_interval=float(raw_eq6_config.get('xi_print_interval', 1e0)),
                log_xi_print_interval=float(raw_eq6_config.get('log_xi_print_interval', 1e0)),
                time_print_interval=float(raw_eq6_config.get('time_print_interval', 1e38)),
                log_time_print_interval=float(raw_eq6_config.get('log_time_print_interval', 1e38)),
                ph_print_interval=float(raw_eq6_config.get('pH_print_interval', 1e38)),
                eh_print_interval=float(raw_eq6_config.get('Eh_print_interval', 1e38)),
                log_fO2_print_interval=float(raw_eq6_config.get('log_fO2_print_interval', 1e38)),
                aw_print_interval=float(raw_eq6_config.get('aw_print_interval', 1e38)),
                steps_print_interval=int(raw_eq6_config.get('steps_print_interval', 10000)),
                iopt_1=get_setting(raw_eq6_config, IOPT_1, IOPT_1.CLOSED_SYS),
                iopt_2=get_setting(raw_eq6_config, IOPT_2, IOPT_2.ARBITRARY_KINETICS),
                iopt_3=get_setting(raw_eq6_config, IOPT_3, IOPT_3.STEP_SIZE_BY_PHASE_BOUNDARIES),
                iopt_4=get_setting(raw_eq6_config, IOPT_4, IOPT_4.IGNORE_SOLID_SOLUTIONS),
                iopt_5=get_setting(raw_eq6_config, IOPT_5, IOPT_5.DONT_CLEAR_SOLIDS),
                iopt_6=get_setting(raw_eq6_config, IOPT_6, IOPT_6.DONT_CLEAR_SOLIDS_AT_INITIAL),
                iopt_7=get_setting(raw_eq6_config, IOPT_7, IOPT_7.DONT_CLEAR_SOLIDS_AT_END),
                iopt_9=get_setting(raw_eq6_config, IOPT_9, IOPT_9.DONT_CLEAR_PRS_SOLIDS_FROM_INPUT),
                iopt_10=get_setting(raw_eq6_config, IOPT_10, IOPT_10.DONT_CLEAR_PRS_SOLIDS_AT_END),
                iopt_11=get_setting(raw_eq6_config, IOPT_11, IOPT_11.DONT_PRE_NR_AUTO_BASIS_SWITCH),
                iopt_12=get_setting(raw_eq6_config, IOPT_12, IOPT_12.DONT_POST_NR_AUTO_BASIS_SWITCH),
                iopt_13=get_setting(raw_eq6_config, IOPT_13, IOPT_13.PATH_TRACE),
                iopt_14=get_setting(raw_eq6_config, IOPT_14, IOPT_14.STIFF_SIMPLE_CORRECTORS),
                iopt_15=get_setting(raw_eq6_config, IOPT_15, IOPT_15.DONT_SUPPRESS_REDOX),
                iopt_16=get_setting(raw_eq6_config, IOPT_16, IOPT_16.NO_BACKUP_FILE),
                iopt_17=get_setting(raw_eq6_config, IOPT_17, IOPT_17.WRITE_PICKUP),
                iopt_18=get_setting(raw_eq6_config, IOPT_18, IOPT_18.DONT_WRITE_TAB),
                iopt_20=get_setting(raw_eq6_config, IOPT_20, IOPT_20.NORMAL_PICKUP),
                iopr_1=get_setting(raw_eq6_config, IOPR_1, IOPR_1.DONT_PRINT_DATA_FILE_SP),
                iopr_2=get_setting(raw_eq6_config, IOPR_2, IOPR_2.DONT_PRINT_RXNS),
                iopr_3=get_setting(raw_eq6_config, IOPR_3, IOPR_3.DONT_PRINT_HARD_DIAMETERS),
                iopr_4=get_setting(raw_eq6_config, IOPR_4, IOPR_4.CUT_NEG100),
                iopr_5=get_setting(raw_eq6_config, IOPR_5, IOPR_5.DONT_PRINT_AQ_OVER_H),
                iopr_6=get_setting(raw_eq6_config, IOPR_6, IOPR_6.DONT_PRINT_AQ_MASS_BAL),
                iopr_7=get_setting(raw_eq6_config, IOPR_7, IOPR_7.PRINT_ALL_AFFINITIES),
                iopr_8=get_setting(raw_eq6_config, IOPR_8, IOPR_8.PRINT_FUGACITIES),
                iopr_9=get_setting(raw_eq6_config, IOPR_9, IOPR_9.DONT_PRINT_MEAN_ACTIVITY_COE),
                iopr_10=get_setting(raw_eq6_config, IOPR_10, IOPR_10.DONT_PRINT_PITZER_INTERACT_COE),
                iopr_17=get_setting(raw_eq6_config, IOPR_17, IOPR_17.PICKUP_IS_INPUT_FORMAT),
                iodb_1=get_setting(raw_eq6_config, IODB_1, IODB_1.DONT_PRINT_DIAG),
                iodb_2=get_setting(raw_eq6_config, IODB_2, IODB_2.DONT_PRINT_KINETIC_DIAG),
                iodb_3=get_setting(raw_eq6_config, IODB_3, IODB_3.DONT_PRINT_PRE_NR_DIAG),
                iodb_4=get_setting(raw_eq6_config, IODB_4, IODB_4.DONT_PRINT_NR_INFO),
                iodb_5=get_setting(raw_eq6_config, IODB_5, IODB_5.DONT_PRINT_STEP_SELECT_INFO),
                iodb_6=get_setting(raw_eq6_config, IODB_6, IODB_6.DONT_PRINT_AFFINITY_CALC),
                iodb_7=get_setting(raw_eq6_config, IODB_7, IODB_7.DONT_PRINT_PHASE_BOUNDARY_INFO),
                iodb_8=get_setting(raw_eq6_config, IODB_8, IODB_8.DONT_PRINT_ODE_CORRECTOR),
            )

        return cls(
            **{
                'model': model,
                'timeout': timeout,
                'charge_balance': charge_balance,
                'eq3_config': eq3_config,
                'eq6_config': eq6_config,
                'basis_map': basis_map,
                'redox_species': redox_species,
                'track_path': track_path,
            })
