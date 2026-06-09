from unittest import TestCase, mock

from eleanor.config.kernel import KernelConfig
from eleanor.kernel.settings import KernelSettings


class TestKernelConfig(TestCase):
    """
    Tests of the eleanor.kernel.config module.
    """

    def test_settings_parameters_default_empty(self) -> None:
        """
        Ensure that :class:`KernelSettings` returns an empty parameter list by default.
        """
        settings = KernelSettings(timeout=30)
        self.assertEqual(settings.parameters(), [])

    def test_config_parameters_delegates_to_settings(self) -> None:
        """
        Ensure that :meth:`KernelConfig.parameters` delegates to the underlying settings object.
        """
        parameter = object()
        settings = mock.Mock(spec=KernelSettings)
        settings.parameters.return_value = [parameter]
        config = KernelConfig(kind="eq36", settings=settings)

        result = config.parameters()

        settings.parameters.assert_called_once_with()
        self.assertEqual(result, [parameter])
