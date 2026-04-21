from unittest import mock

from eleanor.kernel.config import Config, Settings
from eleanor.kernel.registry import KernelSpec

from ..common import TestCase


class TestKernelConfig(TestCase):
    """
    Tests of the eleanor.kernel.config module.
    """

    def test_settings_parameters_default_empty(self):
        """
        Ensure that :class:`Settings` returns an empty parameter list by default.
        """
        settings = Settings(timeout=30)
        self.assertEqual(settings.parameters(), [])

    def test_config_reconstruct_dict_settings(self):
        """
        Ensure that :meth:`Config.reconstruct` converts dict settings via the kernel registry.
        """
        parsed_settings = object()
        spec = KernelSpec(
            settings_from_dict=mock.Mock(return_value=parsed_settings),
            build=mock.Mock(),
        )

        config = Config(type='eq36', settings={'timeout': 12})

        with mock.patch('eleanor.kernel.config.get_spec', return_value=spec) as get_spec_mock:
            config.reconstruct()

        get_spec_mock.assert_called_once_with('eq36')
        spec.settings_from_dict.assert_called_once_with({'timeout': 12})
        self.assertIs(config.settings, parsed_settings)

    def test_config_reconstruct_non_dict_settings_noop(self):
        """
        Ensure that :meth:`Config.reconstruct` leaves non-dict settings unchanged.
        """
        settings = Settings(timeout=10)
        config = Config(type='eq36', settings=settings)

        with mock.patch('eleanor.kernel.config.get_spec') as get_spec_mock:
            config.reconstruct()

        get_spec_mock.assert_not_called()
        self.assertIs(config.settings, settings)

    def test_config_parameters_delegates_to_settings(self):
        """
        Ensure that :meth:`Config.parameters` delegates to the underlying settings object.
        """
        parameter = object()
        settings = mock.Mock()
        settings.parameters.return_value = [parameter]
        config = Config(type='eq36', settings=settings)

        result = config.parameters()

        settings.parameters.assert_called_once_with()
        self.assertEqual(result, [parameter])
