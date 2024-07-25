import datetime
import hashlib
import json
import tomllib
from dataclasses import dataclass

import yaml

from ..exceptions import EleanorParserException
from ..hanger.tool_room import parse_date
from ..kernel.config import Config as KernelConfig
from ..typing import Any, Callable, Optional
from .constraints import ConstraintConfig
from .parameter import Parameter
from .reactant import AbstractReactant, Reactant
from .suppression import Suppression


@dataclass
class Config(object):
    name: str
    date: datetime.date | datetime.datetime
    notes: str
    creator: str
    kernel: KernelConfig
    temperature: Parameter
    pressure: Parameter
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]
    reactants: list[Reactant]
    constraints: list[ConstraintConfig]
    raw: dict[str, Any]

    def parameters(self) -> list[Parameter]:
        parameters: list[Parameter] = [self.temperature, self.pressure]
        parameters.extend(self.kernel.parameters())
        parameters.extend(e for e in self.elements.values())
        parameters.extend(s for s in self.species.values())
        for reactant in self.reactants:
            parameters.extend(reactant.parameters())

        return parameters

    def hash(self) -> str:
        hasher = hashlib.sha256()
        content: bytes = bytes(json.dumps(self.raw, sort_keys=True, default=str), 'utf-8')
        hasher.update(content)

        return hasher.hexdigest()

    @staticmethod
    def from_dict(raw: dict):
        name = raw['name']
        if not isinstance(name, str):
            raise EleanorParserException('name must be a string')

        config_date = raw['date']
        if isinstance(config_date, str):
            config_date = parse_date(config_date)

        if not isinstance(config_date, (datetime.date, datetime.datetime)):
            raise EleanorParserException('date must be a date or datetime')

        notes = raw.get('notes', '')
        if not isinstance(notes, str):
            raise EleanorParserException('notes must be a string')

        creator = raw['creator']
        if not isinstance(creator, str):
            raise EleanorParserException('creator must be a string')

        kernel_type = raw['kernel']['type'].lower()
        if kernel_type == 'eq36':
            # DGM: Ideally this would be done via some type of registration
            from eleanor.kernel.eq36 import Config as Eq36KernelConfig
            kernel = Eq36KernelConfig.from_dict(raw['kernel'])
        else:
            raise EleanorParserException(f'unsupported kernel type "{kernel_type}"')

        temperature = Parameter.from_dict(raw['temperature'], 'temperature')
        pressure = Parameter.from_dict(raw['pressure'], 'pressure')
        elements = {name: Parameter.from_dict(value, name=name) for name, value in raw['elements'].items()}
        species = {name: Parameter.from_dict(value, name=name) for name, value in raw['species'].items()}
        suppressions = [
            Suppression.from_dict({}, name=value) if isinstance(value, str) else Suppression.from_dict(value)
            for value in raw.get('suppressions', [])
        ]

        reactants = [AbstractReactant.from_dict(value, name=name) for name, value in raw.get('reactants', []).items()]

        constraints: list[ConstraintConfig] = []

        return Config(
            name,
            config_date,
            notes,
            creator,
            kernel,
            temperature,
            pressure,
            elements,
            species,
            suppressions,
            reactants,
            constraints,
            raw=raw,
        )

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, 'rb') as handle:
            raw = yaml.safe_load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_toml(fname: str):
        with open(fname, 'rb') as handle:
            raw = tomllib.load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_json(fname: str):
        with open(fname, 'rb') as handle:
            raw = json.load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_file(fname: str):
        parsers: dict[str, Callable[[str], Config]] = {
            'yaml': Config.from_yaml,
            'toml': Config.from_toml,
            'json': Config.from_json
        }

        for filetype, func in parsers.items():
            try:
                return func(fname)
            except EleanorParserException:
                raise
            except Exception:
                pass

        raise EleanorParserException(f'failed to parse "{fname}" as yaml, toml or json')
