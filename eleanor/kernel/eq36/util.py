import io
import re
from dataclasses import dataclass

import numpy as np

import eleanor.kernel.eq36.equilibrium_space as es
from eleanor.exceptions import EleanorException, EleanorFileException, EleanorParserException
from eleanor.typing import Any, Number, Optional

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


def read_eq3_output(file: Optional[str | io.TextIOWrapper] = None) -> es.Eq3Point:
    if file is None:
        return read_eq3_output('problem.3o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return read_eq3_output(handle)

    try:
        lines = file.readlines()
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_3O_FILE)

    if 'Normal exit' not in lines[-1]:
        raise EleanorException('eq3 terminated early', code=RunCode.EQ3_EARLY_TERMINATION)

    data: dict[str, Any] = {
        'elements': [],
        'aqueous_species': [],
        'solid_phases': [],
        'gases': [],
    }

    for i in range(len(lines)):
        line = lines[i]
        if line == '\n':
            continue
            i += 1

        fields = line.split()

        if ' Temperature=' in line:
            data['temperature'] = field_as_float(fields[1])
        elif ' Pressure=' in lines[i]:
            data['pressure'] = field_as_float(fields[1])
        elif ' --- Elemental Composition' in line:
            j = i + 4
            while lines[j] != '\n':
                local_fields = lines[j].strip().split()
                name = local_fields[0]
                log_molality = np.log10(field_as_float(local_fields[4]))
                data['elements'].append(es.Element(name=name, log_molality=log_molality))
                j += 1
        elif ' NBS pH scale         ' in line:
            data['pH'] = field_as_float(fields[-4])
        elif '                Log oxygen fugacity=' in line:
            data['log_fO2'] = field_as_float(fields[-1])
        elif '              Log activity of water=' in line:
            data['log_activity_water'] = field_as_float(fields[-1])
        elif '                 Ionic strength (I)=' in line:
            data['ionic_strength'] = field_as_float(fields[-2])
        elif '                 Solutes (TDS) mass=' in line:
            data['tds_mass'] = field_as_float(fields[-2])
        elif '              Aqueous solution mass=' in line:
            data['solution_mass'] = field_as_float(fields[-2])
        elif '           --- Extended Total Alkalinity ---' in line:
            field = get_field(lines[i + 2], 0)
            data['extended_alkalinity'] = field_as_float(field)
        elif '         Charge imbalance=' in line:
            data['charge_imbalance'] = field_as_float(fields[-1])
        elif '--- Distribution of Aqueous Solute Species ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_fields = lines[j].split()
                name = local_fields[0]
                if name != 'O2(g)':
                    if '*' in local_fields[2] or '*' in local_fields[4]:
                        continue

                    log_molality = field_as_float(local_fields[2])
                    log_activity = field_as_float(local_fields[4])
                    species = es.AqueousSpecies(name=name, log_molality=log_molality, log_activity=log_activity)
                    data['aqueous_species'].append(species)

                j += 1
        elif '--- Saturation States of Pure Solids ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]

                # '******' fills in the value region for numbers lower than -999.9999
                if 'None' not in local_line and not re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    log_qk = field_as_float(local_line[31:44])
                    solid = es.SolidPhase(type='solid', name=name, log_qk=log_qk)
                    data['solid_phases'].append(solid)

                j += 1
        elif ' --- Saturation States of Solid Solutions ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]

                # '******' fills in the value region for numbers lower than -999.9999
                if 'None' not in local_line and not re.findall(r'\*{4}\s*$', local_line):
                    name = local_line[:30].strip()
                    log_qk = field_as_float(local_line[44:55])
                    solid_solution = es.SolidPhase(type='solid solution', name=name, log_qk=log_qk)
                    data['solid_phases'].append(solid_solution)

                j += 1
        elif '    --- Fugacities ---' in line:
            j = i + 4
            while lines[j] != '\n':
                local_line = lines[j]
                local_fields = local_line.strip().split()

                if 'None' not in local_line and not re.findall(r'\*{4}', local_line):
                    name = local_fields[0].strip()
                    log_fugacity = field_as_float(local_fields[1])
                    data['gases'].append(es.Gas(name=name, log_fugacity=log_fugacity))

                j += 1

            break

    return es.Eq3Point(**data)


def read_eq6_output(file: Optional[str | io.TextIOWrapper] = None) -> es.Eq6Point:
    if file is None:
        return read_eq6_output('problem.6o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return read_eq6_output(handle)

    try:
        lines = file.readlines()
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.NO_3O_FILE)

    data: dict[str, Any] = {
        'elements': [],
        'aqueous_species': [],
        'solid_phases': [],
        'gases': [],
    }
    precipitates: list[tuple[str, str, str | None, Number]] = []

    reaction_path_terminated = False
    for i in range(len(lines) - 1, 0, -1):
        # Search from bottom of file
        if '---  The reaction path has terminated early ---' in lines[i]:
            raise EleanorException('eq6 reaction path terminated early', code=RunCode.EQ6_EARLY_TERMINATION)
        elif '---  The reaction path has terminated normally ---' in lines[i]:
            reaction_path_terminated = True

    if not reaction_path_terminated:
        raise EleanorException('no reaction path termination status found', code=RunCode.FILE_ERROR_6O)

    for line in lines:
        fields = line.split()
        if '   Affinity of the overall irreversible reaction=' in line:
            data['initial_affinity'] = field_as_float(fields[-2])
            break

    line_num = len(lines) - 1
    while line_num >= 0:
        line = lines[line_num]
        if '                Log Xi=' in line:
            fields = line.split()
            data['log_xi'] = field_as_float(fields[-1])
            break
        line_num -= 1

    while line_num < len(lines):
        line = lines[line_num]
        if line == '\n':
            line_num += 1
            continue

        fields = line.split()

        if ' Temperature=' in line:
            data['temperature'] = field_as_float(fields[1])
        elif ' Pressure=' in line:
            data['pressure'] = field_as_float(fields[1])
        elif ' --- Elemental Composition' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_fields = lines[i].split()
                name = local_fields[0]
                log_molality = np.log10(field_as_float(local_fields[2]))
                data['elements'].append(es.Element(name=name, log_molality=log_molality))
                i += 1
        elif ' NBS pH scale         ' in line:
            data['pH'] = field_as_float(fields[-4])
        elif '                Log oxygen fugacity=' in line:
            data['log_fO2'] = field_as_float(fields[-1])
        elif '              Log activity of water=' in line:
            data['log_activity_water'] = field_as_float(fields[-1])
        elif '                 Ionic strength (I)=' in line:
            data['ionic_strength'] = field_as_float(fields[-2])
        elif '                 Solutes (TDS) mass=' in line:
            data['tds_mass'] = field_as_float(fields[-2])
        elif '              Aqueous solution mass=' in line:
            data['solution_mass'] = field_as_float(fields[-2])
        elif '           --- Extended Total Alkalinity ---' in line:
            local_fields = lines[line_num + 2].split()
            data['extended_alkalinity'] = field_as_float(local_fields[0])
        elif '        --- Aqueous Solution Charge Balance ---' in line:
            local_fields = lines[line_num + 2].split()
            data['charge_imbalance'] = field_as_float(local_fields[-2])
        elif '--- Distribution of Aqueous Solute Species ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_fields = lines[i].split()
                name = local_fields[0]
                if name != 'O2(g)':
                    if '*' in local_fields[-3] or '*' in local_fields[-1]:
                        continue

                    log_molality = field_as_float(local_fields[2])
                    log_activity = field_as_float(local_fields[4])
                    species = es.AqueousSpecies(name=name, log_molality=log_molality, log_activity=log_activity)
                    data['aqueous_species'].append(species)

                i += 1
        elif '--- Summary of Solid Phases (ES) ---' in line:
            i = line_num + 4
            solid = None
            is_solid_solution = False
            if 'None' not in lines[i]:
                import sys
                while True:
                    line = lines[i]
                    local_fields = line.strip().split()

                    if line == '\n' and lines[i + 1] == '\n':
                        if solid is not None:
                            name, mass = solid
                            type = 'solid solution' if is_solid_solution else 'solid'
                            precipitates.append((type, name, None, mass))

                        solid = None
                        is_solid_solution = False
                        break
                    elif line == '\n':
                        if solid is not None:
                            name, mass = solid
                            type = 'solid solution' if is_solid_solution else 'solid'
                            precipitates.append((type, name, None, mass))

                        solid = None
                        is_solid_solution = False
                    elif re.findall(r'^ [^ ]', line):
                        if solid is not None:
                            name, mass = solid
                            type = 'solid solution' if is_solid_solution else 'solid'
                            precipitates.append((type, name, None, mass))

                        name = local_fields[0]
                        log_moles = field_as_float(local_fields[2])
                        solid = (name, log_moles)
                    elif re.findall(r'^   [^ ]', line):
                        if solid is None:
                            msg = f'found solid solution end member without solid solution at {file.name}:{line_num}'
                            raise EleanorParserException()

                        is_solid_solution = True
                        local_fields = line.strip().split()
                        end_member = local_fields[0]
                        log_moles = field_as_float(local_fields[2])
                        solid_solution, *_ = solid
                        precipitates.append(('solid solution', solid_solution, end_member, log_moles))

                    i += 1
        elif '--- Saturation States of Pure Solids ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]
                local_fields = local_line.strip().split()

                # '******' fills in the value region for numbers lower than -999.9999
                if 'None' not in local_line and not re.findall(r'\*{4}\s*$', local_line):
                    phase: es.SolidPhase | None = None
                    name = local_fields[0]
                    log_qk = field_as_float(local_fields[1])

                    for precipitate in precipitates:
                        if precipitate[0] == 'solid' and precipitate[1] == name and precipitate[2] is None:
                            phase = es.SolidPhase(
                                type=precipitate[0],
                                name=name,
                                log_qk=log_qk,
                                log_moles=precipitate[3],
                            )
                            break

                    if phase is None:
                        phase = es.SolidPhase(type='solid', name=name, log_qk=log_qk)

                    data['solid_phases'].append(phase)

                i += 1
        elif ' --- Saturation States of Solid Solutions ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]
                local_fields = local_line.strip().split()

                # '******' fills in the value region for numbers lower than -999.9999
                if 'None' not in local_line and not re.findall(r'\*{4}\s*$', local_line):
                    phase = None
                    name = local_fields[0]
                    log_qk = field_as_float(local_fields[1])

                    for precipitate in precipitates:
                        if precipitate[0] == 'solid solution' and precipitate[1] == name and precipitate[2] is None:
                            phase = es.SolidPhase(
                                type=precipitate[0],
                                name=name,
                                log_qk=log_qk,
                                log_moles=precipitate[3],
                            )
                            break

                    if phase is None:
                        phase = es.SolidPhase(type='solid solution', name=name, log_qk=log_qk)

                    data['solid_phases'].append(phase)

                i += 1

        elif '    --- Fugacities ---' in line:
            i = line_num + 4
            while lines[i] != '\n':
                local_line = lines[i]
                local_fields = local_line.strip().split()

                if 'None' not in local_line and not re.findall(r'\*{4}', local_line):
                    name = local_fields[0].strip()
                    log_fugacity = field_as_float(local_fields[1])
                    data['gases'].append(es.Gas(name=name, log_fugacity=log_fugacity))

                i += 1

            break

        line_num += 1

    return es.Eq6Point(**data)
