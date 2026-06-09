import contextlib
import io
import re
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self, cast, final, override

import numpy as np

import eleanor.equilibrium_space as es
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.util import field_as_float
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.typing import StrPath

EQ36_NEG_INF = -99999

path_separator = re.compile("^( -)+$")
blank_line = re.compile(r"^\s*$")
_pattern_cache: dict[str, re.Pattern[str]] = {}


@dataclass
class _PureSolidAccum:
    name: str
    log_qk: np.float64 | None = None
    affinity: np.float64 | None = None
    moles: np.float64 | None = None
    log_moles: np.float64 | None = None
    mass: np.float64 | None = None
    log_mass: np.float64 | None = None
    volume: np.float64 | None = None
    log_volume: np.float64 | None = None


@dataclass
class _EndMemberAccum:
    name: str
    log_qk: np.float64 | None = None
    affinity: np.float64 | None = None
    x: np.float64 | None = None
    log_x: np.float64 | None = None
    log_lambda: np.float64 | None = None
    log_activity: np.float64 | None = None
    moles: np.float64 | None = None
    log_moles: np.float64 | None = None
    mass: np.float64 | None = None
    log_mass: np.float64 | None = None
    volume: np.float64 | None = None
    log_volume: np.float64 | None = None


@dataclass
class _SolidSolutionAccum:
    name: str
    log_qk: np.float64 | None = None
    affinity: np.float64 | None = None
    moles: np.float64 | None = None
    log_moles: np.float64 | None = None
    mass: np.float64 | None = None
    log_mass: np.float64 | None = None
    volume: np.float64 | None = None
    log_volume: np.float64 | None = None
    end_members: dict[str, _EndMemberAccum] = field(default_factory=dict)


def _safe_log10(value: np.float64) -> np.float64:
    if value > 0:
        return cast(np.float64, np.log10(value))
    if value == 0:
        return np.float64("-inf")
    return np.float64("nan")


def _require_saturation_value(value: np.float64 | None, field: str, phase: str) -> np.float64:
    if value is None:
        raise EleanorKernelException(f"missing {field} for {phase}", code=RunCode.PARSER_ERROR)
    return value


def _freeze_pure_solid(a: _PureSolidAccum) -> es.PureSolid:
    return es.PureSolid(
        name=a.name,
        log_qk=_require_saturation_value(a.log_qk, "log_qk", f"pure solid {a.name}"),
        affinity=_require_saturation_value(a.affinity, "affinity", f"pure solid {a.name}"),
        log_moles=np.float64(-np.inf) if (a.moles is not None and a.moles == EQ36_NEG_INF) else a.log_moles,
        log_mass=np.float64(-np.inf) if (a.mass is not None and a.mass == EQ36_NEG_INF) else a.log_mass,
        log_volume=np.float64(-np.inf) if (a.volume is not None and a.volume == EQ36_NEG_INF) else a.log_volume,
    )


def _freeze_solid_solution(a: _SolidSolutionAccum) -> es.SolidSolution:
    return es.SolidSolution(
        name=a.name,
        log_qk=_require_saturation_value(a.log_qk, "log_qk", f"solid solution {a.name}"),
        affinity=_require_saturation_value(a.affinity, "affinity", f"solid solution {a.name}"),
        log_moles=a.log_moles,
        log_mass=a.log_mass,
        log_volume=a.log_volume,
        end_members=[
            es.EndMember(
                name=em.name,
                log_qk=_require_saturation_value(em.log_qk, "log_qk", f"end member {em.name}"),
                affinity=_require_saturation_value(em.affinity, "affinity", f"end member {em.name}"),
                log_moles=em.log_moles,
                log_mass=em.log_mass,
                log_volume=em.log_volume,
            )
            for em in a.end_members.values()
        ],
    )


class OutputParser(ABC):
    line_num: int
    lines: list[str]
    _elements: list[es.Element]
    _aqueous_species: list[es.AqueousSpecies]
    _gases: list[es.Gas]
    _redox_reactions: list[es.RedoxReaction]
    _pure_solids: dict[str, _PureSolidAccum]
    _solid_solutions: dict[str, _SolidSolutionAccum]
    _pcH: np.float64 | None
    _pHCl: np.float64 | None
    _extended_alkalinity: np.float64 | None
    _temperature: np.float64
    _pressure: np.float64
    _pH: np.float64
    _Eh: np.float64
    _pe: np.float64
    _Ah: np.float64
    _fO2: np.float64
    _log_fO2: np.float64
    _activity_water: np.float64
    _log_activity_water: np.float64
    _mole_fraction_water: np.float64
    _log_mole_fraction_water: np.float64
    _activity_coefficient_water: np.float64
    _log_activity_coefficient_water: np.float64
    _osmotic_coefficient: np.float64
    _stoichiometric_osmotic_coefficient: np.float64
    _sum_molalities: np.float64
    _sum_stoichiometric_molalities: np.float64
    _ionic_strength: np.float64
    _stoichiometric_ionic_strength: np.float64
    _ionic_asymmetry: np.float64
    _stoichiometric_ionic_asymmetry: np.float64
    _log_ionic_strength: np.float64
    _log_stoichiometric_ionic_strength: np.float64
    _log_sum_molalities: np.float64
    _log_sum_stoichiometric_molalities: np.float64
    _solvent_mass: np.float64
    _solute_mass: np.float64
    _solution_mass: np.float64
    _solvent_fraction: np.float64
    _solute_fraction: np.float64
    _tds: np.float64
    _reactants: list[es.Reactant]
    _overall_affinity: np.float64 | None
    _reactant_mass_reacted: np.float64
    _reactant_mass_remaining: np.float64
    _solid_mass_created: np.float64
    _solid_mass_destroyed: np.float64
    _solid_mass_change: np.float64
    _solid_volume_created: np.float64
    _solid_volume_destroyed: np.float64
    _solid_volume_change: np.float64
    _charge_imbalance: np.float64

    def __init__(self, file: io.TextIOBase) -> None:
        self.line_num = 0
        self.lines = file.readlines()
        self._reset_common_accumulators()

    def _reset_common_accumulators(self) -> None:
        self._elements = []
        self._aqueous_species = []
        self._gases = []
        self._redox_reactions = []

        self._pure_solids = {}
        self._solid_solutions = {}

        self._pcH = None
        self._pHCl = None
        self._extended_alkalinity = None
        self._temperature = np.float64(0.0)
        self._pressure = np.float64(0.0)
        self._pH = np.float64(0.0)
        self._Eh = np.float64(0.0)
        self._pe = np.float64(0.0)
        self._Ah = np.float64(0.0)

        self._fO2 = np.float64(0.0)
        self._log_fO2 = np.float64(0.0)
        self._activity_water = np.float64(0.0)
        self._log_activity_water = np.float64(0.0)
        self._mole_fraction_water = np.float64(0.0)
        self._log_mole_fraction_water = np.float64(0.0)
        self._activity_coefficient_water = np.float64(0.0)
        self._log_activity_coefficient_water = np.float64(0.0)

        self._osmotic_coefficient = np.float64(0.0)
        self._stoichiometric_osmotic_coefficient = np.float64(0.0)
        self._sum_molalities = np.float64(0.0)
        self._sum_stoichiometric_molalities = np.float64(0.0)
        self._ionic_strength = np.float64(0.0)
        self._stoichiometric_ionic_strength = np.float64(0.0)
        self._ionic_asymmetry = np.float64(0.0)
        self._stoichiometric_ionic_asymmetry = np.float64(0.0)

        self._log_ionic_strength = np.float64(0.0)
        self._log_stoichiometric_ionic_strength = np.float64(0.0)
        self._log_sum_molalities = np.float64(0.0)
        self._log_sum_stoichiometric_molalities = np.float64(0.0)

        self._solvent_mass = np.float64(0.0)
        self._solute_mass = np.float64(0.0)
        self._solution_mass = np.float64(0.0)
        self._solvent_fraction = np.float64(0.0)
        self._solute_fraction = np.float64(0.0)
        self._tds = np.float64(0.0)

        self._reactants = []
        self._overall_affinity = None
        self._reactant_mass_reacted = np.float64(0.0)
        self._reactant_mass_remaining = np.float64(0.0)

        self._solid_mass_created = np.float64(0.0)
        self._solid_mass_destroyed = np.float64(0.0)
        self._solid_mass_change = np.float64(0.0)
        self._solid_volume_created = np.float64(0.0)
        self._solid_volume_destroyed = np.float64(0.0)
        self._solid_volume_change = np.float64(0.0)

        self._charge_imbalance = np.float64(0.0)

    def eof(self) -> bool:
        return not (0 <= self.line_num < len(self.lines))

    def retreat(self, n: int = 1) -> None:
        self.line_num -= n

    def advance(self, n: int = 1) -> None:
        self.line_num += n

    def line(self) -> str:
        return self.lines[self.line_num]

    def peek(self) -> str:
        return self.lines[self.line_num + 1]

    def is_blank(self) -> bool:
        return blank_line.match(self.line()) is not None

    def match_pattern(self, pattern: str | re.Pattern[str]) -> re.Match[str] | None:
        if isinstance(pattern, str):
            compiled = _pattern_cache.get(pattern)
            if compiled is None:
                compiled = _pattern_cache[pattern] = re.compile(pattern)
            pattern = compiled
        return pattern.match(self.line())

    def unconsume_to_pattern(self, pattern: str | re.Pattern[str]) -> None:
        if isinstance(pattern, str):
            compiled = _pattern_cache.get(pattern)
            if compiled is None:
                compiled = _pattern_cache[pattern] = re.compile(pattern)
            pattern = compiled
        while self.eof():
            self.retreat()
        while not self.eof() and not pattern.match(self.line()):
            self.retreat()

    def consume_to_pattern(self, pattern: str | re.Pattern[str]) -> None:
        if isinstance(pattern, str):
            compiled = _pattern_cache.get(pattern)
            if compiled is None:
                compiled = _pattern_cache[pattern] = re.compile(pattern)
            pattern = compiled
        lines = self.lines
        line_num = self.line_num
        num_lines = len(lines)
        while line_num < num_lines and not pattern.match(lines[line_num]):
            line_num += 1
        self.line_num = line_num

    def consume_while_pattern(self, pattern: str | re.Pattern[str]) -> None:
        if isinstance(pattern, str):
            compiled = _pattern_cache.get(pattern)
            if compiled is None:
                compiled = _pattern_cache[pattern] = re.compile(pattern)
            pattern = compiled
        lines = self.lines
        line_num = self.line_num
        num_lines = len(lines)
        while line_num < num_lines and pattern.match(lines[line_num]):
            line_num += 1
        self.line_num = line_num

    def consume_blank_lines(self) -> None:
        self.consume_while_pattern(blank_line)

    def consume_to_header(self, header: str) -> None:
        self.consume_to_pattern(rf"^\s*---\s+{header}\s+---\s*$")

    def advance_to_xi_step(self) -> bool:
        self.consume_to_pattern(r"\s*Stepping to Xi")
        if self.eof():
            return False
        found_separator = False
        while not self.eof():
            if path_separator.match(self.line()):
                self.advance()
                found_separator = True
                break
            self.advance()
        if not found_separator:
            raise EleanorKernelException("expected path separator after Stepping to Xi", code=RunCode.PARSER_ERROR)
        return True

    def read_key_value(self) -> tuple[str, np.float64]:
        key, value = self.line().strip().split("=")
        return key, field_as_float(value)

    def read_key_value_unit(self) -> tuple[str, np.float64, str]:
        key, value = self.line().strip().split("=")
        value, unit = value.strip().split()
        return key, field_as_float(value), unit

    def read_basic_property(self, name: str, units: list[str] | None = None, advance: bool = True) -> np.float64:
        line = self.line().strip()
        if not line.startswith(f"{name}="):
            raise EleanorKernelException(f"expected {name} entry", code=RunCode.PARSER_ERROR)
        if units is None or len(units) == 0:
            _default_key, value = self.read_key_value()
        else:
            _default_key, value, unit = self.read_key_value_unit()
            if unit.lower() not in units:
                raise EleanorKernelException(f"expected {name} in {units[0]}", code=RunCode.PARSER_ERROR)
        if advance:
            self.advance()
        return value

    def read_log_property(self, name: str, units: list[str] | None = None) -> tuple[np.float64, np.float64]:
        if len(name) == 0:
            raise EleanorKernelException("expected name to be a non-empty string", code=RunCode.PARSER_ERROR)
        log_name = "Log " + name.lower()
        self.consume_to_pattern(rf"\s*{name}")
        value = self.read_basic_property(name, units=units)
        log_value = self.read_basic_property(log_name)
        return value, log_value

    def read_basic_table(
        self,
        *column_names: str,
        row_names: list[str] | None = None,
    ) -> dict[str, dict[str, np.float64]]:
        table: dict[str, dict[str, np.float64]] = {}
        lines = self.lines
        line_num = self.line_num
        num_lines = len(lines)
        _blank = blank_line
        while line_num < num_lines and not _blank.match(lines[line_num]):
            name, *columns = lines[line_num].strip().split()
            if row_names is not None:
                if len(table) >= len(row_names):
                    raise EleanorKernelException(
                        f"expected {len(row_names)} rows, got more at line {line_num}",
                        code=RunCode.PARSER_ERROR,
                    )
                name = row_names[len(table)]
            if len(column_names) != len(columns):
                raise EleanorKernelException(
                    f"expected {len(column_names)} columns, got {len(columns)} at line {line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            table[name] = dict(zip(column_names, map(field_as_float, columns), strict=True))
            line_num += 1
        self.line_num = line_num
        if row_names is not None and len(table) != len(row_names):
            raise EleanorKernelException(
                f"expected {len(row_names)} rows, got {len(table)} at line {self.line_num}",
                code=RunCode.PARSER_ERROR,
            )
        return table

    def consume_basic_table(self, *column_names: str, row_names: list[str] | None = None) -> None:
        _ = self.read_basic_table(*column_names, row_names=row_names)

    def include_aqueous_species(self, _name: str) -> bool:
        return True

    @abstractmethod
    def read_elemental_composition(self) -> None:
        pass

    @abstractmethod
    def read_numerical_composition(self) -> None:
        pass

    @abstractmethod
    def read_sensible_composition(self) -> None:
        pass

    @abstractmethod
    def read_bulk_properties(self) -> None:
        pass

    @abstractmethod
    def read_charge_balance(self) -> None:
        pass

    def read_pH_like(self) -> None:
        self.consume_to_header("The pH, Eh, pe-, and Ah on various pH scales")
        self.advance(n=4)
        while not self.eof() and not self.is_blank():
            *scale, ph, eh, pe, ah = self.line().strip().split()
            if "*" in ph or "*" in eh or "*" in pe or "*" in ah:
                self.advance()
                continue
            scale_name = " ".join(scale)
            if scale_name in ["NBS pH scale", "NBS"]:
                self._pH = field_as_float(ph)
                self._Eh = field_as_float(eh)
                self._pe = field_as_float(pe)
                self._Ah = field_as_float(ah)
            self.advance()
        self.consume_blank_lines()

        with contextlib.suppress(Exception):
            self._pcH = self.read_basic_property("pcH")

        with contextlib.suppress(Exception):
            self._pHCl = self.read_basic_property("pHCl")

    def read_alkalinity(self) -> None:
        self._extended_alkalinity = None
        self.consume_to_pattern(r"^.*Alkalinity.*$")
        if self.eof() or "is not defined" in self.line():
            return
        pattern = re.compile(r"^\s*---\s+(.*) Total Alkalinity\s+--")
        found_extended = False
        while not found_extended:
            self.consume_to_pattern(pattern)
            m = pattern.match(self.line())
            if m is None:
                raise EleanorKernelException(
                    f"unexpected state in OutputParser at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            found_extended = m[1] == "Extended"
            self.advance(2)
            alkalinity_s, _units = self.line().strip().split()
            if found_extended:
                self._extended_alkalinity = field_as_float(alkalinity_s)
            self.advance()
            while not self.eof() and not self.is_blank():
                self.advance()

    def read_aqueous_solute(self) -> None:
        self.consume_to_header("Distribution of Aqueous Solute Species")
        self.consume_to_pattern(r"\s*Species\s+Molality\s+Log Molality\s+Log Gamma\s+Log Activity\s*")
        self.advance(n=2)
        species_list: list[es.AqueousSpecies] = []
        lines = self.lines
        line_num = self.line_num
        num_lines = len(lines)
        _blank = blank_line
        while line_num < num_lines and not _blank.match(lines[line_num]):
            species, molality_s, log_molality_s, log_gamma_s, log_activity_s = lines[line_num].strip().split()
            if "*" in molality_s or "*" in log_molality_s or "*" in log_gamma_s or "*" in log_activity_s:
                line_num += 1
                continue
            if not self.include_aqueous_species(species):
                line_num += 1
                continue
            molality = field_as_float(molality_s)
            log_activity = field_as_float(log_activity_s)
            species_list.append(
                es.AqueousSpecies(
                    name=species,
                    log_molality=np.float64(-np.inf) if molality == 0 else field_as_float(log_molality_s),
                    log_activity=np.float64(-np.inf) if log_activity == EQ36_NEG_INF else log_activity,
                    log_gamma=field_as_float(log_gamma_s),
                ),
            )
            line_num += 1
        self.line_num = line_num
        self._aqueous_species = species_list

    def read_redox_reactions(self) -> None:
        self.consume_to_header("Aqueous Redox Reactions")
        self.consume_to_pattern(r"\s*Couple\s+Eh, volts\s+pe-\s+log fO2\s+Ah, kcal\s*")
        self.advance(n=2)
        reactions: list[es.RedoxReaction] = []
        while not self.eof() and not self.is_blank():
            couple, eh, pe, log_fO2, ah = self.line().strip().split()
            if "*" in eh or "*" in pe or "*" in log_fO2 or "*" in ah:
                self.advance()
                continue
            reactions.append(
                es.RedoxReaction(
                    couple=couple,
                    Eh=field_as_float(eh),
                    pe=field_as_float(pe),
                    log_fO2=field_as_float(log_fO2),
                    Ah=field_as_float(ah),
                ),
            )
            self.advance()
        self._redox_reactions = reactions

    def read_reactants(self) -> None:
        self._reactants = []
        self._overall_affinity = None
        self._reactant_mass_reacted = np.float64(0.0)
        self._reactant_mass_remaining = np.float64(0.0)
        self.consume_to_header("Reactant Summary")
        self.consume_to_pattern(r"^\s+Reactant\s+Moles\s+Delta moles\s+Mass, g\s+Delta mass, g\s*$")
        self.advance()
        self.consume_blank_lines()
        if self.line().strip() == "None":
            return
        raw: dict[str, dict[str, np.float64]] = {}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            while not self.eof() and not self.is_blank():
                name, moles, delta_moles, mass, delta_mass = self.line().strip().split()
                raw[name] = {
                    "log_moles_remaining": _safe_log10(field_as_float(moles)),
                    "log_moles_reacted": _safe_log10(field_as_float(delta_moles)),
                    "log_mass_remaining": _safe_log10(field_as_float(mass)),
                    "log_mass_reacted": _safe_log10(field_as_float(delta_mass)),
                }
                self.advance()
        self.consume_blank_lines()
        self._reactant_mass_remaining = self.read_basic_property("Mass remaining", units=["grams", "gram", "g"])
        self._reactant_mass_reacted = self.read_basic_property("Mass destroyed", units=["grams", "gram", "g"])
        self.consume_to_pattern(r"^\s+Reactant\s+Affinity\s+Rel\. Rate\s*$")
        self.advance(n=3)
        while not self.eof() and not self.is_blank():
            name, affinity_s, relative_rate_s = self.line().strip().split()
            if name not in raw:
                raise EleanorKernelException(
                    f"found affinity for unexpected reactant at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if "*" in affinity_s or "*" in relative_rate_s:
                self.advance()
                continue
            raw[name]["affinity"] = field_as_float(affinity_s)
            raw[name]["relative_rate"] = field_as_float(relative_rate_s)
            self.advance()
        self.consume_blank_lines()
        self._overall_affinity = self.read_basic_property(
            "Affinity of the overall irreversible reaction",
            units=["kcal", "kcal."],
        )
        self.consume_blank_lines()
        for name, props in raw.items():
            if "affinity" not in props or "relative_rate" not in props:
                continue
            self._reactants.append(
                es.Reactant(
                    name=name,
                    affinity=props["affinity"],
                    relative_rate=props["relative_rate"],
                    log_moles_reacted=props["log_moles_reacted"],
                    log_moles_remaining=props["log_moles_remaining"],
                    log_mass_reacted=props["log_mass_reacted"],
                    log_mass_remaining=props["log_mass_remaining"],
                ),
            )

    def read_solid_blocks(self) -> None:
        def is_end_member(s: str) -> bool:
            return s.startswith("   ")

        parent_phase: str | None = None
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            lines = self.lines
            line_num = self.line_num
            num_lines = len(lines)
            _blank = blank_line
            while line_num < num_lines and not _blank.match(lines[line_num]):
                line = lines[line_num]
                next_line = lines[line_num + 1] if line_num + 1 < num_lines else ""
                try:
                    solid, log_moles_s, moles_s, mass_s, volume_s = line.strip().split()
                except ValueError as e:
                    raise EleanorKernelException(
                        f"unexpected solid phase row format at line {line_num}",
                        code=RunCode.PARSER_ERROR,
                    ) from e
                if "*" in log_moles_s or "*" in moles_s or "*" in mass_s or "*" in volume_s:
                    if _blank.match(next_line):
                        line_num += 2
                    else:
                        line_num += 1
                    continue
                moles_value = field_as_float(moles_s)
                log_moles_value = field_as_float(log_moles_s)
                mass_value = field_as_float(mass_s)
                volume_value = field_as_float(volume_s)
                if is_end_member(line):
                    if parent_phase is None:
                        raise EleanorKernelException("unexpected end member", code=RunCode.PARSER_ERROR)
                    if parent_phase not in self._solid_solutions:
                        self._solid_solutions[parent_phase] = _SolidSolutionAccum(name=parent_phase)
                    end_members = self._solid_solutions[parent_phase].end_members
                    if solid not in end_members:
                        end_members[solid] = _EndMemberAccum(name=solid)
                    em = end_members[solid]
                    em.moles = moles_value
                    em.log_moles = log_moles_value
                    em.mass = mass_value
                    em.log_mass = _safe_log10(mass_value)
                    em.volume = volume_value
                    em.log_volume = _safe_log10(volume_value)
                elif is_end_member(next_line) and not _blank.match(next_line):
                    parent_phase = solid
                    if solid not in self._solid_solutions:
                        self._solid_solutions[solid] = _SolidSolutionAccum(name=solid)
                    ss = self._solid_solutions[solid]
                    ss.moles = moles_value
                    ss.log_moles = log_moles_value
                    ss.mass = mass_value
                    ss.log_mass = _safe_log10(mass_value)
                    ss.volume = volume_value
                    ss.log_volume = _safe_log10(volume_value)
                else:
                    if solid not in self._pure_solids:
                        self._pure_solids[solid] = _PureSolidAccum(name=solid)
                    ps = self._pure_solids[solid]
                    ps.moles = moles_value
                    ps.log_moles = log_moles_value
                    ps.mass = mass_value
                    ps.log_mass = _safe_log10(mass_value)
                    ps.volume = volume_value
                    ps.log_volume = _safe_log10(volume_value)
                    if solid.startswith("fix_f"):
                        ps.log_qk = np.float64(0.0)
                        ps.affinity = np.float64(0.0)
                    parent_phase = None
                if _blank.match(next_line):
                    line_num += 2
                else:
                    line_num += 1
            self.line_num = line_num

    def read_solid_phases(self) -> None:
        self._solid_mass_created = np.float64(0.0)
        self._solid_mass_destroyed = np.float64(0.0)
        self._solid_mass_change = np.float64(0.0)
        self._solid_volume_created = np.float64(0.0)
        self._solid_volume_destroyed = np.float64(0.0)
        self._solid_volume_change = np.float64(0.0)
        self.consume_to_header(r"Summary of Solid Phases \(ES\)")
        self.consume_to_pattern(r"\s*Phase/End-member\s+Log moles\s+Moles\s+Grams\s+Volume, cm3\s*")
        self.advance(n=2)
        if "None" in self.line():
            self.advance(n=3)
        else:
            while not self.eof() and "None" not in self.line() and not self.is_blank():
                self.read_solid_blocks()
            self.advance()
        if self.match_pattern(r"^\s*---\s+Grand Summary of Solid Phases \(ES \+ PRS \+ Reactants\)\s+---\s*$"):
            self.consume_to_pattern(r"\s*Phase/End-member\s+Log moles\s+Moles\s+Grams\s+Volume, cm3\s*")
            self.advance(n=2)
            while not self.eof() and "None" not in self.line() and not self.is_blank():
                self.read_solid_blocks()
            self.advance(n=3)
        else:
            self.advance(n=2)
        summary = self.read_basic_table("mass", "volume", row_names=["created", "destroyed", "net"])
        self._solid_mass_created = summary["created"]["mass"]
        self._solid_mass_destroyed = summary["destroyed"]["mass"]
        self._solid_mass_change = summary["net"]["mass"]
        self._solid_volume_created = summary["created"]["volume"]
        self._solid_volume_destroyed = summary["destroyed"]["volume"]
        self._solid_volume_change = summary["net"]["volume"]

    def read_aqueous_saturation_states(self) -> None:
        self.consume_to_header("Saturation States of Aqueous Reactions Not Fixed at Equilibrium")
        self.consume_to_pattern(r"\s*Reaction\s+Log Q/K\s+Affinity, kcal\s*")
        self.advance(n=2)
        while not self.eof() and not self.is_blank():
            self.advance()

    def _read_saturation_state_rows(self, header: str) -> dict[str, tuple[np.float64, np.float64]]:
        rows: dict[str, tuple[np.float64, np.float64]] = {}
        self.consume_to_header(header)
        self.consume_to_pattern(r"\s*Phase\s+Log Q/K\s+Affinity, kcal\s*")
        self.advance(n=2)
        lines = self.lines
        line_num = self.line_num
        num_lines = len(lines)
        _blank = blank_line
        while line_num < num_lines and not _blank.match(lines[line_num]):
            cur = lines[line_num].strip()
            if cur == "None":
                break
            phase, log_qk, affinity, *rest = cur.split()
            if len(rest) > 1:
                raise EleanorKernelException(
                    f"too many columns in {header} at line {line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if len(rest) != 0 and rest[0] not in ["SATD", "SSATD"]:
                raise EleanorKernelException(
                    f"unexpected value in State column of {header} at line {line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if "*" in log_qk or "*" in affinity:
                line_num += 1
                continue
            rows[phase] = (field_as_float(log_qk), field_as_float(affinity))
            line_num += 1
        self.line_num = line_num
        return rows

    def read_pure_solid_saturation_states(self) -> None:
        for phase, (log_qk, affinity) in self._read_saturation_state_rows("Saturation States of Pure Solids").items():
            if phase not in self._pure_solids:
                self._pure_solids[phase] = _PureSolidAccum(name=phase)
            self._pure_solids[phase].log_qk = log_qk
            self._pure_solids[phase].affinity = affinity

    def read_liquid_saturation_states(self) -> None:
        self.consume_to_header("Saturation States of Pure Liquids")
        self.consume_to_pattern(r"\s*Phase\s+Log Q/K\s+Affinity, kcal\s*")
        self.advance(n=2)
        while not self.eof() and not self.is_blank():
            _phase, _log_qk, _affinity, *rest = self.line().strip().split()
            if len(rest) > 1:
                raise EleanorKernelException(
                    f"too many columns in Saturation States of Pure Liquids at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if len(rest) != 0 and rest[0] not in ["SATD", "SSATD"]:
                raise EleanorKernelException(
                    f"unexpected value in State column of Saturation States of Pure Liquids block at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            self.advance()

    def read_solid_solution_saturation_states(self) -> None:
        for phase, (log_qk, affinity) in self._read_saturation_state_rows(
            "Saturation States of Solid Solutions",
        ).items():
            if phase not in self._solid_solutions:
                self._solid_solutions[phase] = _SolidSolutionAccum(name=phase)
            self._solid_solutions[phase].log_qk = log_qk
            self._solid_solutions[phase].affinity = affinity
        for props in self._solid_solutions.values():
            for end_member, em_props in props.end_members.items():
                if em_props.log_qk is None and end_member in self._pure_solids:
                    em_props.log_qk = self._pure_solids[end_member].log_qk
                if em_props.affinity is None and end_member in self._pure_solids:
                    em_props.affinity = self._pure_solids[end_member].affinity

    def read_end_members(self, end_members: dict[str, _EndMemberAccum]) -> None:
        self.consume_to_pattern(r"^\s*Component\s+x\s+Log x\s+ Log lambda\s+Log activity\s*$")
        self.advance(n=2)
        while not self.eof() and not self.is_blank():
            end_member, x, log_x, log_lambda, log_activity = self.line().strip().split()
            if "*" in x or "*" in log_x or "*" in log_lambda or "*" in log_activity:
                self.advance()
                continue
            if end_member not in end_members:
                end_members[end_member] = _EndMemberAccum(name=end_member)
            em = end_members[end_member]
            em.x = field_as_float(x)
            em.log_x = field_as_float(log_x)
            em.log_lambda = field_as_float(log_lambda)
            em.log_activity = field_as_float(log_activity)
            self.advance()

    def read_mineral(
        self,
        header: str,
        phases: dict[str, _SolidSolutionAccum],
        expected_phase: str | None = None,
    ) -> None:
        self.consume_to_pattern(r"^\s*Mineral\s+Log Q/K\s+Aff, kcal\s+State\s*$")
        self.advance(n=2)
        mineral, log_qk, affinity, *state = self.line().strip().split()
        if expected_phase is not None and expected_phase != mineral:
            raise EleanorKernelException(
                f"expected phase ({expected_phase}) and mineral ({mineral}) to match in {header} at line {self.line_num}",
                code=RunCode.PARSER_ERROR,
            )
        if len(state) > 1:
            raise EleanorKernelException(f"too many columns in {header} at {self.line_num}", code=RunCode.PARSER_ERROR)
        if len(state) != 0 and state[0] not in ["SATD", "SSATD"]:
            raise EleanorKernelException(
                f"unexpected columns in {header} at line {self.line_num}",
                code=RunCode.PARSER_ERROR,
            )
        if "*" in log_qk or "*" in affinity:
            self.advance()
            return
        if mineral not in phases:
            phases[mineral] = _SolidSolutionAccum(name=mineral)
        phases[mineral].log_qk = field_as_float(log_qk)
        phases[mineral].affinity = field_as_float(affinity)
        self.advance()

    def read_end_member_saturations(self, header: str, end_members: dict[str, _EndMemberAccum]) -> None:
        while not self.eof() and not self.is_blank():
            end_member, log_qk, affinity, *state = self.line().strip().split()
            if len(state) > 1:
                raise EleanorKernelException(
                    f"too many columns in {header} at {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if len(state) != 0 and state[0] not in ["SATD", "SSATD"]:
                raise EleanorKernelException(
                    f"unexpected value in State column of {header} block at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            if "*" in log_qk or "*" in affinity:
                self.advance()
                continue
            if end_member not in end_members:
                raise EleanorKernelException(
                    f"unexpected end member ({end_member}) in {header} block at line {self.line_num}",
                    code=RunCode.PARSER_ERROR,
                )
            end_members[end_member].log_qk = field_as_float(log_qk)
            end_members[end_member].affinity = field_as_float(affinity)
            self.advance()

    def read_product_phases(self, header: str) -> None:
        self.consume_to_header(header)
        if self.eof():
            raise EleanorKernelException(f"expected {header} block at line {self.line_num}", code=RunCode.PARSER_ERROR)
        self.advance(n=2)
        while not self.eof():
            match = re.match(r"^\s+---\s(.*)\s---\s*$", self.line())
            if match and match[1] == "Fugacities":
                self.line_num -= 1
                break
            if match:
                phase = match[1]
                if phase not in self._solid_solutions:
                    self._solid_solutions[phase] = _SolidSolutionAccum(name=phase)
                end_members = self._solid_solutions[phase].end_members
                self.read_end_members(end_members)
                self.read_mineral(header, self._solid_solutions, phase)
                self.read_end_member_saturations(header, end_members)
            self.advance()

    def read_fugacities(self) -> None:
        self.consume_to_header("Fugacities")
        self.consume_to_pattern(r"\s*Gas\s+Log Fugacity\s+Fugacity\s*")
        self.advance(n=2)
        gases: list[es.Gas] = []
        while not self.eof() and not self.is_blank():
            gas, log_fugacity, fugacity = self.line().strip().split()
            if "*" in log_fugacity or "*" in fugacity:
                self.advance()
                continue
            gases.append(es.Gas(name=gas, log_fugacity=field_as_float(log_fugacity)))
            self.advance()
        self._gases = gases

    @abstractmethod
    def parse(self) -> Self:
        pass


@final
class OutputParser3(OutputParser):
    point: es.Point | None
    _solution_volume: np.float64 | None
    _solution_density: np.float64 | None
    _cations: np.float64 | None
    _anions: np.float64 | None
    _total_charge: np.float64 | None
    _mean_charge: np.float64 | None

    def __init__(self, file: StrPath | io.TextIOBase | None = None) -> None:
        if file is None:
            file = Path("problem.3o")
        try:
            if isinstance(file, (str, Path)):
                with Path(file).open("r") as handle:
                    super().__init__(handle)
            else:
                super().__init__(file)
        except FileNotFoundError as e:
            raise EleanorKernelException("failed to open 3o file", code=RunCode.NO_3O_FILE) from e
        self.point = None
        self._solution_volume = None
        self._solution_density = None
        self._cations = None
        self._anions = None
        self._total_charge = None
        self._mean_charge = None

    @override
    def read_elemental_composition(self) -> None:
        self.consume_to_header("Elemental Composition of the Aqueous Solution")
        self.consume_to_pattern(r"\s*Element\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*")
        self.advance(n=2)
        table = self.read_basic_table("concentration", "mass_fraction", "molarity", "molality")
        elements: list[es.Element] = []
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            for name, props in table.items():
                elements.append(
                    es.Element(
                        name=name,
                        log_molality=_safe_log10(props["molality"]),
                        mass_fraction=props["mass_fraction"] * np.float64(1e-6),
                    ),
                )
        self._elements = elements

    @override
    def read_numerical_composition(self) -> None:
        self.consume_to_header("Numerical Composition of the Aqueous Solution")
        self.consume_to_pattern(r"\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*")
        self.advance(n=2)
        self.consume_basic_table("concentration", "mass_fraction", "molarity", "molality")

    @override
    def read_sensible_composition(self) -> None:
        self.consume_to_header("Sensible Composition of the Aqueous Solution")
        self.consume_to_pattern(r"\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*")
        self.advance(n=2)
        self.consume_basic_table("concentration", "mass_fraction", "molarity", "molality")

    @override
    def read_bulk_properties(self) -> None:
        self._fO2, self._log_fO2 = self.read_log_property("Oxygen fugacity", units=["bars", "bar"])
        self._activity_water, self._log_activity_water = self.read_log_property("Activity of water")
        self._mole_fraction_water, self._log_mole_fraction_water = self.read_log_property("Mole fraction of water")
        self._activity_coefficient_water, self._log_activity_coefficient_water = self.read_log_property(
            "Activity coefficient of water",
        )
        self.consume_to_pattern(r"\s*Osmotic coefficient")
        self._osmotic_coefficient = self.read_basic_property("Osmotic coefficient")
        self._stoichiometric_osmotic_coefficient = self.read_basic_property("Stoichiometric osmotic coefficient")
        self.consume_to_pattern(r"\s*Sum of molalities")
        self._sum_molalities = self.read_basic_property("Sum of molalities")
        self._sum_stoichiometric_molalities = self.read_basic_property("Sum of stoichiometric molalities")
        self.consume_to_pattern(r"\s*Ionic strength \(I\)")
        self._ionic_strength = self.read_basic_property("Ionic strength (I)", units=["molal"])
        self._stoichiometric_ionic_strength = self.read_basic_property("Stoichiometric ionic strength", units=["molal"])
        self.consume_to_pattern(r"\s*Ionic asymmetry \(J\)")
        self._ionic_asymmetry = self.read_basic_property("Ionic asymmetry (J)", units=["molal"])
        self._stoichiometric_ionic_asymmetry = self.read_basic_property(
            "Stoichiometric ionic asymmetry",
            units=["molal"],
        )
        self.consume_to_pattern(r"\s*Solvent mass")
        self._solvent_mass = self.read_basic_property("Solvent mass", units=["grams", "gram", "g"])
        self._solute_mass = self.read_basic_property("Solutes (TDS) mass", units=["grams", "gram", "g"])
        self._solution_mass = self.read_basic_property("Aqueous solution mass", units=["grams", "gram", "g"])
        self.consume_to_pattern(r"\s*Aqueous solution volume")
        self._solution_volume = self.read_basic_property("Aqueous solution volume", units=["liters", "l"])
        self.consume_to_pattern(r"\s*Solvent fraction")
        self._solvent_fraction = self.read_basic_property("Solvent fraction", units=["kg.h2o/kg.sol"])
        self._solute_fraction = self.read_basic_property("Solute fraction", units=["kg.tds/kg.sol"])
        self.consume_to_pattern(r"\s*Total dissolved solutes \(TDS\)")
        self._tds = self.read_basic_property("Total dissolved solutes (TDS)", units=["mg/kg.sol"])
        self.consume_to_pattern(r"\s*Solution density")
        self._solution_density = self.read_basic_property("Solution density", units=["g/ml"])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            self._log_ionic_strength = _safe_log10(self._ionic_strength)
            self._log_stoichiometric_ionic_strength = _safe_log10(self._stoichiometric_ionic_strength)
            self._log_sum_molalities = _safe_log10(self._sum_molalities)
            self._log_sum_stoichiometric_molalities = _safe_log10(self._sum_stoichiometric_molalities)

    @override
    def read_charge_balance(self) -> None:
        self.consume_to_header("Electrical Balance Totals")
        self.advance(n=4)
        self._cations = self.read_basic_property("Sigma(mz) cations")
        self._anions = self.read_basic_property("Sigma(mz) anions")
        self._total_charge = self.read_basic_property("Total charge")
        self._mean_charge = self.read_basic_property("Mean charge")
        self._charge_imbalance = self.read_basic_property("Charge imbalance")
        self.advance(4)
        self.advance()
        self.advance(3)
        m = re.compile(r"^\s*---\s+Electrical Balancing on (.*)\s+---\s*$").match(self.line())
        if m is None:
            raise EleanorKernelException(
                f"expected Electrical Balancing block at {self.line_num}",
                code=RunCode.PARSER_ERROR,
            )
        self.advance(4)
        try:
            self.consume_basic_table("concentration", "mass_fraction", "molality")
        except EleanorKernelException:
            self.consume_basic_table("log_activity")

    def _build_point(self) -> es.Point:
        custom_properties: dict[str, object] = {
            "mole_fraction_water": self._mole_fraction_water,
            "log_gamma_water": self._log_activity_coefficient_water,
            "pe": self._pe,
            "Ah": self._Ah,
            "log_stoichiometric_ionic_strength": self._log_stoichiometric_ionic_strength,
            "ionic_asymmetry": self._ionic_asymmetry,
            "stoichiometric_ionic_asymmetry": self._stoichiometric_ionic_asymmetry,
            "osmotic_coefficient": self._osmotic_coefficient,
            "stoichiometric_osmotic_coefficient": self._stoichiometric_osmotic_coefficient,
            "log_sum_molalities": self._log_sum_molalities,
            "log_sum_stoichiometric_molalities": self._log_sum_stoichiometric_molalities,
            "charge_imbalance": self._charge_imbalance,
            "solute_fraction": self._solute_fraction,
            "solvent_fraction": self._solvent_fraction,
        }

        if self._pcH is not None:
            custom_properties["pcH"] = self._pcH
        if self._pHCl is not None:
            custom_properties["pHCl"] = self._pHCl
        if self._anions is not None:
            custom_properties["anions"] = self._anions
        if self._cations is not None:
            custom_properties["cations"] = self._cations
        if self._total_charge is not None:
            custom_properties["total_charge"] = self._total_charge
        if self._mean_charge is not None:
            custom_properties["mean_charge"] = self._mean_charge
        if self._solution_volume is not None:
            custom_properties["solution_volume"] = self._solution_volume
        if self._extended_alkalinity is not None:
            custom_properties["extended_alkalinity"] = self._extended_alkalinity

        return es.Point(
            stage="eq3",
            temperature=self._temperature,
            pressure=self._pressure,
            pH=self._pH,
            log_fO2=self._log_fO2,
            log_activity_water=self._log_activity_water,
            Eh=self._Eh,
            log_ionic_strength=self._log_ionic_strength,
            solute_mass=self._solute_mass,
            solvent_mass=self._solvent_mass,
            solution_mass=self._solution_mass,
            tds=self._tds,
            elements=self._elements,
            aqueous_species=self._aqueous_species,
            pure_solids=[_freeze_pure_solid(a) for a in self._pure_solids.values()],
            solid_solutions=[_freeze_solid_solution(a) for a in self._solid_solutions.values()],
            gases=self._gases,
            redox_reactions=self._redox_reactions,
            custom_properties=custom_properties,
        )

    @override
    def parse(self) -> Self:
        try:
            self.consume_to_pattern(r"\s*\* General\s*$")
            self.advance()
            self._temperature = self.read_basic_property("tempc")
            self.advance()
            self._pressure = self.read_basic_property("press")
            self.read_elemental_composition()
            self.read_numerical_composition()
            self.read_sensible_composition()
            self.read_bulk_properties()
            self.read_pH_like()
            self.read_alkalinity()
            self.read_charge_balance()
            self.read_aqueous_solute()
            self.read_redox_reactions()
            self.read_aqueous_saturation_states()
            self.read_pure_solid_saturation_states()
            self.read_liquid_saturation_states()
            self.read_solid_solution_saturation_states()
            self.read_product_phases("Saturation States of Hypothetical Solid Solutions")
            self.read_fugacities()
        except Exception as e:
            raise EleanorKernelException(
                f"failed to parse EQ3 output at line {self.line_num}",
                code=RunCode.PARSER_ERROR,
            ) from e
        if "Normal exit" not in self.lines[-1]:
            raise EleanorKernelException("eq3 terminated early", code=RunCode.EQ3_EARLY_TERMINATION)
        self.point = self._build_point()
        return self


@final
class OutputParser6(OutputParser):
    path: list[es.Point]
    _xi: np.float64
    _log_xi: np.float64
    _expected_charge_imbalance: np.float64 | None
    _charge_discrepancy: np.float64 | None
    _sigma: np.float64 | None

    def __init__(self, file: StrPath | io.TextIOBase | None = None) -> None:
        self.path = []
        if file is None:
            file = Path("problem.6o")
        try:
            if isinstance(file, (str, Path)):
                with Path(file).open("r") as handle:
                    super().__init__(handle)
            else:
                super().__init__(file)
        except FileNotFoundError as e:
            raise EleanorKernelException("failed to open 6o file", code=RunCode.NO_6O_FILE) from e
        self._reset_step_accumulators()

    def _reset_step_accumulators(self) -> None:
        self._reset_common_accumulators()
        self._xi = np.float64(0.0)
        self._log_xi = np.float64(0.0)
        self._expected_charge_imbalance = None
        self._charge_discrepancy = None
        self._sigma = None

    @override
    def read_elemental_composition(self) -> None:
        self.consume_to_header("Elemental Composition of the Aqueous Solution")
        self.advance(n=2)
        if self.match_pattern(r"\s*Element\s+mg/kg\.sol\s+Molality\s*"):
            self.advance(n=2)
            table = self.read_basic_table("mass_fraction", "molality")
        elif self.match_pattern(r"\s*Element\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*"):
            self.advance(n=2)
            table = self.read_basic_table("mass_per_volume", "mass_fraction", "molarity", "molality")
        else:
            raise EleanorKernelException("expected a table header", code=RunCode.PARSER_ERROR)
        elements: list[es.Element] = []
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            for name, props in table.items():
                elements.append(
                    es.Element(
                        name=name,
                        log_molality=_safe_log10(props["molality"]),
                        mass_fraction=props["mass_fraction"] * np.float64(1e-6),
                    ),
                )
        self._elements = elements

    @override
    def read_numerical_composition(self) -> None:
        self.consume_to_header("Numerical Composition of the Aqueous Solution")
        self.advance(n=2)
        if self.match_pattern(r"\s*Species\s+mg/kg\.sol\s+Molality\s*"):
            self.advance(n=2)
            self.consume_basic_table("mass_fraction", "molality")
        elif self.match_pattern(r"\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*"):
            self.advance(n=2)
            self.consume_basic_table("mass_per_volume", "mass_fraction", "molarity", "molality")
        else:
            raise EleanorKernelException("expected a table header", code=RunCode.PARSER_ERROR)

    @override
    def read_sensible_composition(self) -> None:
        self.consume_to_header("Sensible Composition of the Aqueous Solution")
        self.advance(n=2)
        if self.match_pattern(r"\s*Species\s+mg/kg\.sol\s+Molality\s*"):
            self.advance(n=2)
            self.consume_basic_table("mass_fraction", "molality")
        elif self.match_pattern(r"\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*"):
            self.advance(n=2)
            self.consume_basic_table("mass_per_volume", "mass_fraction", "molarity", "molality")
        else:
            raise EleanorKernelException("expected a table header", code=RunCode.PARSER_ERROR)

    @override
    def read_bulk_properties(self) -> None:
        self._fO2, self._log_fO2 = self.read_log_property("Oxygen fugacity", units=["bars", "bar"])
        self._activity_water, self._log_activity_water = self.read_log_property("Activity of water")
        self._mole_fraction_water, self._log_mole_fraction_water = self.read_log_property("Mole fraction of water")
        self._activity_coefficient_water, self._log_activity_coefficient_water = self.read_log_property(
            "Activity coefficient of water",
        )
        self.consume_to_pattern(r"\s*Osmotic coefficient")
        self._osmotic_coefficient = self.read_basic_property("Osmotic coefficient")
        self._stoichiometric_osmotic_coefficient = self.read_basic_property("Stoichiometric osmotic coefficient")
        self.consume_to_pattern(r"\s*Sum of molalities")
        self._sum_molalities = self.read_basic_property("Sum of molalities")
        self._sum_stoichiometric_molalities = self.read_basic_property("Sum of stoichiometric molalities")
        self.consume_to_pattern(r"\s*Ionic strength \(I\)")
        self._ionic_strength = self.read_basic_property("Ionic strength (I)", units=["molal"])
        self._stoichiometric_ionic_strength = self.read_basic_property("Stoichiometric ionic strength", units=["molal"])
        self.consume_to_pattern(r"\s*Ionic asymmetry \(J\)")
        self._ionic_asymmetry = self.read_basic_property("Ionic asymmetry (J)", units=["molal"])
        self._stoichiometric_ionic_asymmetry = self.read_basic_property(
            "Stoichiometric ionic asymmetry",
            units=["molal"],
        )
        self.consume_to_pattern(r"\s*Solvent mass")
        self._solvent_mass = self.read_basic_property("Solvent mass", units=["grams", "gram", "g"])
        self._solute_mass = self.read_basic_property("Solutes (TDS) mass", units=["grams", "gram", "g"])
        self._solution_mass = self.read_basic_property("Aqueous solution mass", units=["grams", "gram", "g"])
        self.consume_to_pattern(r"\s*Solvent fraction")
        self._solvent_fraction = self.read_basic_property("Solvent fraction", units=["kg.h2o/kg.sol"])
        self._solute_fraction = self.read_basic_property("Solute fraction", units=["kg.tds/kg.sol"])
        self.consume_to_pattern(r"\s*Total dissolved solutes \(TDS\)")
        self._tds = self.read_basic_property("Total dissolved solutes (TDS)", units=["mg/kg.sol"])
        self.consume_to_header("More Precise Aqueous Phase Masses")
        self.advance(n=2)
        self._solvent_mass = self.read_basic_property("Solvent mass", units=["grams", "gram", "g"])
        self._solute_mass = self.read_basic_property("Solutes (TDS) mass", units=["grams", "gram", "g"])
        self._solution_mass = self.read_basic_property("Aqueous solution mass", units=["grams", "gram", "g"])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            self._log_ionic_strength = _safe_log10(self._ionic_strength)
            self._log_stoichiometric_ionic_strength = _safe_log10(self._stoichiometric_ionic_strength)
            self._log_sum_molalities = _safe_log10(self._sum_molalities)
            self._log_sum_stoichiometric_molalities = _safe_log10(self._sum_stoichiometric_molalities)
        self.read_alkalinity()

    @override
    def include_aqueous_species(self, name: str) -> bool:
        return name != "O2(g)"

    @override
    def read_charge_balance(self) -> None:
        self.consume_to_header("Aqueous Solution Charge Balance")
        self.advance(n=2)
        self._charge_imbalance = self.read_basic_property("Actual Charge imbalance", units=["eq"])
        self._expected_charge_imbalance = self.read_basic_property("Expected Charge imbalance", units=["eq"])
        self._charge_discrepancy = self.read_basic_property("Charge discrepancy", units=["eq"])
        self._sigma = self.read_basic_property("Sigma |equivalents|", units=["eq"])
        self.advance()
        _ = self.read_basic_property("Actual Charge imbalance", units=["eq/kg.solu"])
        _ = self.read_basic_property("Expected Charge imbalance", units=["eq/kg.solu"])
        _ = self.read_basic_property("Charge discrepancy", units=["eq/kg.solu"])
        _ = self.read_basic_property("Sigma |equivalents|", units=["eq/kg.solu"])
        self.advance()
        _ = self.read_basic_property("Relative charge discrepancy")

    def _build_point(self) -> es.Point:
        custom_properties: dict[str, object] = {
            "pe": self._pe,
            "Ah": self._Ah,
            "mole_fraction_water": self._mole_fraction_water,
            "log_gamma_water": self._log_activity_coefficient_water,
            "osmotic_coefficient": self._osmotic_coefficient,
            "stoichiometric_osmotic_coefficient": self._stoichiometric_osmotic_coefficient,
            "log_sum_molalities": self._log_sum_molalities,
            "log_sum_stoichiometric_molalities": self._log_sum_stoichiometric_molalities,
            "log_stoichiometric_ionic_strength": self._log_stoichiometric_ionic_strength,
            "ionic_asymmetry": self._ionic_asymmetry,
            "stoichiometric_ionic_asymmetry": self._stoichiometric_ionic_asymmetry,
            "solute_fraction": self._solute_fraction,
            "solvent_fraction": self._solvent_fraction,
            "charge_imbalance": self._charge_imbalance,
            "solid_mass_created": self._solid_mass_created,
            "solid_mass_destroyed": self._solid_mass_destroyed,
            "solid_mass_change": self._solid_mass_change,
            "solid_volume_created": self._solid_volume_created,
            "solid_volume_destroyed": self._solid_volume_destroyed,
            "solid_volume_change": self._solid_volume_change,
        }

        if self._pHCl is not None:
            custom_properties["pHCl"] = self._pHCl
        if self._expected_charge_imbalance is not None:
            custom_properties["expected_charge_imbalance"] = self._expected_charge_imbalance
        if self._charge_discrepancy is not None:
            custom_properties["charge_discrepancy"] = self._charge_discrepancy
        if self._sigma is not None:
            custom_properties["sigma"] = self._sigma
        if self._extended_alkalinity is not None:
            custom_properties["extended_alkalinity"] = self._extended_alkalinity
        if self._overall_affinity is not None:
            custom_properties["overall_affinity"] = self._overall_affinity

        return es.Point(
            stage="eq6",
            log_xi=self._log_xi,
            temperature=self._temperature,
            pressure=self._pressure,
            pH=self._pH,
            Eh=self._Eh,
            log_fO2=self._log_fO2,
            log_activity_water=self._log_activity_water,
            log_ionic_strength=self._log_ionic_strength,
            solute_mass=self._solute_mass,
            solvent_mass=self._solvent_mass,
            solution_mass=self._solution_mass,
            tds=self._tds,
            reactant_mass_reacted=self._reactant_mass_reacted,
            reactant_mass_remaining=self._reactant_mass_remaining,
            elements=self._elements,
            aqueous_species=self._aqueous_species,
            pure_solids=[_freeze_pure_solid(a) for a in self._pure_solids.values()],
            solid_solutions=[_freeze_solid_solution(a) for a in self._solid_solutions.values()],
            gases=self._gases,
            reactants=self._reactants,
            redox_reactions=self._redox_reactions,
            custom_properties=custom_properties,
        )

    def parse_step(self) -> Self:
        try:
            self.consume_blank_lines()
            self._xi = self.read_basic_property("Xi")
            self.advance()
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                self._log_xi = _safe_log10(self._xi)
            self.consume_blank_lines()
            self._temperature = self.read_basic_property("Temperature", units=["celsius", "c"])
            self.consume_blank_lines()
            self._pressure = self.read_basic_property("Pressure", units=["bars", "bar"])
            self.read_reactants()
            self.read_elemental_composition()
            self.read_numerical_composition()
            self.read_sensible_composition()
            self.read_pH_like()
            self.read_bulk_properties()
            self.read_charge_balance()
            self.read_aqueous_solute()
            self.read_redox_reactions()
            self.read_solid_phases()
            self.read_aqueous_saturation_states()
            self.read_pure_solid_saturation_states()
            self.read_liquid_saturation_states()
            self.read_solid_solution_saturation_states()
            self.read_product_phases("Solid Solution Product Phases")
            self.read_fugacities()
        except Exception as e:
            raise EleanorKernelException(
                f"failed to parse EQ6 output at line {self.line_num}",
                code=RunCode.PARSER_ERROR,
            ) from e
        self.path.append(self._build_point())
        self._reset_step_accumulators()
        return self

    def check_path_termination(self) -> None:
        pattern = re.compile(r"^\s*---\s+The reaction path has terminated (early|normally)\s+---\s*$")
        self.unconsume_to_pattern(pattern)
        if self.eof():
            raise EleanorKernelException("no reaction path termination status found", code=RunCode.EQ6_ERROR)

        match = pattern.match(self.line())
        if match is None:
            raise EleanorKernelException("no reaction path termination status found", code=RunCode.EQ6_ERROR)
        if match[1] != "normally":
            raise EleanorKernelException("eq6 reaction path terminated early", code=RunCode.EQ6_EARLY_TERMINATION)

    @override
    def parse(self) -> Self:
        while self.advance_to_xi_step():
            _ = self.parse_step()
        self.check_path_termination()
        return self


_ = OutputParser.register(OutputParser3)
_ = OutputParser.register(OutputParser6)
