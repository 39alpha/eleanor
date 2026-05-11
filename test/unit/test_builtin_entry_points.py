from importlib.metadata import entry_points

from eleanor.cli.registry import BUILTIN_CLI_COMMANDS
from eleanor.cli.registry import ENTRY_POINT_GROUP as CLI_EP
from eleanor.executor.registry import BUILTIN_EXECUTORS
from eleanor.executor.registry import ENTRY_POINT_GROUP as EXEC_EP
from eleanor.kernel.registry import BUILTIN_KERNELS
from eleanor.kernel.registry import ENTRY_POINT_GROUP as KERN_EP
from eleanor.navigator.registry import BUILTIN_NAVIGATORS
from eleanor.navigator.registry import ENTRY_POINT_GROUP as NAV_EP
from eleanor.output.registry import BUILTIN_OUTPUTS
from eleanor.output.registry import ENTRY_POINT_GROUP as OUT_EP

from .common import TestCase


class TestBuiltinEntryPointConsistency(TestCase):
    """Tests that builtin-name constants match installed entry-point names."""

    def test_builtin_sets_match_eleanor_entry_points(self):
        """Ensure each BUILTIN_* frozenset stays in sync with pyproject entry points."""
        expectations = (
            ("executor", BUILTIN_EXECUTORS, EXEC_EP),
            ("kernel", BUILTIN_KERNELS, KERN_EP),
            ("navigator", BUILTIN_NAVIGATORS, NAV_EP),
            ("output", BUILTIN_OUTPUTS, OUT_EP),
            ("cli", BUILTIN_CLI_COMMANDS, CLI_EP),
        )
        for kind, builtins, group in expectations:
            with self.subTest(kind=kind):
                self.assertEqual(
                    builtins,
                    self._entry_point_names_for_eleanor(group),
                )

    @staticmethod
    def _entry_point_names_for_eleanor(group: str) -> frozenset[str]:
        """Return entry-point names in ``group`` filtered to the eleanor distribution."""
        import unittest

        eps = tuple(entry_points(group=group))
        eleanor_eps = tuple(
            ep for ep in eps if (dist := getattr(ep, "dist", None)) is not None and dist.name.lower() == "eleanor"
        )
        if not eleanor_eps:
            raise unittest.SkipTest(
                f"entry points in {group!r} lack distribution metadata; "
                "cannot distinguish eleanor built-ins from third-party plugins"
            )
        return frozenset(ep.name for ep in eleanor_eps)
