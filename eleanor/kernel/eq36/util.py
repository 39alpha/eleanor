import io
import re
import warnings
from dataclasses import dataclass

import numpy as np

import eleanor.kernel.eq36.equilibrium_space as es
from eleanor.exceptions import EleanorException, EleanorFileException, EleanorParserException
from eleanor.typing import Any, Number, Optional, Species

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
    match: re.Match[str] | list[Any] | None = re.match(r'([-\+]?\d+(\.\d+)?)([-\+]\d+)', field)
    if match:
        return float(match[1] + 'e' + match[3])

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


# DGM: I believe we can replace this with `read_eq6_output`
def determine_species(file: Optional[str | io.TextIOWrapper] = None) -> Species:
    if file is None:
        return determine_species('problem.3o')

    if isinstance(file, str):
        with open(file, 'r') as handle:
            return determine_species(file)

    suppress = []
    elements = []
    aqueous_species = []
    solids = []
    solid_solutions = []
    gases = []

    lines = file.readlines()

    # gather suppress info from near the top of the
    for i in range(len(lines)):
        if ' * Alter/suppress options' in lines[i]:
            # number of suppression options
            supp_n = int(lines[i + 1].split()[-1])
            # print(supp_n)
            for j in range(1, supp_n + 1):
                suppress.append(lines[i + 2 * j][12:].strip())
            break

    # search for all other info from teh bottom of the file
    for i in range(len(lines) - 1, 0, -1):
        # find the beginning of the print section for the final system composition.
        if ' Done. Hybrid Newton-Raphson iteration converged in ' in lines[i]:
            break

    # now count forward in lines against to read the system composition
    while i < len(lines):
        if re.findall('^\n', lines[i]):
            i += 1
        elif '           --- Elemental Composition of the Aqueous Solution ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                ele = lines[i][:13].strip()
                if ele not in ['O', 'H']:
                    if float(lines[i].split()[1]) == 0.0:
                        # element not loaded (ie. Cl). this shows up in
                        # the eq3 element set even if set to 0.
                        pass
                    else:
                        elements.append(ele)
                    i += 1
                else:
                    i += 1

        elif '--- Distribution of Aqueous Solute Species ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                name = lines[i][:26].strip()
                # O2(g) is a ficticious aqueous species
                if name != 'O2(g)':
                    aqueous_species.append(name)
                i += 1
        elif '           --- Saturation States of Pure Solids ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                if 'None' not in lines[i]:
                    solids.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif '--- Saturation States of Solid Solutions ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                if 'None' not in lines[i]:
                    solid_solutions.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif '--- Fugacities ---' in lines[i]:
            i += 4
            while not re.findall('^\n', lines[i]):
                gases.append(lines[i][:26].strip())
                i += 1

            break

        else:
            i += 1

    # without knowing which lists contain the suppressions, they all must be searched
    elements = [element for element in elements if element not in suppress]
    aqueous_species = [species for species in aqueous_species if species not in suppress]
    solids = [solid for solid in solids if solid not in suppress]
    solid_solutions = [solid_solution for solid_solution in solid_solutions if solid_solutions not in suppress]
    gases = [gas for gas in gases if gas not in suppress]

    return elements, aqueous_species, solids, solid_solutions, [], gases
