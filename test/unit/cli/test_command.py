"""``EleanorCommand`` / ``EleanorGroup``: a shared ``-v/--verbose`` and uniform error reporting."""

import click
import pytest
from click.testing import CliRunner, Result

from eleanor.cli import main
from eleanor.cli.command import EleanorCommand, EleanorGroup, command, group
from eleanor.cli.util import show_verbose_output
from eleanor.exceptions import EleanorError


def walk(cmd: click.Command, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], click.Command]]:
    found = [(path, cmd)]
    if isinstance(cmd, click.Group):
        ctx = click.Context(cmd)
        for name in cmd.list_commands(ctx):
            sub = cmd.get_command(ctx, name)
            if sub is not None:
                found.extend(walk(sub, (*path, name)))
    return found


TREE = walk(main)


@pytest.mark.parametrize(("path", "cmd"), TREE, ids=[" ".join(("eleanor", *path)) for path, _ in TREE])
def test_every_builtin_command_is_an_eleanor_command(path: tuple[str, ...], cmd: click.Command) -> None:
    expected = EleanorGroup if isinstance(cmd, click.Group) else EleanorCommand
    assert isinstance(cmd, expected), path


@pytest.mark.parametrize(("path", "cmd"), TREE, ids=[" ".join(("eleanor", *path)) for path, _ in TREE])
def test_every_builtin_command_defines_verbose_exactly_once(path: tuple[str, ...], cmd: click.Command) -> None:
    opts = [opt for param in cmd.params for opt in param.opts if opt in ("-v", "--verbose")]
    assert sorted(opts) == ["--verbose", "-v"], path


def _probe_tree(seen: list[bool], error: BaseException | None = None) -> EleanorGroup:
    """Build ``root sub leaf`` and record whether verbose was set when ``leaf`` ran."""

    @group()
    def root() -> None: ...

    @root.group()
    def sub() -> None: ...

    @sub.command(error_message="leaf failed")
    def leaf() -> None:
        seen.append(show_verbose_output())
        if error is not None:
            raise error

    return root


@pytest.mark.parametrize(
    "args",
    [
        ["-v", "sub", "leaf"],
        ["sub", "-v", "leaf"],
        ["sub", "leaf", "-v"],
        ["--verbose", "sub", "leaf"],
        ["sub", "leaf", "--verbose"],
    ],
)
def test_verbose_is_accepted_at_any_level(args: list[str]) -> None:
    seen: list[bool] = []

    result = CliRunner().invoke(_probe_tree(seen), args)

    assert result.exit_code == 0, result.output
    assert seen == [True]


def test_verbose_defaults_off() -> None:
    seen: list[bool] = []

    result = CliRunner().invoke(_probe_tree(seen), ["sub", "leaf"])

    assert result.exit_code == 0, result.output
    assert seen == [False]


def test_show_verbose_output_is_false_outside_a_cli_context() -> None:
    assert show_verbose_output() is False


def test_subcommands_and_subgroups_inherit_the_eleanor_classes() -> None:
    root = _probe_tree([])
    sub = root.commands["sub"]

    assert isinstance(sub, EleanorGroup)
    assert isinstance(sub.commands["leaf"], EleanorCommand)  # pyrefly: ignore[missing-attribute]


def test_helpers_forward_click_attributes() -> None:
    @command("renamed", help="Custom help.", hidden=True)
    def original() -> None: ...

    @group("grouped", context_settings={"help_option_names": ["-h", "--help"]})
    def grp() -> None: ...

    assert original.name == "renamed"
    assert original.help == "Custom help."
    assert original.hidden is True
    assert grp.name == "grouped"
    assert grp.context_settings == {"help_option_names": ["-h", "--help"]}


def _fail(error: BaseException, *args: str) -> Result:
    return CliRunner().invoke(_probe_tree([], error), ["sub", "leaf", *args])


def test_errors_are_reported_with_the_command_message() -> None:
    result = _fail(EleanorError("boom"))

    assert result.exit_code == 1
    assert result.stderr == "Error: leaf failed - boom\n"


def test_errors_without_a_command_message_are_reported_bare() -> None:
    @group()
    def root() -> None: ...

    @root.command()
    def leaf() -> None:
        raise RuntimeError("boom")

    result = CliRunner().invoke(root, ["leaf"])

    assert result.exit_code == 1
    assert result.stderr == "Error: boom\n"


def test_errors_are_reported_exactly_once() -> None:
    result = _fail(RuntimeError("boom"))

    assert result.stderr.count("Error:") == 1
    assert result.stderr.count("boom") == 1


@pytest.mark.parametrize("args", [["sub", "leaf", "-v"], ["-v", "sub", "leaf"]], ids=["on-leaf", "on-root"])
def test_verbose_errors_print_the_traceback(args: list[str]) -> None:
    result = CliRunner().invoke(_probe_tree([], RuntimeError("boom")), args)

    assert result.exit_code == 1
    assert "Traceback" in result.stderr
    assert "RuntimeError: boom" in result.stderr
    assert "leaf failed" not in result.stderr


def test_click_exceptions_pass_through_unchanged() -> None:
    result = _fail(click.UsageError("bad usage"))

    assert result.exit_code == 2
    assert "Error: bad usage" in result.stderr
    assert "leaf failed" not in result.stderr


def test_click_exceptions_never_print_a_traceback() -> None:
    result = _fail(click.ClickException("plain message"), "-v")

    assert result.exit_code == 1
    assert result.stderr == "Error: plain message\n"


def test_abort_is_reported_by_click() -> None:
    result = _fail(click.Abort())

    assert result.exit_code == 1
    assert result.stderr == "Aborted!\n"


@pytest.mark.parametrize("code", [0, 3])
def test_exit_keeps_its_code(code: int) -> None:
    result = _fail(click.exceptions.Exit(code))

    assert result.exit_code == code
    assert result.stderr == ""


def test_keyboard_interrupt_is_left_to_click() -> None:
    result = _fail(KeyboardInterrupt())

    assert result.exit_code == 1
    assert result.stderr == "\nAborted!\n"


def test_plain_click_commands_under_an_eleanor_group_get_generic_handling() -> None:
    @group()
    def root() -> None: ...

    @click.command()
    def plugin() -> None:
        raise RuntimeError("boom")

    root.add_command(plugin)

    quiet = CliRunner().invoke(root, ["plugin"])
    verbose = CliRunner().invoke(root, ["-v", "plugin"])

    assert quiet.stderr == "Error: boom\n"
    assert "Traceback" in verbose.stderr


def test_verbose_option_can_be_suppressed() -> None:
    @command(verbose_option=False)
    def cmd() -> None: ...

    @group(verbose_option=False)
    def grp() -> None: ...

    for suppressed in (cmd, grp):
        assert not [opt for param in suppressed.params for opt in param.opts if opt in ("-v", "--verbose")]

    result = CliRunner().invoke(cmd, ["-v"])

    assert result.exit_code == 2
    assert "No such option '-v'" in result.stderr


def test_suppressing_verbose_frees_the_flag_for_the_command() -> None:
    @command(verbose_option=False)
    @click.option("-v", "--version", "version", is_flag=True)
    def cmd(*, version: bool) -> None:
        click.echo(f"version={version} verbose={show_verbose_output()}")

    result = CliRunner().invoke(cmd, ["-v"])

    assert result.exit_code == 0, result.output
    assert result.output == "version=True verbose=False\n"


def test_verbose_from_a_parent_still_reaches_a_suppressed_subcommand() -> None:
    seen: list[bool] = []

    @group()
    def root() -> None: ...

    @root.command(verbose_option=False)
    def leaf() -> None:
        seen.append(show_verbose_output())

    result = CliRunner().invoke(root, ["-v", "leaf"])

    assert result.exit_code == 0, result.output
    assert seen == [True]


def test_subcommand_helpers_forward_the_suppression_flags() -> None:
    @group()
    def root() -> None: ...

    @root.group(handle_errors=False, verbose_option=False)
    def sub() -> None: ...

    @sub.command(handle_errors=False, verbose_option=False)
    def leaf() -> None: ...

    for cmd in (sub, leaf):
        assert isinstance(cmd, EleanorCommand)
        assert cmd.handle_errors is False
        assert not [opt for param in cmd.params for opt in param.opts if opt in ("-v", "--verbose")]


def test_error_handling_is_on_by_default() -> None:
    @command()
    def cmd() -> None: ...

    @group()
    def grp() -> None: ...

    assert cmd.handle_errors is True
    assert grp.handle_errors is True


def test_unhandled_command_errors_propagate_unchanged() -> None:
    error = RuntimeError("boom")

    @command(handle_errors=False, error_message="cmd failed")
    def cmd() -> None:
        raise error

    result = CliRunner().invoke(cmd, [])

    assert result.exception is error
    assert result.stderr == ""


def test_unhandled_group_errors_propagate_unchanged() -> None:
    error = RuntimeError("boom")

    @group(handle_errors=False, error_message="grp failed")
    def grp() -> None:
        raise error

    @grp.command()
    def leaf() -> None: ...

    result = CliRunner().invoke(grp, ["leaf"])

    assert result.exception is error
    assert result.stderr == ""


def test_an_unhandled_group_still_lets_its_subcommands_handle_errors() -> None:
    @group(handle_errors=False)
    def root() -> None: ...

    @root.command(error_message="leaf failed")
    def leaf() -> None:
        raise RuntimeError("boom")

    result = CliRunner().invoke(root, ["leaf"])

    assert result.exit_code == 1
    assert result.stderr == "Error: leaf failed - boom\n"


def test_unhandled_errors_still_propagate_with_verbose() -> None:
    error = RuntimeError("boom")

    @command(handle_errors=False)
    def cmd() -> None:
        raise error

    result = CliRunner().invoke(cmd, ["-v"])

    assert result.exception is error
    assert "Traceback" not in result.stderr


def test_an_unhandled_subcommand_is_not_rehandled_by_its_parent() -> None:
    # Opting out on a leaf should let its exception escape the whole CLI; today
    # the enclosing group catches it and reports it as if the leaf were a plain
    # click command, so the opt-out only has an effect under an opted-out parent.
    error = RuntimeError("boom")

    @group()
    def root() -> None: ...

    @root.command(handle_errors=False, error_message="leaf failed")
    def leaf() -> None:
        raise error

    result = CliRunner().invoke(root, ["leaf"])

    assert result.exception is error
    assert result.stderr == ""
