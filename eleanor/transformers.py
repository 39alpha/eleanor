import re
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .order import Order, Suborder, Suborders
from .parameters import Parameter, ValueParameter
from .reactants import GlassReactant, GlassReactantOxide, ReactantType
from .typing import cast, override


class AbstractTransformer(ABC):
    @abstractmethod
    def transform(self, order: Order, kernel: AbstractKernel) -> Order:
        return order


class GlassReactantEmbedder(AbstractTransformer):
    filename: str
    reactant_name: str
    amount: Parameter
    titration_rate: Parameter
    assume_mass_fraction: bool
    combined: bool
    proportional_sampling: bool
    limit: int | None

    def __init__(
        self,
        filename: str,
        reactant_name: str,
        amount,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        *args,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        assume_mass_fraction: bool = False,
        combined: bool = False,
        proportional_sampling: bool = False,
        titration_rate=None,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        limit: int | None = None,
        **kwargs,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    ):
        self.filename = filename
        self.reactant_name = reactant_name
        try:
            self.amount = Parameter.load(amount, name='amount')
            if titration_rate is None:
                self.titration_rate = ValueParameter(name='titration_rate', type=None, value=1.0)
            else:
                self.titration_rate = Parameter.load(titration_rate, name='titration_rate')
        except Exception as e:
            raise EleanorException('failed to construct the GlassReactantEmbedder') from e

        self.assume_mass_fraction = assume_mass_fraction
        self.combined = combined
        self.proportional_sampling = proportional_sampling
        self.limit = limit
        if self.limit is not None and self.limit < 1:
            self.limit = 1

    def read_oxide_composition(self, name: str) -> dict[str, int] | None:
        pattern = re.compile(r'([A-Z][a-z]?)(\d*)(?=[A-Z]|$)')
        if not pattern.match(name):
            return None
        composition: dict[str, int] = {}
        for element, count in pattern.findall(name):  # pyright: ignore[reportAny]
            if not isinstance(element, str) or not isinstance(count, str):
                return None
            composition[element] = int(count) if count != '' else 1
        return composition

    def read_csv(self) -> pd.DataFrame:
        try:
            data = pd.read_csv(self.filename)
        except Exception as e:
            raise EleanorException(f'failed to read "{self.filename}" in CSV format') from e

        return pd.DataFrame(data)

    @override
    def transform(self, order: Order, kernel: AbstractKernel) -> Order:
        data = self.read_csv()
        names: list[str] = []
        compositions: dict[str, dict[str, int]] = {}
        molar_masses: dict[str, float] = {}
        for (colnum, name) in enumerate(data.columns):
            composition = self.read_oxide_composition(name)
            if composition is not None:
                molar_mass = 0.0
                for element, count in composition.items():
                    atomic_weight = kernel.get_atomic_weight(element)
                    if atomic_weight is None:
                        raise EleanorException(f'kernel could not find atomic weight for element "{element}" in column {colnum}')
                    molar_mass += count * atomic_weight
                names.append(name)
                compositions[name] = composition
                molar_masses[name] = molar_mass

        order.suborders = Suborders({'combined': self.combined, 'proportional_sampling': self.proportional_sampling})
        for n, (_, row) in enumerate(data.iterrows()):
            oxide_names: list[str] = []
            fractions = np.empty(0)

            for oxide_name, fraction in row.items():  # pyright: ignore[reportAny]
                oxide_name = str(oxide_name)
                if oxide_name in compositions and isinstance(fraction, float) and fraction > 0:
                    oxide_names.append(oxide_name)
                    fractions = np.append(fractions, fraction)

            if self.assume_mass_fraction:
                for (i, oxide_name) in enumerate(oxide_names):
                    fractions[i] /= molar_masses[oxide_name]

            fractions /= np.sum(fractions)

            oxides: dict[str, GlassReactantOxide] = {}
            for (i, oxide_name) in enumerate(oxide_names):
                oxide = GlassReactantOxide(
                    oxide_name,
                    compositions[oxide_name],
                    float(fractions[i]),  # pyright: ignore[reportAny]
                )
                oxides[oxide_name] = oxide

            reactant = GlassReactant(
                name=self.reactant_name,
                type=ReactantType.GLASS,
                amount=self.amount,
                titration_rate=self.titration_rate,
                oxides=oxides,
            )

            order.suborders.suborders.append(Suborder(reactants=[reactant]))

            if self.limit is not None and n + 1 >= self.limit:
                break

        return order


def transform(order: Order, kernel: AbstractKernel) -> Order:
    if len(order.transformers) != 0:
        for transformer_config in order.transformers:
            transformer = cast(AbstractTransformer, transformer_config.load()(**transformer_config.args))
            order = transformer.transform(order, kernel)
        order.transformers = []
    return order
