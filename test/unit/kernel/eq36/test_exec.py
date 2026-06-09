from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest import TestCase, mock

from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.exceptions import Eq36Exception
from eleanor.kernel.eq36.exec import eq3, eq6, eqpt, error_guard, run


class TestEq36Exec(TestCase):
    """
    Tests of the eleanor.kernel.eq36.exec module.
    """

    def test_error_guard_no_error_text(self) -> None:
        """
        Ensure error_guard is a no-op when no error marker is present.
        """
        self.assertIsNone(error_guard(b"all good", "eq3nr", RunCode.EQ3_ERROR))

    def test_error_guard_raises_with_and_without_fname(self) -> None:
        """
        Ensure error_guard raises Eq36Exception with expected message formatting.
        """
        with self.assertRaises(Eq36Exception) as cm:
            error_guard(b"Error - bad thing happened", "eq3nr", RunCode.EQ3_ERROR)
        self.assertEqual(cm.exception.code, RunCode.EQ3_ERROR)
        self.assertIn("eq3nr", str(cm.exception))

        with self.assertRaises(Eq36Exception) as cm2:
            error_guard(
                b"Error - bad file thing", "eq6", RunCode.EQ6_ERROR, fname="sample.6i"
            )
        self.assertEqual(cm2.exception.code, RunCode.EQ6_ERROR)
        self.assertIn('in file "sample.6i"', str(cm2.exception))

    def test_run_success(self) -> None:
        """
        Ensure run executes process and returns stdout/stderr on success.
        """
        process = SimpleNamespace(
            communicate=mock.Mock(return_value=(b"ok", b"")),
            returncode=0,
            kill=mock.Mock(),
        )
        with mock.patch("eleanor.kernel.eq36.exec.Popen", return_value=process):
            out, err = run("eq3nr", "data1", "input.3i", code=RunCode.EQ3_ERROR)
        self.assertEqual(out, b"ok")
        self.assertEqual(err, b"")

    def test_run_nonzero_returncode_raises(self) -> None:
        """
        Ensure run raises Eq36Exception when subprocess exits nonzero.
        """
        process = SimpleNamespace(
            communicate=mock.Mock(return_value=(b"ok", b"")),
            returncode=9,
            kill=mock.Mock(),
        )
        with mock.patch("eleanor.kernel.eq36.exec.Popen", return_value=process):
            with self.assertRaises(Eq36Exception) as cm:
                run("eq6", "data1", "input.6i", code=RunCode.EQ6_ERROR)
        self.assertEqual(cm.exception.code, 9)
        self.assertIn("unexpected error", str(cm.exception))

    def test_run_timeout_without_errors(self) -> None:
        """
        Ensure timeout without parsed errors raises timeout-specific Eq36Exception.
        """
        process = SimpleNamespace(
            communicate=mock.Mock(
                side_effect=[TimeoutExpired(cmd="eq6", timeout=1), (b"", b"")]
            ),
            returncode=0,
            kill=mock.Mock(),
        )
        with (
            mock.patch("eleanor.kernel.eq36.exec.Popen", return_value=process),
            mock.patch("eleanor.kernel.eq36.exec.error_guard", return_value=None),
        ):
            with self.assertRaises(Eq36Exception) as cm:
                run("eq6", "data1", "input.6i", timeout=1, code=RunCode.EQ6_ERROR)
        process.kill.assert_called_once()
        self.assertEqual(cm.exception.code, RunCode.EQ36_TIMEOUT)
        self.assertIn("timed out without errors", str(cm.exception))

    def test_run_timeout_with_errors(self) -> None:
        """
        Ensure timeout with parsed subprocess errors raises wrapped timeout-with-errors exception.
        """
        process = SimpleNamespace(
            communicate=mock.Mock(
                side_effect=[
                    TimeoutExpired(cmd="eq6", timeout=1),
                    (b"Error - fail", b""),
                ]
            ),
            returncode=0,
            kill=mock.Mock(),
        )
        with (
            mock.patch("eleanor.kernel.eq36.exec.Popen", return_value=process),
            mock.patch(
                "eleanor.kernel.eq36.exec.error_guard",
                side_effect=Eq36Exception("eq6 failed", code=RunCode.EQ6_ERROR),
            ),
        ):
            with self.assertRaises(Eq36Exception) as cm:
                run("eq6", "data1", "input.6i", timeout=1, code=RunCode.EQ6_ERROR)
        self.assertEqual(cm.exception.code, RunCode.EQ36_TIMEOUT)
        self.assertIn("timed out with errors", str(cm.exception))

    def test_wrapper_functions_call_run(self) -> None:
        """
        Ensure eqpt/eq3/eq6 wrappers delegate to run with expected command arguments.
        """
        with mock.patch(
            "eleanor.kernel.eq36.exec.run", return_value=(b"", b"")
        ) as run_mock:
            eqpt("sample.d0")
            eq3("sample.d1", "sample.3i", timeout=17)
            eq6("sample.d1", "sample.6i", timeout=18)

        run_mock.assert_any_call(
            "eqpt", "sample.d0", fname="sample.d0", code=RunCode.EQPT_ERROR
        )
        run_mock.assert_any_call(
            "eq3nr",
            "sample.d1",
            "sample.3i",
            timeout=None,
            fname="sample.3i",
            code=RunCode.EQ3_ERROR,
        )
        run_mock.assert_any_call(
            "eq6",
            "sample.d1",
            "sample.6i",
            timeout=18,
            fname="sample.6i",
            code=RunCode.EQ6_ERROR,
        )
