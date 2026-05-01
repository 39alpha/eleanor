import io
import re

from eleanor.exceptions import EleanorFileException, EleanorParserException
from eleanor.typing import Species

from .codes import RunCode

_FORTRAN_FLOAT_RE: re.Pattern[str] = re.compile(r"([-\+]?\d+(\.\d+)?)([-\+]\d+)")
_NUMERIC_FALLBACK_RE: re.Pattern[str] = re.compile(r"[0-9Ee\+\.-]+")


def get_field(line: str, pos: int) -> str:
    """
    Split the string `line` on spaces and return the `pos`-th
    """
    return line.split()[pos]


def field_as_float(field: str) -> float:
    """
    Parse a string from an EQ3/6 output file as a `float`
    """
    try:
        return float(field)
    except ValueError:
        pass

    match = _FORTRAN_FLOAT_RE.match(field)
    if match:
        return float(match[1] + "e" + match[3])
    fallback = _NUMERIC_FALLBACK_RE.search(field)
    if fallback is not None:
        try:
            return float(fallback[0])
        except ValueError:
            pass

    raise EleanorParserException(f'failed to read "{field}" as float')


def read_pickup_lines(file: str | io.TextIOWrapper | None = None) -> list[str]:
    if file is None:
        return read_pickup_lines("problem.3p")

    if isinstance(file, str):
        try:
            with open(file, "r") as handle:
                return read_pickup_lines(handle)
        except FileNotFoundError as e:
            raise EleanorFileException(e, code=RunCode.FILE_ERROR_3P)

    try:
        lines = file.readlines()
        for i, line in reversed(list(enumerate(lines))):
            if line.startswith("*---"):
                return lines[i + 1 :]
        raise EleanorFileException("failed to find seperator in pickup file", code=RunCode.FILE_ERROR_3P)
    except FileNotFoundError as e:
        raise EleanorFileException(e, code=RunCode.FILE_ERROR_3P)


# DGM: I believe we can replace this with `read_eq6_output`
def determine_species(file: str | io.TextIOWrapper | None = None) -> Species:
    if file is None:
        return determine_species("problem.3o")

    if isinstance(file, str):
        with open(file, "r") as handle:
            return determine_species(handle)

    suppress: list[str] = []
    elements: list[str] = []
    aqueous_species: list[str] = []
    solids: list[str] = []
    solid_solutions: list[str] = []
    redox: list[str] = []
    gases: list[str] = []

    lines = file.readlines()

    # gather suppress info from near the top of the
    for i in range(len(lines)):
        if " * Alter/suppress options" in lines[i]:
            # number of suppression options
            supp_n = int(lines[i + 1].split()[-1])
            # print(supp_n)
            for j in range(1, supp_n + 1):
                suppress.append(lines[i + 2 * j][12:].strip())
            break

    # search for all other info from teh bottom of the file
    start_idx = 0
    for i in range(len(lines) - 1, 0, -1):
        # find the beginning of the print section for the final system composition.
        if " Done. Hybrid Newton-Raphson iteration converged in " in lines[i]:
            start_idx = i
            break

    # now count forward in lines against to read the system composition
    i = start_idx
    while i < len(lines):
        if re.findall("^\n", lines[i]):
            i += 1
        elif "           --- Elemental Composition of the Aqueous Solution ---" in lines[i]:
            i += 4
            while not re.findall("^\n", lines[i]):
                ele = lines[i][:13].strip()
                if ele not in ["O", "H"]:
                    if float(lines[i].split()[1]) == 0.0:
                        # element not loaded (ie. Cl). this shows up in
                        # the eq3 element set even if set to 0.
                        pass
                    else:
                        elements.append(ele)
                    i += 1
                else:
                    i += 1

        elif "--- Distribution of Aqueous Solute Species ---" in lines[i]:
            i += 4
            while not re.findall("^\n", lines[i]):
                name = lines[i][:26].strip()
                # O2(g) is a ficticious aqueous species
                if name != "O2(g)":
                    aqueous_species.append(name)
                i += 1
        elif "           --- Saturation States of Pure Solids ---" in lines[i]:
            i += 4
            while not re.findall("^\n", lines[i]):
                if "None" not in lines[i]:
                    solids.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif "--- Saturation States of Solid Solutions ---" in lines[i]:
            i += 4
            while not re.findall("^\n", lines[i]):
                if "None" not in lines[i]:
                    solid_solutions.append(lines[i][:26].strip())
                    i += 1
                else:
                    i += 1

        elif "--- Fugacities ---" in lines[i]:
            i += 4
            while not re.findall("^\n", lines[i]):
                gases.append(lines[i][:26].strip())
                i += 1

            break

        else:
            i += 1

    # without knowing which lists contain the suppressions, they all must be searched
    elements = [element for element in elements if element not in suppress]
    aqueous_species = [species for species in aqueous_species if species not in suppress]
    solids = [solid for solid in solids if solid not in suppress]
    solid_solutions = [solid_solution for solid_solution in solid_solutions if solid_solution not in suppress]
    gases = [gas for gas in gases if gas not in suppress]

    return elements, aqueous_species, solids, solid_solutions, redox, gases
