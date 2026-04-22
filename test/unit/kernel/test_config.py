from unittest import mock

from eleanor.exceptions import EleanorException
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

    def test_config_resolved_settings_converts_dict(self):
        """
        Ensure :meth:`Config.resolved_settings` converts a dict payload via the registry.
        """
        parsed_settings = Settings(timeout=5)
        spec = KernelSpec(
            settings_from_dict=mock.Mock(return_value=parsed_settings),
            build=mock.Mock(),
        )

        # Build Config with a placeholder Settings so SQLAlchemy is happy,
        # then overwrite ``settings`` with a dict to simulate the state
        # SQLAlchemy leaves behind when rehydrating a JSON column.
        config = Config(type='eq36', settings=Settings(timeout=None))
        config.settings = {'timeout': 12}  # type: ignore[assignment]

        with mock.patch('eleanor.kernel.registry.get_factory', return_value=spec) as get_factory_mock:
            resolved = config.resolved_settings()

        get_factory_mock.assert_called_once_with('eq36')
        spec.settings_from_dict.assert_called_once_with({'timeout': 12})
        self.assertIs(resolved, parsed_settings)
        # Cached in-place for subsequent accesses.
        self.assertIs(config.settings, parsed_settings)

    def test_config_resolved_settings_returns_existing_settings_instance(self):
        """
        Ensure :meth:`Config.resolved_settings` is a no-op when already typed.
        """
        settings = Settings(timeout=10)
        config = Config(type='eq36', settings=settings)

        with mock.patch('eleanor.kernel.registry.get_factory') as get_factory_mock:
            resolved = config.resolved_settings()

        get_factory_mock.assert_not_called()
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
