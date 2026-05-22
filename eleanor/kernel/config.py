from dataclasses import dataclass
from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.typing import cast

if TYPE_CHECKING:
    from eleanor.parameters import Parameter


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
    from eleanor.kernel.registry import get_factory

    spec = get_factory(kernel_type)
    settings = spec.settings_from_dict(payload)
    if not isinstance(settings, Settings):
        msg = f"kernel plugin {kernel_type!r} returned {type(settings).__name__}, expected a Settings instance"
        raise EleanorException(msg)

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
            msg = f"kernel.settings has unexpected type {type(raw).__name__}"
            raise EleanorException(msg)
        return raw

    def parameters(self) -> list[Parameter]:
        return self.resolved_settings().parameters()


__all__ = [
    "Config",
    "Settings",
    "resolve_settings",
]
