import io
import re

import numpy as np

from eleanor.exceptions import EleanorException, EleanorFileException, EleanorParserException
from eleanor.typing import Float, Optional

from .codes import RunCode


def get_field(line: str, pos: int) -> str:
    """
    Split the string `line` on spaces and return the `pos`-th
    """
    return line.split()[pos]


def field_as_float(field: str) -> float:
    """
    Parse a string from an EQ3/6 output file as a `float`
    """
    if re.findall(r'[0-9][-\+][0-9]', field):
        return 0.000

    match = re.findall(r'[0-9Ee\+\.-]+', field)
    if match:
        return float(match[0])

    raise EleanorParserException(f'failed to read "{field}" as float')


def read_pickup_lines(file: Optional[str | io.TextIOWrapper] = None) -> list[str]:
    if file is None:
        return read_pickup_lines('problem.3p')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return read_pickup_lines(handle)

    try:
        lines = file.readlines()
        for i, line in reversed(list(enumerate(lines))):
            if line.startswith('*---'):
                return lines[i + 1:]
        raise EleanorFileException('failed to find seperator in pickup file', code=RunCode.FILE_ERROR_3P)
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.FILE_ERROR_3P)


def read_eq3_output(file: Optional[str | io.TextIOWrapper] = None) -> dict[str, Float]:
    if file is None:
        return read_eq3_output('problem.3o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return read_eq3_output(handle)

    try:
        lines = file.readlines()
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_3O_FILE)

    data: dict[str, Float] = {}
    data['extended_alk'] = np.nan

    if 'Normal exit' not in lines[-1]:
        raise EleanorException('eq3 terminated early', code=RunCode.EQ3_EARLY_TERMINATION)

    for i in range(len(lines)):
        line = lines[i]
        if line == '\n':
            continue
            i += 1

        fields = line.split()

        if ' Temperature=' in line:
            data['T_cel'] = field_as_float(fields[-2])
        elif ' Pressure=' in lines[i]:
            data['P_bar'] = field_as_float(fields[1])
        elif ' --- Elemental Composition' in line:
            j = i + 4
            while lines[j] != '\n':
                local_fields = lines[j].split()
                name = local_fields[0]
                value = np.round(np.log10(field_as_float(local_fields[-1])), 6)
                data[f'm_{name}'] = value
                j += 1
        elif ' NBS pH scale         ' in line:
            data['pH'] = field_as_float(fields[-4])
        elif '                Log oxygen fugacity=' in line:
            data['fO2'] = field_as_float(fields[-1])
        elif '              Log activity of water=' in line:
            data['a_H2O'] = field_as_float(fields[-1])
        elif '                 Ionic strength (I)=' in line:
            data['ionic'] = field_as_float(fields[-2])
        elif '                 Solutes (TDS) mass=' in line:
            data['tds'] = field_as_float(fields[-2])
        elif '              Aqueous solution mass=' in line:
            data['soln_mass'] = field_as_float(fields[-2])
        elif '           --- Extended Total Alkalinity ---' in line:
            field = get_field(lines[i + 2], 0)
            data['extended_alk'] = field_as_float(field)
        elif '         Charge imbalance=' in line:
            data['charge_imbalance_eq'] = field_as_float(fields[-1])
        elif '--- Distribution of Aqueous Solute Species ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_fields = lines[j].split()
                name = local_fields[0]
                if name != 'O2(g)':
                    # '******' shows up with species are less than -99999.0 which signifies that it was suppressed.

                    # -3 is log molality
                    molality = local_fields[-3]
                    data[f'm_{name}'] = -99999.0 if '*' in molality else field_as_float(molality)

                    # -1 position is log activity,
                    activity = local_fields[-1]
                    data[f'a_{name}'] = -99999.0 if '*' in activity else field_as_float(activity)

                j += 1
        elif '--- Saturation States of Pure Solids ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]

                # '******'' fills in the value region for numbers lower than -999.9999. Replace with boundary
                if re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = -999.9999
                elif 'None' not in local_line:
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = field_as_float(local_line[31:44])

                j += 1
        elif ' --- Saturation States of Solid Solutions ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]

                # '******' fills in the value region for numbers lower than -999.9999. Replace with boundary
                if re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = -999.9999
                elif 'None' not in local_line:
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = field_as_float(local_line[44:55])

                j += 1
        elif '    --- Fugacities ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]

                if 'None' not in local_line:
                    # '******'' fills in the value region for numbers lower than -999.9999. Replace with
                    if re.findall(r'\*{4}', local_line):
                        # boundary condition
                        name = local_line[:30].strip()
                        data[f'f_{name}'] = -999.9999
                    else:
                        name = local_line[:30].strip()
                        data[f'f_{name}'] = field_as_float(local_line[28:41])

                j += 1

            break

    return data


def read_eq6_output(file: Optional[str | io.TextIOWrapper] = None) -> dict[str, Float]:
    if file is None:
        return read_eq6_output('problem.6o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return read_eq6_output(handle)

    try:
        lines = file.readlines()
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_3O_FILE)

    data: dict[str, Float] = {}
    data['extended_alk'] = np.nan

    reaction_path_terminated = False
    for i in range(len(lines) - 1, 0, -1):
        # Search from bottom of file
        if '---  The reaction path has terminated early ---' in lines[i]:
            raise EleanorException('eq6 reaction path terminated early', code=RunCode.EQ6_EARLY_TERMINATION)
        elif '---  The reaction path has terminated normally ---' in lines[i]:
            reaction_path_terminated = True

    if not reaction_path_terminated:
        raise EleanorException('no reaction path termination status found', code=RunCode.FILE_ERROR_6O)

    data["initial_aff"] = 0.0
    for line in lines:
        fields = line.split()
        if '   Affinity of the overall irreversible reaction=' in line:
            data["initial_aff"] = field_as_float(fields[-2])
            break

    line_num = len(lines) - 1
    while line_num >= 0:
        line = lines[line_num]
        if '                Log Xi=' in line:
            fields = line.split()
            data['xi_max'] = field_as_float(fields[-1])
            break
        line_num -= 1

    while line_num < len(lines):
        line = lines[line_num]
        if line == '\n':
            line_num += 1
            continue

        fields = line.split()

        if ' Temperature=' in line:
            data['T_cel'] = field_as_float(fields[-2])
        elif ' Pressure=' in line:
            data['P_bar'] = field_as_float(fields[-2])
        elif ' --- Elemental Composition' in lines[i]:
            i = line_num + 4
            while lines[i] != '\n':
                local_fields = lines[i].split()
                name = local_fields[0]
                data[f'm_{name}'] = np.round(np.log10(field_as_float(local_fields[-1])), 6)
                i += 1
        elif ' NBS pH scale         ' in line:
            data['pH'] = field_as_float(fields[-4])
        elif '                Log oxygen fugacity=' in line:
            data['fO2'] = field_as_float(fields[-1])
        elif '              Log activity of water=' in line:
            data['a_H2O'] = field_as_float(fields[-1])
        elif '                 Ionic strength (I)=' in line:
            data['ionic'] = field_as_float(fields[-2])
        elif '                 Solutes (TDS) mass=' in line:
            data['tds'] = field_as_float(fields[-2])
        elif '              Aqueous solution mass=' in line:
            data['soln_mass'] = field_as_float(fields[-2])
        elif '           --- Extended Total Alkalinity ---' in line:
            local_fields = lines[line_num + 2].split()
            data['extended_alk'] = field_as_float(local_fields[0])
        elif '        --- Aqueous Solution Charge Balance ---' in line:
            local_fields = lines[line_num + 2].split()
            data['charge_imbalance_eq'] = field_as_float(local_fields[-2])
        elif '--- Distribution of Aqueous Solute Species ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_fields = lines[i].split()
                name = local_fields[0]
                if name != 'O2(g)':
                    # '******' shows up with species are less than -99999.0 which signifies that it was suppressed.

                    # -3 is log molality
                    molality = local_fields[-3]
                    data[f'm_{name}'] = -99999.0 if '*' in molality else field_as_float(molality)
                    if data[f'm_{name}'] == -99999:
                        data[f'm_{name}'] = 0

                    # -1 position is log activity,
                    activity = local_fields[-1]
                    data[f'a_{name}'] = -99999.0 if '*' in activity else field_as_float(activity)
                    if data[f'a_{name}'] == -99999:
                        data[f'a_{name}'] = 0

                i += 1
        elif '--- Summary of Solid Phases (ES) ---' in line:
            i = line_num + 4
            solid_solution = None
            end_member = None
            if 'None' not in lines[i]:
                import sys
                while True:
                    line = lines[i]

                    if line == '\n' and lines[i + 1] == '\n':
                        # Two blank lines signifies end of block
                        break
                    elif line == '\n':
                        # Single blank lines separate solids from solid slutions reporting
                        solid_solution = None
                        end_member = None
                    elif re.findall(r'^ [^ ]', line):
                        # Pure phases and solid solutions parents
                        solid_solution = line[:25].strip()
                        local_fields = line.split()
                        data[f'm_{solid_solution}'] = field_as_float(local_fields[-3])
                    elif re.findall(r'^   [^ ]', line):
                        # Solid solution endmember. Grab with parent association
                        if solid_solution is None:
                            msg = f'found solid solution end member without solid solution at {file.name}:{line_num}'
                            raise EleanorParserException()
                        end_member = line[:25].strip()
                        local_fields = line.split()
                        data[f'm_{end_member}_{solid_solution}'] = field_as_float(local_fields[-3])
                        end_member = None

                    i += 1
        elif '--- Saturation States of Pure Solids ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]

                # '******'' fills in the value region for numbers lower than -999.9999. Replace with boundary
                if re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = -999.9999
                elif 'None' not in local_line:
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = field_as_float(local_line[31:44])

                i += 1
        elif ' --- Saturation States of Solid Solutions ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]

                # '******' fills in the value region for numbers lower than -999.9999. Replace with boundary
                if re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = -999.9999
                elif 'None' not in local_line:
                    name = local_line[:30].strip()
                    data[f'qk_{name}'] = field_as_float(local_line[44:55])

                i += 1

        elif '    --- Fugacities ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]

                if 'None' not in local_line:
                    # '******'' fills in the value region for numbers lower than -999.9999. Replace with
                    if re.findall(r'\*{4}', local_line):
                        # boundary condition
                        name = local_line[:30].strip()
                        data[f'f_{name}'] = -999.9999
                    else:
                        name = local_line[:30].strip()
                        data[f'f_{name}'] = field_as_float(local_line[28:41])

                i += 1

            break

        line_num += 1

    return data
