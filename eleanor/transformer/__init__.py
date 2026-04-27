from abc import ABC, abstractmethod

from ..exceptions import EleanorException
from ..kernel.interface import AbstractKernel
from ..order import Order
from ..plugin import is_abstract_instantiation_error, resolve_api_version


class AbstractTransformer(ABC):
    @abstractmethod
    def transform(self, order: Order, kernel: AbstractKernel) -> Order:
        return order


def transform(
    order: Order,
    kernel: AbstractKernel,
    overrides: list[AbstractTransformer] | None = None,
) -> Order:
    """Apply the order's transformers (or ``overrides``) to ``order`` in sequence.

    :param overrides: optional list of already-instantiated transformers to
        apply instead of those declared in the order file. Useful for the
        inline-plugin workflow where a caller constructs a transformer
        programmatically and wants to bypass the registry lookup.
    """
    if overrides is not None:
        for transformer in overrides:
            order = transformer.transform(order, kernel)
        order.transformers = []
        return order

    if len(order.transformers) != 0:
        for transformer_config in order.transformers:
            transformer_factory = get_factory(transformer_config.type)
            version = resolve_api_version(transformer_factory)
            try:
                built = transformer_factory(**transformer_config.args)
            except TypeError as e:
                if not is_abstract_instantiation_error(e):
                    raise
                version_suffix = "" if version is None else f" (API v{version})"
                raise EleanorException(
                    f'transformer plugin "{transformer_config.type}" failed to instantiate{version_suffix}: {e}',
                ) from e
            if not isinstance(built, AbstractTransformer):
                raise EleanorException(
                    f'transformer plugin "{transformer_config.type}" returned '
                    + f"{type(built).__name__}, expected an AbstractTransformer",
                )
            order = built.transform(order, kernel)
        order.transformers = []
    return order


from .registry import (  # noqa: E402
    BUILTIN_TRANSFORMERS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    TransformerFactory,
    available_transformers,
    get_factory,
    register_transformer,
)

__all__ = [
    "AbstractTransformer",
    "BUILTIN_TRANSFORMERS",
    "ENTRY_POINT_GROUP",
    "OVERRIDE_ENV_VAR",
    "TransformerFactory",
    "available_transformers",
    "get_factory",
    "register_transformer",
    "transform",
]
