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
        amount: object,
        *_args: object,
        assume_mass_fraction: bool = False,
        combined: bool = False,
        proportional_sampling: bool = False,
        titration_rate: object | None = None,
        limit: int | None = None,
        **_kwargs: object,
    ):
        self.filename = filename
        self.reactant_name = reactant_name
        try:
            self.amount = Parameter.load(amount, name='amount')
            if titration_rate is None:
                self.titration_rate = ValueParameter(name='titration_rate', type=None, value=1.0)
                self.oxide_rates: dict[str, Parameter] = {}
            elif isinstance(titration_rate, dict) and 'base_rate' in titration_rate:
                titration_rate_map = cast(dict[str, object], titration_rate)
                self.titration_rate = Parameter.load(titration_rate_map['base_rate'], name='titration_rate')
                oxide_rates_raw = cast(dict[str, object], titration_rate_map.get('oxide_rates', {}))
                self.oxide_rates = {
                    name: Parameter.load(rate, name=f'oxide_rate_{name}')
                    for name, rate in oxide_rates_raw.items()
                }
            else:
                self.titration_rate = Parameter.load(cast(object, titration_rate), name='titration_rate')
                self.oxide_rates = {}
        except EleanorException:
            raise
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
        matches = cast(list[tuple[object, object]], pattern.findall(name))
        for element, count in matches:
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

        if self.oxide_rates:
            for rate_name in self.oxide_rates:
                if rate_name not in names:
                    raise EleanorException(
                        f'oxide rate "{rate_name}" does not match any oxide column in "{self.filename}"'
                    )

        order.suborders = Suborders({'combined': self.combined, 'proportional_sampling': self.proportional_sampling})
        for n, (_, row) in enumerate(data.iterrows()):
            oxide_names: list[str] = []
            fractions = np.empty(0)

            row_items = cast(list[tuple[object, object]], list(row.items()))
            for oxide_name_raw, fraction in row_items:
                oxide_name = str(oxide_name_raw)
                if oxide_name in compositions and isinstance(fraction, float) and fraction > 0:
                    oxide_names.append(oxide_name)
                    fractions = np.append(fractions, fraction)

            if self.oxide_rates:
                for oxide_name in oxide_names:
                    if oxide_name not in self.oxide_rates:
                        raise EleanorException(
                            f'oxide "{oxide_name}" has a positive quantity but no relative rate was specified'
                        )

            if self.assume_mass_fraction:
                for (i, oxide_name) in enumerate(oxide_names):
                    fractions[i] /= molar_masses[oxide_name]

            fractions /= np.sum(fractions)

            oxides: dict[str, GlassReactantOxide] = {}
            for (i, oxide_name) in enumerate(oxide_names):
                relative_rate = self.oxide_rates.get(
                    oxide_name,
                    ValueParameter(name='relative_rate', type=None, value=1.0),
                )
                oxide = GlassReactantOxide(
                    oxide_name,
                    compositions[oxide_name],
                    float(cast(float, fractions[i])),
                    relative_rate,
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
