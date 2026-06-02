import signal
from unittest import TestCase, mock

from eleanor.signals import ShutdownState, _safe_prev, shutdown_on_signal


class TestSignals(TestCase):
    """Tests for cooperative signal handling helpers."""

    def test_shutdown_on_signal_installs_and_restores_handlers(self):
        """Ensure shutdown_on_signal installs and restores SIGINT/SIGTERM handlers."""
        prev_int = signal.SIG_IGN
        prev_term = signal.SIG_DFL

        with (
            mock.patch("eleanor.signals.signal.getsignal", side_effect=[prev_int, prev_term]),
            mock.patch("eleanor.signals.signal.signal") as signal_mock,
        ):
            with shutdown_on_signal() as state:
                self.assertIsInstance(state, ShutdownState)
                self.assertFalse(state.requested)
                self.assertIsNone(state.signal_name)

        self.assertEqual(signal_mock.call_count, 4)
        install_int_call, install_term_call, restore_int_call, restore_term_call = signal_mock.call_args_list

        self.assertEqual(install_int_call.args[0], signal.SIGINT)
        handler = install_int_call.args[1]
        self.assertTrue(callable(handler))
        self.assertEqual(install_term_call, mock.call(signal.SIGTERM, handler))
        self.assertEqual(restore_int_call, mock.call(signal.SIGINT, prev_int))
        self.assertEqual(restore_term_call, mock.call(signal.SIGTERM, prev_term))

    def test_shutdown_on_signal_handler_raises_keyboard_interrupt(self):
        """Ensure the installed handler marks state and raises KeyboardInterrupt."""
        prev_int = signal.SIG_IGN
        prev_term = signal.SIG_DFL

        with (
            mock.patch("eleanor.signals.signal.getsignal", side_effect=[prev_int, prev_term]),
            mock.patch("eleanor.signals.signal.signal") as signal_mock,
        ):
            with shutdown_on_signal() as state:
                handler = signal_mock.call_args_list[0].args[1]
                self.assertTrue(callable(handler))

                with self.assertRaises(KeyboardInterrupt):
                    handler(signal.SIGTERM, None)

                self.assertTrue(state.requested)
                self.assertEqual(state.signal_name, "SIGTERM")
                self.assertEqual(signal_mock.call_count, 4)
                self.assertEqual(signal_mock.call_args_list[2], mock.call(signal.SIGINT, prev_int))
                self.assertEqual(signal_mock.call_args_list[3], mock.call(signal.SIGTERM, prev_term))

        self.assertEqual(signal_mock.call_count, 6)
        self.assertEqual(signal_mock.call_args_list[4], mock.call(signal.SIGINT, prev_int))
        self.assertEqual(signal_mock.call_args_list[5], mock.call(signal.SIGTERM, prev_term))

    def test_shutdown_on_signal_off_main_thread_is_a_no_op(self):
        """Ensure non-main-thread usage returns a no-op state and installs no handlers."""
        with (
            mock.patch("eleanor.signals.threading.current_thread", return_value=object()),
            mock.patch("eleanor.signals.threading.main_thread", return_value=object()),
            mock.patch("eleanor.signals.signal.getsignal") as getsignal_mock,
            mock.patch("eleanor.signals.signal.signal") as signal_mock,
        ):
            with shutdown_on_signal() as state:
                self.assertIsInstance(state, ShutdownState)
                self.assertFalse(state.requested)
                self.assertIsNone(state.signal_name)

        getsignal_mock.assert_not_called()
        signal_mock.assert_not_called()

    def test_safe_prev_returns_sig_dfl_for_none(self):
        """Ensure _safe_prev normalizes None handlers and passes through valid handlers."""
        self.assertIs(_safe_prev(None), signal.SIG_DFL)
        self.assertIs(_safe_prev(signal.SIG_IGN), signal.SIG_IGN)
