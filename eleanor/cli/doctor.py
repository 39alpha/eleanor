import argparse
import sys

import eleanor
from eleanor.executor.registry import available_executors
from eleanor.kernel.registry import available_kernels
from eleanor.navigator.registry import available_navigators
from eleanor.output.registry import available_outputs
from eleanor.plugin import PLUGIN_API_VERSIONS


def init(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = "Print diagnostic information about this eleanor installation"
    parser.set_defaults(func=execute)
    return parser


def _use_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _fmt(text: str, code: str) -> str:
    if _use_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def _bold(text: str) -> str:
    return _fmt(text, "1")


def _dim(text: str) -> str:
    return _fmt(text, "2")


def _green(text: str) -> str:
    return _fmt(text, "32")


def execute(_parser: argparse.ArgumentParser, _ns: argparse.Namespace) -> None:
    print()
    print(f"  {_bold('eleanor')} {_green(eleanor.__version__)}")
    print(f"  {_dim('Python')}  {_dim(sys.version.split(chr(10))[0])}")
    print()

    print(f"  {_bold('Plugin API versions')}")
    for kind in sorted(PLUGIN_API_VERSIONS):
        current, floor = PLUGIN_API_VERSIONS[kind]
        label = f"  {kind:12s}"
        versions = f"v{current} {_dim('(min v' + str(floor) + ')')}"
        print(f"  {label}  {versions}")
    print()

    sections = [
        ("Executors", sorted(available_executors())),
        ("Kernels", sorted(available_kernels())),
        ("Navigators", sorted(available_navigators())),
        ("Outputs", sorted(available_outputs())),
    ]
    for heading, names in sections:
        print(f"  {_bold(heading)}")
        if names:
            for name in names:
                print(f"    {_green('•')} {name}")
        else:
            print(f"    {_dim('(none)')}")
    print()
