from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.kernel import discover

from ..common import TestCase


class TestKernelDiscover(TestCase):
    """
    Tests of the eleanor.kernel.discover module.
    """

    def test_import_kernel_module_normalizes_name_and_imports(self):
        """
        Ensure that kernel names are lowercased/prefixed before import.
        """
        expected_name = "eleanor.kernel.eq36"
        with (
            mock.patch.object(discover, "kernels", {expected_name}),
            mock.patch.object(discover, "import_module", return_value="module") as import_mock,
        ):
            module = discover.import_kernel_module("EQ36")

        import_mock.assert_called_once_with(expected_name)
        self.assertEqual(module, "module")

    def test_import_kernel_module_accepts_fully_qualified_name(self):
        """
        Ensure that fully qualified kernel names are accepted without adding a second prefix.
        """
        expected_name = "eleanor.kernel.eq36"
        with (
            mock.patch.object(discover, "kernels", {expected_name}),
            mock.patch.object(discover, "import_module", return_value="module") as import_mock,
        ):
            module = discover.import_kernel_module(expected_name)

        import_mock.assert_called_once_with(expected_name)
        self.assertEqual(module, "module")

    def test_import_kernel_module_rejects_unknown_kernel(self):
        """
        Ensure that unknown kernels raise an informative :class:`EleanorException`.
        """
        with mock.patch.object(discover, "kernels", {"eleanor.kernel.eq36"}):
            with self.assertRaises(EleanorException) as cm:
                discover.import_kernel_module("unknown")

        self.assertIn('unsupported kernel type "eleanor.kernel.unknown"', str(cm.exception))

    def test_import_all_kernels(self):
        """
        Ensure that :func:`import_all_kernels` imports every kernel from the discovered registry.
        """
        kernels = {"eleanor.kernel.a", "eleanor.kernel.b"}

        with (
            mock.patch.object(discover, "kernels", kernels),
            mock.patch.object(
                discover,
                "import_kernel_module",
                side_effect=lambda kernel_type: f"module:{kernel_type}",
            ) as import_kernel_mock,
        ):
            modules = discover.import_all_kernels()

        self.assertEqual(
            modules,
            {
                "eleanor.kernel.a": "module:eleanor.kernel.a",
                "eleanor.kernel.b": "module:eleanor.kernel.b",
            },
        )
        self.assertEqual(import_kernel_mock.call_count, 2)
