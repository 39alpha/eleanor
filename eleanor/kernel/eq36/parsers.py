import io
import re
import sys
import warnings
from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np

from eleanor.exceptions import EleanorException, EleanorFileException, EleanorParserException
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.util import field_as_float

path_separator = re.compile('^( -)+$')
blank_line = re.compile(r'^\s*$')


class OutputParser(ABC):
    line_num: int
    lines: list[str]
    data: dict[str, Any]

    def __init__(self, file: io.TextIOWrapper):
        self.line_num = 0
        self.lines = file.readlines()
        self.data = {}

    def eof(self) -> bool:
        return 0 > self.line_num or self.line_num >= len(self.lines)

    def retreat(self, n: int = 1):
        self.line_num -= n

    def advance(self, n: int = 1):
        self.line_num += n

    def line(self) -> str:
        return self.lines[self.line_num]

    def peek(self) -> str:
        return self.lines[self.line_num + 1]

    def is_blank(self):
        return blank_line.match(self.line())

    def unconsume_to_pattern(self, pattern: str | re.Pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        while self.eof():
            self.retreat()

        while not self.eof() and not pattern.match(self.line()):
            self.retreat()

    def consume_to_pattern(self, pattern: str | re.Pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        while not self.eof() and not pattern.match(self.line()):
            self.advance()

    def consume_while_pattern(self, pattern: str | re.Pattern):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        while not self.eof() and pattern.match(self.line()):
            self.advance()

    def consume_blank_lines(self):
        self.consume_while_pattern(blank_line)

    def consume_to_header(self, header):
        self.consume_to_pattern(rf'^\s*---\s+{header}\s+---\s*$')

    def advance_to_xi_step(self):
        self.consume_to_pattern(r'\s*Stepping to Xi')

        if self.eof():
            return False

        while not self.eof():
            if path_separator.match(self.line()):
                self.advance()
                break
            self.advance()

        return True

    def read_key_value(self) -> tuple[str, float]:
        key, value = self.line().strip().split('=')
        return key, field_as_float(value)

    def read_key_value_unit(self) -> tuple[str, float, str]:
        key, value = self.line().strip().split('=')
        value, unit = value.strip().split()
        return key, field_as_float(value), unit

    def read_basic_property(self,
                            name: str,
                            units: Optional[list[str]] = None,
                            advance: bool = True,
                            data: Optional[dict[str, Any]] = None,
                            key: Optional[str] = None):
        line = self.line().strip()
        if not line.startswith(f'{name}='):
            raise EleanorParserException(f'expected {name} entry')

        if units is None or len(units) == 0:
            default_key, value = self.read_key_value()
        else:
            default_key, value, unit = self.read_key_value_unit()
            if unit.lower() not in units:
                raise EleanorParserException(f'expected {name} in {units[0]}')

        if data is None:
            data = self.data

        if key is None:
            data[default_key] = value
        else:
            data[key] = value

        if advance:
            self.advance()

    def read_log_property(self, name, key=None, units=None):
        log_name = 'Log ' + name.lower()
        log_key = 'log_' + key
        self.consume_to_pattern(rf'\s*{name}')
        self.read_basic_property(name, key=key, units=units)
        self.read_basic_property(log_name, key=log_key)

    def read_reactants(self):
        summary: dict[str, Any] = {}

        self.consume_to_header('Reactant Summary')
        self.consume_to_pattern(r'^\s+Reactant\s+Moles\s+Delta moles\s+Mass, g\s+Delta mass, g\s*$')

        self.advance()
        self.consume_blank_lines()

        if self.line().strip() == 'None':
            return

        reactants: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            name, moles, delta_moles, mass, delta_mass = self.line().strip().split()
            reactants[name] = {
                'moles_remaining': field_as_float(moles),
                'moles_reacted': field_as_float(delta_moles),
                'mass_remaining': field_as_float(mass),
                'mass_reacted': field_as_float(delta_mass),
            }
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                for key, value in list(reactants[name].items()):
                    reactants[name][f'log_{key}'] = float(np.log10(value))

            self.advance()

        self.consume_blank_lines()

        self.read_basic_property('Mass remaining', key="mass_remaining", units=['grams', 'gram', 'g'], data=summary)
        self.read_basic_property('Mass destroyed', key="mass_reacted", units=['grams', 'gram', 'g'], data=summary)

        self.consume_to_pattern(r'^\s+Reactant\s+Affinity\s+Rel\. Rate\s*$')

        self.advance(n=3)

        while not self.eof() and not self.is_blank():
            name, affinity, relative_rate = self.line().strip().split()
            if name not in reactants:
                raise EleanorParserException(f'found affinity for unexpected reactant at line {self.line_num}')

            reactants[name].update({
                'affinity': field_as_float(affinity),
                'relative_rate': field_as_float(relative_rate),
            })

            self.advance()

        self.consume_blank_lines()

        self.read_basic_property('Affinity of the overall irreversible reaction',
                                 key='overall_affinity',
                                 units=['kcal', 'kcal.'],
                                 data=summary)

        self.consume_blank_lines()

        summary['reactants'] = reactants
        self.data['reactants'] = summary

    def read_basic_table(self, *column_names, row_names=None, **kwargs):
        table: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            name, *columns = self.line().strip().split()
            if row_names is not None:
                name = row_names[len(table)]

            if len(column_names) != len(columns):
                raise EleanorParserException(
                    f'expected {len(column_names)} columns, got {len(columns)} at line {self.line_num}')

            table[name] = dict(zip(
                column_names,
                map(field_as_float, columns),
            ))
            self.advance()

        return table

    @abstractmethod
    def read_elemental_composition(self):
        pass

    @abstractmethod
    def read_numerical_composition(self):
        pass

    @abstractmethod
    def read_sensible_composition(self):
        pass

    def read_pH_like(self):
        self.consume_to_header('The pH, Eh, pe-, and Ah on various pH scales')
        self.advance(n=4)

        scales: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            *scale, ph, eh, pe, ah = self.line().strip().split()
            scales[' '.join(scale)] = {
                'pH': field_as_float(ph),
                'Eh': field_as_float(eh),
                'pe-': field_as_float(pe),
                'Ah': field_as_float(ah),
            }
            self.advance()

        self.data['pH'] = scales

        self.consume_blank_lines()

        try:
            self.read_basic_property('pcH')
        except Exception:
            pass

        try:
            self.read_basic_property('pHCl')
        except Exception:
            pass

    @abstractmethod
    def read_bulk_properties(self):
        pass

    @abstractmethod
    def read_charge_balance(self):
        pass

    def read_alkalinity(self):

        self.consume_to_pattern(r'^.*Alkalinity.*$')
        if 'is not defined' in self.line():
            return

        self.data['alkalinity'] = {}

        pattern = re.compile(r'^\s*---\s+(.*) Total Alkalinity\s+--')
        found_extended = False
        while not found_extended:
            self.consume_to_pattern(pattern)
            m = pattern.match(self.line())
            if m is None:
                raise EleanorParserException(f'unexpected state in OutputParser at line {self.line_num}')

            alkalinity_kind = m[1]
            found_extended = alkalinity_kind == 'Extended'

            self.advance(2)
            alkalinity, units = self.line().strip().split()
            self.data['alkalinity'][alkalinity_kind] = {'Total': field_as_float(alkalinity)}
            self.advance()

            while not self.eof() and not self.is_blank():
                try:
                    alkalinity, units, species = self.line().strip().split()
                except ValueError:
                    self.advance()
                    continue

                if 'L' not in units:
                    self.data['alkalinity'][alkalinity_kind][species] = field_as_float(alkalinity)

                self.advance()

    def read_aqueous_solute(self):
        self.consume_to_header('Distribution of Aqueous Solute Species')
        self.consume_to_pattern(r'\s*Species\s+Molality\s+Log Molality\s+Log Gamma\s+Log Activity\s*')
        self.advance(n=2)

        aqueous: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            species, molality, log_molality, log_gamma, log_activity = self.line().strip().split()
            aqueous[species] = {
                'molality': field_as_float(molality),
                'log_molality': field_as_float(log_molality),
                'log_gamma': field_as_float(log_gamma),
                'log_activity': field_as_float(log_activity),
            }
            self.advance()

        self.data['aqueous'] = aqueous

    def read_redox_reactions(self):
        self.consume_to_header('Aqueous Redox Reactions')
        self.consume_to_pattern(r'\s*Couple\s+Eh, volts\s+pe-\s+log fO2\s+Ah, kcal\s*')
        self.advance(n=2)

        redox: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            couple, eh, pe, log_fO2, ah = self.line().strip().split()
            redox[couple] = {
                'Eh': field_as_float(eh),
                'pe-': field_as_float(pe),
                'log_fO2': field_as_float(log_fO2),
                'Ah': field_as_float(ah),
            }
            self.advance()

        self.data['redox'] = redox

    def read_solid_blocks(self, pure_solids, solid_solutions):

        def is_end_member(s):
            return s.startswith('   ')

        parent_phase: str | None = None
        while not self.eof() and not self.is_blank():
            line, next_line = self.line(), self.peek()
            solid, log_moles, moles, mass, volume = self.line().strip().split()
            if is_end_member(line):
                if parent_phase is None:
                    raise EleanorParserException('unexpected end member')

                # This line is an end member
                datum: dict[str, Any] = {
                    'moles': field_as_float(moles),
                    'log_moles': field_as_float(log_moles),
                    'mass': field_as_float(mass),
                    'volume': field_as_float(volume),
                }

                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=RuntimeWarning)
                    datum['log_mass'] = float(np.log10(datum['mass']))
                    datum['log_volume'] = float(np.log10(datum['volume']))

                solid_solutions[parent_phase]['end_members'][solid] = datum
            elif is_end_member(next_line) and not blank_line.match(next_line):
                # This line is a solid solution
                parent_phase = solid

                datum = {
                    'moles': field_as_float(moles),
                    'log_moles': field_as_float(log_moles),
                    'mass': field_as_float(mass),
                    'volume': field_as_float(volume),
                    'end_members': {},
                }

                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=RuntimeWarning)
                    datum['log_mass'] = float(np.log10(datum['mass']))
                    datum['log_volume'] = float(np.log10(datum['volume']))

                solid_solutions[solid] = datum
            else:
                # This line is a pure_phase
                datum = {
                    'moles': field_as_float(moles),
                    'log_moles': field_as_float(log_moles),
                    'mass': field_as_float(mass),
                    'volume': field_as_float(volume),
                }

                with warnings.catch_warnings():
                    warnings.filterwarnings('ignore', category=RuntimeWarning)
                    datum['log_mass'] = float(np.log10(datum['mass']))
                    datum['log_volume'] = float(np.log10(datum['volume']))

                pure_solids[solid] = datum

                parent_phase = None

            if blank_line.match(next_line):
                self.advance(n=2)
            else:
                self.advance(n=1)

    def read_solid_phases(self):
        solids: dict[str, Any] = {}
        self.consume_to_header(r'Summary of Solid Phases \(ES\)')
        self.consume_to_pattern(r'\s*Phase/End-member\s+Log moles\s+Moles\s+Grams\s+Volume, cm3\s*')
        self.advance(n=2)

        pure_solids: dict[str, Any] = {}
        solid_solutions: dict[str, Any] = {}
        while not self.eof() and 'None' not in self.line() and not self.is_blank():
            self.read_solid_blocks(pure_solids, solid_solutions)

        self.consume_to_header(r'Grand Summary of Solid Phases \(ES \+ PRS \+ Reactants\)')
        self.consume_to_pattern(r'\s*Phase/End-member\s+Log moles\s+Moles\s+Grams\s+Volume, cm3\s*')
        self.advance(n=2)

        while not self.eof() and 'None' not in self.line() and not self.is_blank():
            self.read_solid_blocks(pure_solids, solid_solutions)

        self.advance(n=3)
        solids.update(self.read_basic_table('mass', 'volume', row_names=['created', 'destroyed', 'net']))

        solids['pure_solids'] = pure_solids
        solids['solid_solutions'] = solid_solutions
        self.data['solids'] = solids

    def read_aqueous_saturation_states(self):
        self.consume_to_header('Saturation States of Aqueous Reactions Not Fixed at Equilibrium')
        self.consume_to_pattern(r'\s*Reaction\s+Log Q/K\s+Affinity, kcal\s*')
        self.advance(n=2)

        while not self.eof() and not self.is_blank():
            # TODO: Handle this section
            self.advance()

    def read_saturation_states(self, header, phases):
        self.consume_to_header(header)
        self.consume_to_pattern(r'\s*Phase\s+Log Q/K\s+Affinity, kcal\s*')
        self.advance(n=2)

        while not self.eof() and not self.is_blank():
            if self.line().strip() == 'None':
                break

            phase, log_qk, affinity, *rest = self.line().strip().split()
            if len(rest) > 1:
                raise EleanorParserException(f'too many columns in {header} at line {self.line_num}')
            elif len(rest) != 0 and rest[0] not in ['SATD', 'SSATD']:
                raise EleanorParserException(f'unexpected value in State column of {header} at line {self.line_num}')

            if '*' in log_qk or '*' in affinity:
                self.advance()
                continue

            if phase in phases:
                phases[phase]['log_qk'] = field_as_float(log_qk)
                phases[phase]['affinity'] = field_as_float(affinity)
            else:
                phases[phase] = {
                    'log_qk': field_as_float(log_qk),
                    'affinity': field_as_float(affinity),
                }

            self.advance()

    def read_pure_solid_saturation_states(self):
        if 'solids' not in self.data:
            self.data['solids'] = {}

        if 'pure_solids' not in self.data['solids']:
            self.data['solids']['pure_solids'] = {}

        self.read_saturation_states('Saturation States of Pure Solids', self.data['solids']['pure_solids'])

    def read_liquid_saturation_states(self):
        self.consume_to_header('Saturation States of Pure Liquids')
        self.consume_to_pattern(r'\s*Phase\s+Log Q/K\s+Affinity, kcal\s*')
        self.advance(n=2)

        liquids: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            phase, log_qk, affinity, *rest = self.line().strip().split()
            if len(rest) > 1:
                raise EleanorParserException(
                    f'too many columns in Saturation States of Pure Liquids at line {self.line_num}')
            elif len(rest) != 0 and rest[0] not in ['SATD', 'SSATD']:
                raise EleanorParserException(
                    f'unexpected value in State column of Saturation States of Pure Liquids block at line {self.line_num}'
                )

            if '*' in log_qk or '*' in affinity:
                self.advance()
                continue

            liquids[phase] = {
                'log_qk': field_as_float(log_qk),
                'affinity': field_as_float(affinity),
            }
            self.advance()

        self.data['liquids'] = liquids

    def read_solid_solution_saturation_states(self):
        if 'solids' not in self.data:
            self.data['solids'] = {}

        if 'solid_solutions' not in self.data['solids']:
            self.data['solids']['solid_solutions'] = {}

        self.read_saturation_states('Saturation States of Solid Solutions', self.data['solids']['solid_solutions'])

    def read_end_members(self, end_members):
        self.consume_to_pattern(r'^\s*Component\s+x\s+Log x\s+ Log lambda\s+Log activity\s*$')
        self.advance(n=2)
        while not self.eof() and not self.is_blank():
            end_member, x, log_x, log_lambda, log_activity = self.line().strip().split()
            props = {
                'x': field_as_float(x),
                'log_x': field_as_float(log_x),
                'log_lambda': field_as_float(log_lambda),
                'log_activity': field_as_float(log_activity),
            }

            if end_member not in end_members:
                end_members[end_member] = props
            else:
                end_members[end_member].update(props)
            self.advance()

    def read_mineral(self, header, phases, expected_phase: Optional[str] = None):
        self.consume_to_pattern(r'^\s*Mineral\s+Log Q/K\s+Aff, kcal\s+State\s*$')
        self.advance(n=2)
        mineral, log_qk, affinity, *state = self.line().strip().split()
        assert expected_phase is None or expected_phase == mineral
        if len(state) > 1:
            raise EleanorParserException(f'too many columns in {header} at {self.line_num}')
        elif len(state) != 0 and state[0] not in ['SATD', 'SSATD']:
            raise EleanorParserException(f'unexpected columns in {header} at line {self.line_num}')

        phases[mineral].update({
            'log_qk': field_as_float(log_qk),
            'affinity': field_as_float(affinity),
        })
        self.advance()

    def read_end_member_saturations(self, header, end_members):
        while not self.eof() and not self.is_blank():
            end_member, log_qk, affinity, *state = self.line().strip().split()
            if len(state) > 1:
                raise EleanorParserException(f'too many columns in {header} at {self.line_num}')
            elif len(state) != 0 and state[0] not in ['SATD', 'SSATD']:
                raise EleanorParserException(
                    f'unexpected value in State column of {header} block at line {self.line_num}')

            end_members[end_member].update({
                'log_qk': field_as_float(log_qk),
                'affinity': field_as_float(affinity),
            })
            self.advance()

    def read_product_phases(self, header):
        self.consume_to_header(header)
        self.advance(n=2)

        if 'solids' not in self.data:
            self.data['solids'] = {}

        if 'solid_solutions' not in self.data['solids']:
            self.data['solids']['solid_solutions'] = {}

        solid_solutions = self.data['solids']['solid_solutions']
        while not self.eof():
            match = re.match(r'^\s+---\s(.*)\s---\s*$', self.line())
            if match and match[1] == 'Fugacities':
                self.line_num -= 1
                break
            elif match:
                phase = match[1]

                if phase not in solid_solutions:
                    solid_solutions[phase] = {'end_members': {}}
                elif 'end_members' not in solid_solutions[phase]:
                    solid_solutions[phase]['end_members'] = {}

                end_members = solid_solutions[phase]['end_members']

                self.read_end_members(end_members)
                self.read_mineral(header, solid_solutions, phase)
                self.read_end_member_saturations(header, end_members)

            self.advance()

    def read_fugacities(self):
        self.consume_to_header('Fugacities')
        self.consume_to_pattern(r'\s*Gas\s+Log Fugacity\s+Fugacity\s*')
        self.advance(n=2)

        gases: dict[str, Any] = {}
        while not self.eof() and not self.is_blank():
            gas, log_fugacity, fugacity = self.line().strip().split()
            if '*' in log_fugacity or '*' in fugacity:
                self.advance()
                continue

            gases[gas] = {
                'fugacity': field_as_float(fugacity),
                'log_fugacity': field_as_float(log_fugacity),
            }
            self.advance()

        self.data['gases'] = gases

    def pretty_print(self, obj):

        def recprint(key, props, indent=0):
            if isinstance(props, dict):
                if indent == 0:
                    print(key)
                else:
                    print(' ' * (indent - 1), key)
                for subkey, subprops in props.items():
                    recprint(subkey, subprops, indent + 4)
            else:
                if indent == 0:
                    print(key, props)
                else:
                    print(' ' * (indent - 1), key, props)

        for key, props in obj.items():
            recprint(key, props)

    @abstractmethod
    def parse(self):
        pass


class OutputParser3(OutputParser):

    def __init__(self, file: Optional[str | io.TextIOWrapper] = None):
        if file is None:
            file = 'problem.3o'

        try:
            if isinstance(file, str):
                with open(file, 'r') as handle:
                    super().__init__(handle)
            else:
                super().__init__(file)
        except FileNotFoundError as e:
            raise EleanorFileException(e, code=RunCode.NO_3O_FILE)

    def read_elemental_composition(self):
        self.consume_to_header('Elemental Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Element\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*')
        self.advance(n=2)

        elements = self.read_basic_table('concentration', 'mass_fraction', 'molarity', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for element, properties in elements.items():
                properties['concentration'] *= 1e-3
                properties['mass_fraction'] *= 1e-6
                properties['log_molarity'] = float(np.log10(properties['molarity']))
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['elements'] = elements

    def read_numerical_composition(self):
        self.consume_to_header('Numerical Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*')
        self.advance(n=2)

        composition = self.read_basic_table('concentration', 'mass_fraction', 'molarity', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for species, properties in composition.items():
                properties['concentration'] *= 1e-3
                properties['mass_fraction'] *= 1e-6
                properties['log_molarity'] = float(np.log10(properties['molarity']))
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['numerical_composition'] = composition

    def read_sensible_composition(self):
        self.consume_to_header('Sensible Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Species\s+mg/L\s+mg/kg\.sol\s+Molarity\s+Molality\s*')
        self.advance(n=2)

        composition = self.read_basic_table('concentration', 'mass_fraction', 'molarity', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for species, properties in composition.items():
                properties['concentration'] *= 1e-3
                properties['mass_fraction'] *= 1e-6
                properties['log_molarity'] = float(np.log10(properties['molarity']))
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['sensible_composition'] = composition

    def read_bulk_properties(self):
        self.read_log_property('Oxygen fugacity', key='fO2', units=['bars', 'bar'])
        self.read_log_property('Activity of water', key='activity_water')
        self.read_log_property('Mole fraction of water', key='mole_fraction_water')
        self.read_log_property('Activity coefficient of water', key='activity_coefficient_water')

        self.consume_to_pattern(r'\s*Osmotic coefficient')
        self.read_basic_property('Osmotic coefficient', key='osmotic_coefficient')
        self.read_basic_property('Stoichiometric osmotic coefficient', key='stoichiometric_osmotic_coefficient')

        self.consume_to_pattern(r'\s*Sum of molalities')
        self.read_basic_property('Sum of molalities', key='sum_molalities')
        self.read_basic_property('Sum of stoichiometric molalities', key='sum_stoichiometric_molalities')

        self.consume_to_pattern(r'\s*Ionic strength \(I\)')
        self.read_basic_property('Ionic strength (I)', key='ionic_strength', units=['molal'])
        self.read_basic_property('Stoichiometric ionic strength', key='stoichiometric_ionic_strength', units=['molal'])

        self.consume_to_pattern(r'\s*Ionic asymmetry \(J\)')
        self.read_basic_property('Ionic asymmetry (J)', key='ionic_asymmetry', units=['molal'])
        self.read_basic_property('Stoichiometric ionic asymmetry',
                                 key='stoichiometric_ionic_asymmetry',
                                 units=['molal'])

        self.consume_to_pattern(r'\s*Solvent mass')
        self.read_basic_property('Solvent mass', key='solvent_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Solutes (TDS) mass', key='solute_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Aqueous solution mass', key='solution_mass', units=['grams', 'gram', 'g'])

        self.consume_to_pattern(r'\s*Aqueous solution volume')
        self.read_basic_property('Aqueous solution volume', key='solution_volume', units=['liters', 'l'])

        self.consume_to_pattern(r'\s*Solvent fraction')
        self.read_basic_property('Solvent fraction', key='solvent_fraction', units=['kg.H2O/kg.sol'.lower()])
        self.read_basic_property('Solute fraction', key='solute_fraction', units=['kg.tds/kg.sol'])

        self.consume_to_pattern(r'\s*Total dissolved solutes \(TDS\)')
        self.read_basic_property('Total dissolved solutes (TDS)', key='tds_mass', units=['mg/kg.sol'])
        self.data['tds_mass'] *= 1e-6

        self.consume_to_pattern(r'\s*Solution density')
        self.read_basic_property('Solution density', key='solution_density', units=['g/ml'])
        self.data['solution_density'] *= 1e3

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for key in [
                    'ionic_strength', 'stoichiometric_ionic_strength', 'ionic_asymmetry',
                    'stoichiometric_ionic_asymmetry', 'sum_molalities', 'sum_stoichiometric_molalities', 'solvent_mass',
                    'solute_mass', 'solution_mass'
            ]:
                self.data[f'log_{key}'] = float(np.log10(self.data[key]))

    def read_charge_balance(self):
        self.consume_to_header('Electrical Balance Totals')

        self.advance(n=4)

        self.read_basic_property('Sigma(mz) cations', key='cations')
        self.read_basic_property('Sigma(mz) anions', key='anions')
        self.read_basic_property('Total charge', key='total_charge')
        self.read_basic_property('Mean charge', key='mean_charge')
        self.read_basic_property('Charge imbalance', key='charge_imbalance')

        self.advance(4)

        percent_total_charge, *rest = self.line().strip().split()
        self.data['charge_imbalance_percent_total'] = field_as_float(percent_total_charge)
        self.advance()

        percent_mean_charge, *rest = self.line().strip().split()
        self.data['charge_imbalance_percent_mean'] = field_as_float(percent_mean_charge)
        self.advance(3)

        m = re.compile(r'^\s*---\s+Electrical Balancing on (.*)\s+---\s*$').match(self.line())
        if m is None:
            raise EleanorParserException(f'expected Electrical Balancing block at {self.line_num}')

        self.advance(4)

        charge_balance = {
            'species': m[1],
        }

        try:
            table = self.read_basic_table('concentration', 'mass_fraction', 'molality')

            for phase, props in table.items():
                props['concentration'] *= 1e-3
                props['mass_fraction'] *= 1e-6

            charge_balance.update(table)
        except EleanorParserException:
            charge_balance.update(self.read_basic_table('log_activity'))

        self.data['charge_balance'] = charge_balance

    def parse(self):
        try:
            self.consume_to_pattern(r'\s*\* General\s*$')
            self.advance()
            self.read_basic_property('tempc', key='temperature')
            self.advance()
            self.read_basic_property('press', key='pressure')

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
            self.read_product_phases('Saturation States of Hypothetical Solid Solutions')
            self.read_fugacities()
        except Exception as e:
            raise EleanorParserException(f'failed to parse EQ3 output at line {self.line_num}', e)

        if 'Normal exit' not in self.lines[-1]:
            raise EleanorException('eq3 terminated early', code=RunCode.EQ3_EARLY_TERMINATION)

        return self


class OutputParser6(OutputParser):
    path: list[dict[str, Any]]

    def __init__(self, file: Optional[str | io.TextIOWrapper] = None):
        self.path = []

        if file is None:
            file = 'problem.6o'

        try:
            if isinstance(file, str):
                with open(file, 'r') as handle:
                    super().__init__(handle)
            else:
                super().__init__(file)
        except FileNotFoundError as e:
            raise EleanorFileException(e, code=RunCode.NO_6O_FILE)

    def read_elemental_composition(self):
        self.consume_to_header('Elemental Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Element\s+mg/kg\.sol\s+Molality\s*')
        self.advance(n=2)

        elements = self.read_basic_table('mass_fraction', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for element, properties in elements.items():
                properties['mass_fraction'] *= 1e-6
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['elements'] = elements

    def read_numerical_composition(self):
        pass
        self.consume_to_header('Numerical Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Species\s+mg/kg\.sol\s+Molality\s*')
        self.advance(n=2)

        composition = self.read_basic_table('mass_fraction', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for species, properties in composition.items():
                properties['mass_fraction'] *= 1e-6
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['numerical_composition'] = composition

    def read_sensible_composition(self):
        self.consume_to_header('Sensible Composition of the Aqueous Solution')
        self.consume_to_pattern(r'\s*Species\s+mg/kg\.sol\s+Molality\s*')
        self.advance(n=2)

        composition = self.read_basic_table('mass_fraction', 'molality')
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for species, properties in composition.items():
                properties['mass_fraction'] *= 1e-6
                properties['log_molality'] = float(np.log10(properties['molality']))
        self.data['sensible_composition'] = composition

    def read_bulk_properties(self):
        self.read_log_property('Oxygen fugacity', key='fO2', units=['bars', 'bar'])
        self.read_log_property('Activity of water', key='activity_water')
        self.read_log_property('Mole fraction of water', key='mole_fraction_water')
        self.read_log_property('Activity coefficient of water', key='activity_coefficient_water')

        self.consume_to_pattern(rf'\s*Osmotic coefficient')
        self.read_basic_property('Osmotic coefficient', key='osmotic_coefficient')
        self.read_basic_property('Stoichiometric osmotic coefficient', key='stoichiometric_osmotic_coefficient')

        self.consume_to_pattern(rf'\s*Sum of molalities')
        self.read_basic_property('Sum of molalities', key='sum_molalities')
        self.read_basic_property('Sum of stoichiometric molalities', key='sum_stoichiometric_molalities')

        self.consume_to_pattern(rf'\s*Ionic strength \(I\)')
        self.read_basic_property('Ionic strength (I)', key='ionic_strength', units=['molal'])
        self.read_basic_property('Stoichiometric ionic strength', key='stoichiometric_ionic_strength', units=['molal'])

        self.consume_to_pattern(rf'\s*Ionic asymmetry \(J\)')
        self.read_basic_property('Ionic asymmetry (J)', key='ionic_asymmetry', units=['molal'])
        self.read_basic_property('Stoichiometric ionic asymmetry',
                                 key='stoichiometric_ionic_asymmetry',
                                 units=['molal'])

        self.consume_to_pattern(rf'\s*Solvent mass')
        self.read_basic_property('Solvent mass', key='solvent_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Solutes (TDS) mass', key='solute_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Aqueous solution mass', key='solution_mass', units=['grams', 'gram', 'g'])

        self.consume_to_pattern(rf'\s*Solvent fraction')
        self.read_basic_property('Solvent fraction', key='solvent_fraction', units=['kg.H2O/kg.sol'.lower()])
        self.read_basic_property('Solute fraction', key='solute_fraction', units=['kg.tds/kg.sol'])

        self.consume_to_pattern(rf'\s*Total dissolved solutes \(TDS\)')
        self.read_basic_property('Total dissolved solutes (TDS)', key='tds_mass', units=['mg/kg.sol'])
        self.data['tds_mass'] *= 1e-6

        self.consume_to_header('More Precise Aqueous Phase Masses')
        self.advance(n=2)

        self.read_basic_property('Solvent mass', key='solvent_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Solutes (TDS) mass', key='solute_mass', units=['grams', 'gram', 'g'])
        self.read_basic_property('Aqueous solution mass', key='solution_mass', units=['grams', 'gram', 'g'])

        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            for key in [
                    'ionic_strength', 'stoichiometric_ionic_strength', 'ionic_asymmetry',
                    'stoichiometric_ionic_asymmetry', 'sum_molalities', 'sum_stoichiometric_molalities', 'solvent_mass',
                    'solute_mass', 'solution_mass'
            ]:
                self.data[f'log_{key}'] = float(np.log10(self.data[key]))

        self.read_alkalinity()

    def read_charge_balance(self):
        self.consume_to_header('Aqueous Solution Charge Balance')

        self.advance(n=2)

        self.read_basic_property('Actual Charge imbalance', key='charge_imbalance', units=['eq'])
        self.read_basic_property('Expected Charge imbalance', key='expected_charge_imbalance', units=['eq'])
        self.read_basic_property('Charge discrepancy', key='charge_discrepancy', units=['eq'])
        self.read_basic_property('Sigma |equivalents|', key='sigma', units=['eq'])

        self.advance()

        self.read_basic_property('Actual Charge imbalance',
                                 key='charge_imbalance_per_unit_solution',
                                 units=['eq/kg.solu'])
        self.data['charge_imbalance_per_unit_solution'] *= 1e-3
        self.read_basic_property('Expected Charge imbalance',
                                 key='expected_charge_imbalance_per_unit_solution',
                                 units=['eq/kg.solu'])
        self.data['expected_charge_imbalance_per_unit_solution'] *= 1e-3
        self.read_basic_property('Charge discrepancy', key='charge_discrepency_per_unit_solution', units=['eq/kg.solu'])
        self.data['charge_discrepency_per_unit_solution'] *= 1e-3
        self.read_basic_property('Sigma |equivalents|', key='sigma_per_unit_solution', units=['eq/kg.solu'])
        self.data['sigma_per_unit_solution'] *= 1e-3

        self.advance()

        self.read_basic_property('Relative charge discrepancy', key='relative_charge_discrepency')

    def parse_step(self):
        try:
            self.consume_blank_lines()
            self.read_basic_property('Xi', key="xi")
            self.advance()
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                self.data['log_xi'] = float(np.log10(self.data['xi']))
            self.consume_blank_lines()
            self.read_basic_property('Temperature', key='temperature', units=['celcius', 'c'])
            self.consume_blank_lines()
            self.read_basic_property('Pressure', key='pressure', units=['bars', 'bar'])
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
            self.read_product_phases('Solid Solution Product Phases')
            self.read_fugacities()
        except Exception as e:
            raise EleanorParserException(f'failed to parse EQ6 output at line {self.line_num}', e)

        self.path.append(self.data)
        self.data = {}

        return self

    def check_path_termination(self):
        pattern = re.compile(r'^\s*---\s+The reaction path has terminated (early|normally)\s+---\s*$')
        self.unconsume_to_pattern(pattern)
        if self.eof():
            raise EleanorException('no reaction path termination status found', code=RunCode.EQ6_ERROR)
        else:
            match = pattern.match(self.line())
            if match is None:
                raise EleanorException('no reaction path termination status found', code=RunCode.EQ6_ERROR)
            elif match[1] == 'normally':
                pass
            elif match[1] == 'early':
                raise EleanorException('eq6 reaction path terminated early', code=RunCode.EQ6_EARLY_TERMINATION)
            else:
                raise EleanorException('eq6 reaction path terminated early', code=RunCode.EQ6_EARLY_TERMINATION)

    def parse(self):
        while self.advance_to_xi_step():
            self.parse_step()

        self.check_path_termination()

        return self


OutputParser.register(OutputParser3)
OutputParser.register(OutputParser6)
