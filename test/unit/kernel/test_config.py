from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.kernel.config import Config, Settings

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

    def test_config_resolved_settings_rejects_dict_payload(self):
        """
        Ensure :meth:`Config.resolved_settings` rejects raw dict payloads.
        """
        config = Config(type='eq36', settings=Settings(timeout=None))
        config.settings = {'timeout': 12}  # type: ignore[assignment]
        with self.assertRaises(EleanorException):
            config.resolved_settings()

    def test_config_resolved_settings_returns_existing_settings_instance(self):
        """
        Ensure :meth:`Config.resolved_settings` is a no-op when already typed.
        """
        settings = Settings(timeout=10)
        config = Config(type='eq36', settings=settings)

        resolved = config.resolved_settings()
        self.assertIs(resolved, settings)

    def test_config_resolved_settings_rejects_unknown_types(self):
        """
        Ensure :meth:`Config.resolved_settings` raises on unexpected payload types.
        """
        config = Config(type='eq36', settings=Settings(timeout=None))
        config.settings = 42  # type: ignore[assignment]

        with self.assertRaises(EleanorException):
            config.resolved_settings()

    def test_config_parameters_delegates_to_settings(self):
        """
        Ensure that :meth:`Config.parameters` delegates to the underlying settings object.
        """
        parameter = object()
        settings = mock.Mock(spec=Settings)
        settings.parameters.return_value = [parameter]
        config = Config(type='eq36', settings=settings)

        result = config.parameters()

        settings.parameters.assert_called_once_with()
        self.assertEqual(result, [parameter])
