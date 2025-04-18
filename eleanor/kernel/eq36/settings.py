from enum import IntEnum

from sqlalchemy import INTEGER, TypeDecorator


class Eq36SettingField(TypeDecorator):
    impl = INTEGER
    cache_ok = True

    def __init__(self, base):
        super().__init__()
        self.base = base

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self.base(value)


class JTEMP(IntEnum):
    """
    Temperature option (jtemp). This feature in eq3/6 can take on one of 4 settings,
    which correspond to 4 different treatments of temperature.
    For Eleanor version  1, we only use jtemp = 0 (constant Temperature)
    We plan to add jtemp = 3 (fluid mixing, for Eleanor version 1.1)
    """
    CONSTANT_T = 0


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
    IGNORE_SS = 0
    PERMIT_SS = 1


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
     - Print All Reactions:
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
    DONT_PRINT_PHASE_BOUNDRY_INFO = 0
    SUMMARY_PHASE_BOUNDRY_INFO = 1  # Print summary information


class IODB_8(IntEnum):
    """
    Print ODE Corrector Iteration Information:
    """
    DONT_PRINT_ODE_CORRECTOR = 0
    SUMMARY_ODE_CORRECTOR = 1  # Print summary information
    DETAILED_ODE_CORRECTOR = 2  # Print detailed information (including the betar and delvcr vectors)|
