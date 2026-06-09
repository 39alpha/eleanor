import io
from typing import cast
from unittest import TestCase, mock

from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.util import field_as_float, get_field, read_pickup_lines
from eleanor.kernel.exceptions import EleanorKernelException


class TestEq36Util(TestCase):
    """
    Tests of the eleanor.kernel.eq36.util module.
    """

    def test_get_field_and_field_as_float(self) -> None:
        """
        Ensure field extraction and float parsing support expected EQ36 formats.
        """
        self.assertEqual(get_field("a b c", 1), "b")
        self.assertEqual(field_as_float("1.23+04"), 1.23e04)
        self.assertEqual(field_as_float("-2.5E-02"), -2.5e-02)
        with self.assertRaises(EleanorKernelException):
            _ = field_as_float("not-a-number")

    def test_read_pickup_lines_variants(self) -> None:
        """
        Ensure pickup line reading supports handles/paths/default and errors on missing separators.
        """
        with mock.patch(
            "eleanor.kernel.eq36.util.read_pickup_lines", return_value=["x"]
        ) as rl:
            self.assertEqual(read_pickup_lines(None), ["x"])
            rl.assert_called_once_with("problem.3p")

        handle = io.StringIO("head\n*---\nline1\nline2\n")
        self.assertEqual(
            read_pickup_lines(cast(io.TextIOWrapper, cast(object, handle))),
            ["line1\n", "line2\n"],
        )

        with mock.patch(
            "builtins.open", return_value=io.StringIO("head\n*---\nline1\n")
        ):
            self.assertEqual(read_pickup_lines("file.3p"), ["line1\n"])

        with self.assertRaises(EleanorKernelException) as cm:
            _ = read_pickup_lines(
                cast(io.TextIOWrapper, cast(object, io.StringIO("no separator\n")))
            )
        self.assertEqual(cm.exception.code, RunCode.FILE_ERROR_3P)

        with mock.patch("builtins.open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorKernelException) as cm2:
                _ = read_pickup_lines("missing.3p")
        self.assertEqual(cm2.exception.code, RunCode.FILE_ERROR_3P)

    def test_read_pickup_lines_handle_read_raises_filenotfound(self) -> None:
        """
        Ensure handle-based read failures are wrapped as EleanorKernelException.
        """
        handle = mock.Mock()
        handle.readlines.side_effect = FileNotFoundError("missing")
        with self.assertRaises(EleanorKernelException) as cm:
            _ = read_pickup_lines(handle)
        self.assertEqual(cm.exception.code, RunCode.FILE_ERROR_3P)

    def test_read_pickup_lines_separator_at_end_returns_empty_payload(self) -> None:
        """
        Ensure pickup parsing returns empty content when separator is the final line.
        """
        handle = io.StringIO("header\n*---\n")
        self.assertEqual(
            read_pickup_lines(cast(io.TextIOWrapper, cast(object, handle))), []
        )
