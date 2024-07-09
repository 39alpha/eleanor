from dataclasses import dataclass

import numpy as np

from ..exceptions import EleanorException, EleanorParserException
from ..hanger.tool_room import NumberFormat, convert_to_number, is_list_of
from ..typing import Number, Optional, Self


@dataclass
class Parameter(object):
    name: str
    type: Optional[str]
    unit: str
    min: Optional[Number]
    max: Optional[Number]
    value: Optional[Number]
    values: Optional[list[Number]]

    @property
    def is_fully_specified(self) -> bool:
        return self.value is not None and all(x is None for x in [self.min, self.max, self.values])

    def __init__(self,
                 name: str,
                 unit: str,
                 type: Optional[str] = None,
                 min: Optional[Number] = None,
                 max: Optional[Number] = None,
                 value: Optional[Number] = None,
                 values: Optional[list[Number]] = None):

        if min is None and max is None and value is None and values is None:
            raise EleanorParserException(
                f'must provide min and max, or value or values in parameter configuration {name}')
        elif min is not None or max is not None:
            if min is None or max is None:
                raise EleanorParserException(
                    f'if min or max is provided, then the other is required in parameter configuration {name}')
            elif value is not None or values is not None:
                raise EleanorParserException(
                    f'must provide min and max, or value or values in parameter configuration {name}')
            elif min > max:
                raise EleanorParserException(f'min and max values are out of order in parameter configuration {name}')
        elif value is not None and values is not None:
            raise EleanorParserException(
                f'must provide min and max, or value or values in parameter configuration {name}')

        self.name = name
        self.type = type
        self.unit = unit
        self.min = min
        self.max = max
        self.value = value
        self.values = values

        self.refine()
        self.validate()

    @property
    def range(self) -> tuple[Number, Number]:
        if self.value is not None:
            return (self.value, self.value)
        elif self.values is not None:
            return (self.values[0], self.values[-1])
        elif self.min is not None and self.max is not None:
            return (self.min, self.max)
        else:
            raise EleanorException(f'unexpected Parameter state: {self}')

    def refine(self) -> Self:
        if self.min is not None and self.min == self.max:
            self.value, self.min, self.max = self.min, None, None
        elif self.values is not None:
            self.values = list(set(self.values))
            if len(self.values) == 1:
                self.value, self.values = self.values[0], None

        return self

    def validate(self) -> Self:
        s = sum([self.value is not None, self.min is not None and self.max is not None, self.values is not None])
        if s == 0:
            raise Exception()
        elif s > 1:
            raise Exception()

        return self

    def fix(self, value: Number) -> Self:
        self.value = value
        self.min = None
        self.max = None
        self.values = None

        return self

    def constrain_by_value(self, value: Number) -> Self:
        if self.value is not None:
            if self.value != value:
                self.clear()
            else:
                self.fix(value)
        elif self.min is not None and self.max is not None:
            if value < self.min or value > self.max:
                self.clear()
            else:
                self.min = self.max = value
        elif self.values is not None:
            values = self.values
            self.values = [v for v in values if v == value]
        else:
            raise Exception()

        return self.validate()

    def constrain_by_range(self, minimum: Number, maximum: Number) -> Self:
        if minimum > maximum:
            return self.constrain_by_range(maximum, minimum)

        if self.value is not None:
            if self.value < minimum or self.value > maximum:
                self.clear()
        elif self.min is not None and self.max is not None:
            self.min = max(self.min, minimum)
            self.max = min(self.max, maximum)
        elif self.values is not None:
            self.values = [v for v in self.values if minimum <= v and v <= maximum]
        else:
            raise Exception()

        self.refine()
        return self.validate()

    def constrain_by_list(self, values: list[Number]) -> Self:
        if self.value is not None:
            self.values = [v for v in values if v == self.value]
        elif self.min is not None and self.max is not None:
            minimum, maximum = self.min, self.max
            self.values = [v for v in values if minimum <= v and v <= maximum]
        elif self.values is not None:
            self.values = [v for v in values if v in self.values]
        else:
            raise Exception()

        self.min = None
        self.max = None
        self.value = None

        self.refine()
        return self.validate()

    def clear(self):
        self.values = []
        self.value = None
        self.min = None
        self.max = None

    @property
    def is_over_constrained(self) -> bool:
        if self.values is not None and len(self.values) == 0:
            return True

        if self.value is not None or (self.min is not None and self.max is not None):
            return False

        raise Exception()

    def format(self, *args, formatter=NumberFormat.SCIENTIFIC, **kwargs):
        # TODO: Handle units
        if self.value is not None:
            return formatter.fmt(self.value, *args, **kwargs)
        elif self.values is not None:
            return '[' + ', '.join([formatter.fmt(v, *args, **kwargs) for v in self.values]) + ']'
        elif self.min is not None and self.max is not None:
            return f'({formatter.fmt(self.min, *args, **kwargs)}, {formatter.fmt(self.max, *args, **kwargs)})'

        raise EleanorException(f'unexpected Parameter state: {self}')

    def to_row(self) -> dict[str, Number]:
        # DGM: The second condition is redundant, but satisfies MyPy
        if not self.is_fully_specified or self.value is None:
            raise EleanorException('cannot convert underspecified parameter to row')

        return {f'{self.name}': self.value}

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        if not isinstance(name, str):
            raise EleanorParserException(f'parameter {name} name must be a string')

        param_type = raw.get('type')
        if not isinstance(param_type, (str, type(None))):
            raise EleanorParserException(f'parameter {name} type must be a string')

        unit = raw['unit']
        if not isinstance(unit, str):
            raise EleanorParserException(f'parameter {name} unit must be a string')

        min = raw.get('min')
        if min is not None:
            min = convert_to_number(min)

        max = raw.get('max')
        if max is not None:
            max = convert_to_number(max)

        value = raw.get('value')
        if value is not None:
            value = convert_to_number(value)

        values = raw.get('values')
        if values is not None:
            if not isinstance(values, list):
                raise EleanorParserException(f'parameter {name} values must be a list')
            values = [convert_to_number(value) for value in values]

        return Parameter(name, unit, param_type, min, max, value, values)
