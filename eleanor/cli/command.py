# pyrefly: ignore-errors [explicit-any]
# ruff: noqa: ANN401
from collections.abc import Callable
from typing import Any, override

import click

from eleanor.cli.util import _record_verbose, handle_exception

_UNHANDLED_ERROR = "eleanor.unhandled"


class EleanorCommand(click.Command):
    def __init__(
        self,
        *args: Any,
        error_message: str | None = None,
        handle_errors: bool = True,
        verbose_option: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.handle_errors = handle_errors
        self.error_message = error_message
        if verbose_option:
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
            if not self.handle_errors or ctx.meta.get(_UNHANDLED_ERROR) is e:
                ctx.meta[_UNHANDLED_ERROR] = e
                raise
            handle_exception(e, self.error_message)


class EleanorGroup(EleanorCommand, click.Group):
    command_class = EleanorCommand
    group_class = type


def command(
    name: str | None = None,
    *,
    error_message: str | None = None,
    handle_errors: bool = True,
    verbose_option: bool = True,
    **attrs: Any,
) -> Callable[[Callable[..., Any]], EleanorCommand]:
    return click.command(
        name,
        cls=EleanorCommand,
        error_message=error_message,
        handle_errors=handle_errors,
        verbose_option=verbose_option,
        **attrs,
    )


def group(
    name: str | None = None,
    *,
    error_message: str | None = None,
    handle_errors: bool = True,
    verbose_option: bool = True,
    **attrs: Any,
) -> Callable[[Callable[..., Any]], EleanorGroup]:
    return click.group(
        name,
        cls=EleanorGroup,
        error_message=error_message,
        handle_errors=handle_errors,
        verbose_option=verbose_option,
        **attrs,
    )


__all__ = [
    "EleanorCommand",
    "EleanorGroup",
    "command",
    "group",
]
