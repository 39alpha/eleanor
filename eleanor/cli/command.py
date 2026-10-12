# pyrefly: ignore-errors [explicit-any]
# ruff: noqa: ANN401
from collections.abc import Callable
from typing import Any, override

import click

from eleanor.cli.util import _record_verbose, handle_exception


class EleanorCommand(click.Command):
    def __init__(self, *args: Any, error_message: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.error_message = error_message
        self.params.append(
            click.Option(
                ["-v", "--verbose"],
                is_flag=True,
                expose_value=False,
                is_eager=True,
                callback=_record_verbose,
                help="Enable verbose output.",
            ),
        )

    @override
    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except Exception as e:
            handle_exception(e, self.error_message)


class EleanorGroup(EleanorCommand, click.Group):
    command_class = EleanorCommand
    group_class = type


def command(
    name: str | None = None,
    *,
    error_message: str | None = None,
    **attrs: Any,
) -> Callable[[Callable[..., Any]], EleanorCommand]:
    return click.command(name, cls=EleanorCommand, error_message=error_message, **attrs)


def group(
    name: str | None = None,
    *,
    error_message: str | None = None,
    **attrs: Any,
) -> Callable[[Callable[..., Any]], EleanorGroup]:
    return click.group(name, cls=EleanorGroup, error_message=error_message, **attrs)


__all__ = [
    "EleanorCommand",
    "EleanorGroup",
    "command",
    "group",
]
