from dataclasses import dataclass

from sqlalchemy import Column, ForeignKey, Integer, String, Table

from ..exceptions import EleanorException
from ..parameters import Parameter
from ..typing import cast
from ..yeoman import JSONDict, yeoman_registry


@dataclass
class Settings(object):
    timeout: int | None

    def parameters(self) -> list[Parameter]:
        return []


@yeoman_registry.mapped_as_dataclass(kw_only=True)
class Config(object):
    """ORM-mapped kernel configuration row.

    .. warning::
        The ``settings`` attribute is an internal ORM column field.  After a
        database round-trip SQLAlchemy rehydrates it as a raw ``dict``; it is
        **not safe to read ``settings`` directly**.  Always use
        :meth:`resolved_settings` as the sole public entry point for
        accessing the typed :class:`Settings` value.
    """

    __table__: Table = Table(
        'kernel',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), primary_key=True),
        Column('type', String, nullable=False),
        Column('settings', JSONDict, nullable=False),
    )

    type: str
    # SQLAlchemy interprets this annotation to choose the mapped column type,
    # so it must name a single concrete class. At runtime the attribute may
    # briefly hold a ``dict`` (the form SQLAlchemy rehydrates out of the
    # ``JSONDict`` column); :meth:`resolved_settings` is the only safe entry
    # point for reading it and narrows the raw form via the kernel registry.
    settings: Settings
    id: int | None = None

    def resolved_settings(self) -> Settings:
        """Return ``self.settings`` as a fully-typed :class:`Settings` instance.

        If the field is still a raw mapping (the shape SQLAlchemy rehydrates
        from the ``JSONDict`` column), dispatch through the kernel registry to
        produce the correct concrete ``Settings`` subclass and cache it in
        place. The registry is imported lazily to avoid pulling the plugin
        subsystem into this leaf config module.

        The ``settings`` attribute is statically typed as :class:`Settings`
        to satisfy SQLAlchemy's Mapped-column inference, but the JSONDict
        column deserializer hands us a raw ``dict`` until this method caches
        the parsed form. :func:`object.__getattribute__` retrieves the value
        untyped so the isinstance guards below are meaningful to pyright.
        """
        raw = cast(object, object.__getattribute__(self, 'settings'))
        if isinstance(raw, Settings):
            return raw
        if not isinstance(raw, dict):
            raise EleanorException(
                f'kernel.settings has unexpected type {type(raw).__name__}',
            )
        from .registry import get_factory

        spec = get_factory(self.type)
        settings = spec.settings_from_dict(cast(dict[str, object], raw))
        if not isinstance(settings, Settings):
            raise EleanorException(
                f'kernel plugin "{self.type}" returned '
                + f'{type(settings).__name__}, expected a Settings instance',
            )
        self.settings = settings
        return settings

    def parameters(self) -> list[Parameter]:
        return self.resolved_settings().parameters()
