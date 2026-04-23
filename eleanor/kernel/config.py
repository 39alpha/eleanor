from dataclasses import dataclass

from ..exceptions import EleanorException
from ..parameters import Parameter
from ..typing import cast


@dataclass
class Settings(object):
    timeout: int | None

    def parameters(self) -> list[Parameter]:
        return []


def resolve_settings(kernel_type: str, payload: dict[str, object]) -> Settings:
    """Look up ``kernel_type`` in the kernel registry and rehydrate ``payload``
    into the plugin's concrete :class:`Settings` subclass.

    This is the single entry point both the order parser
    (:func:`eleanor.order.load_kernel_settings`) and the postgres persistence
    mapper use when turning a raw ``(type, dict)`` pair into a typed
    :class:`Settings` instance, so error messages and validation stay in lock
    step between the two paths.

    The registry is imported lazily so this leaf config module does not pull
    the plugin subsystem into callers that only need the :class:`Config` /
    :class:`Settings` dataclass types.
    """
    from .registry import get_factory  # noqa: PLC0415

    spec = get_factory(kernel_type)
    settings = spec.settings_from_dict(payload)
    if not isinstance(settings, Settings):
        raise EleanorException(
            f'kernel plugin "{kernel_type}" returned '
            + f'{type(settings).__name__}, expected a Settings instance',
        )
    return settings

@dataclass(kw_only=True)
class Config(object):
    type: str
    settings: Settings

    def resolved_settings(self) -> Settings:
        """Return the typed :class:`Settings` value.

        This remains a trivial typed helper so callers don't have to care that
        the persistence layer is the only thing that ever produces a
        :class:`Config`. It also defensively validates the runtime type so a
        mis-constructed instance (e.g. a test fixture that bypasses the type
        system via ``# type: ignore[assignment]``) still produces a legible
        error instead of silently behaving like a :class:`Settings`.

        The read is widened to :class:`object` so the ``isinstance`` guard
        survives basedpyright's narrow-by-annotation analysis
        (``reportUnnecessaryIsInstance``) without being dropped as dead code.
        """
        raw = cast(object, self.settings)
        if not isinstance(raw, Settings):
            raise EleanorException(
                f'kernel.settings has unexpected type {type(raw).__name__}',
            )
        return raw

    def parameters(self) -> list[Parameter]:
        return self.resolved_settings().parameters()
