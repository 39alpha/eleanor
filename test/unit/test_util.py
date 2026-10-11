import datetime
import hashlib
import io
import os
from collections.abc import Iterator
from os.path import join
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import eleanor.util as util
import numpy as np
import pytest
from eleanor.exceptions import EleanorError
from eleanor.typing import ReadStream


class TestUtils(TestCase):
    """
    Tests of the eleanor.hanger.tool_room module
    """

    def test_canary(self) -> None:
        """
        Confirm that the test case is being run
        """
        self.assertTrue(True)

    def test_working_directory(self) -> None:
        """
        Ensure that :class:`WorkingDirectory` changes directory to the desired path and back again.
        """
        cwd = Path.cwd()
        new_dir = (cwd / "..").resolve()

        wd = util.WorkingDirectory("..")

        self.assertEqual(wd.path, new_dir)
        self.assertEqual(wd.cwd, cwd)

        with wd as new_cwd:
            self.assertEqual(new_cwd, new_dir)
            self.assertEqual(Path.cwd(), new_cwd)
            self.assertEqual(wd.path, cwd)

        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(wd.path, new_dir)
        self.assertEqual(wd.cwd, cwd)

    def test_working_directory_nonexistent_directory(self) -> None:
        """
        Ensure that if you try to switch to a non-existent directory, the properties of the
        :class:`WorkingDirectory` do not change.
        """
        cwd = Path.cwd()

        wd = util.WorkingDirectory("not-real")

        self.assertEqual(wd.path, cwd / "not-real")
        self.assertEqual(wd.cwd, cwd)

        with self.assertRaises(FileNotFoundError):
            with wd:
                pass

        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(wd.path, cwd / "not-real")
        self.assertEqual(wd.cwd, cwd)

    def test_working_directory_handles_error(self) -> None:
        """
        Ensure that if the :class:`WorkingDirectory` code block raises, we switch back to the
        previous working directory.
        """
        cwd = Path.cwd()

        wd = util.WorkingDirectory("..")

        self.assertEqual(wd.path, (cwd / "..").resolve())
        self.assertEqual(wd.cwd, cwd)

        with self.assertRaises(ValueError):
            with wd:
                raise ValueError("whomp")

        self.assertEqual(Path.cwd(), cwd)
        self.assertEqual(wd.path, (cwd / "..").resolve())
        self.assertEqual(wd.cwd, cwd)

    def test_working_directory_can_be_nested(self) -> None:
        """
        Ensure that the :class:`WorkingDirectory` context manager can be nested.
        """
        cwd0 = Path.cwd()
        with TemporaryDirectory() as root:
            root = Path(root).resolve()
            self.assertNotEqual(root, cwd0)
            (root / "abc").mkdir()
            with util.WorkingDirectory(root) as cwd1:
                self.assertEqual(Path.cwd(), root)
                self.assertEqual(cwd1, root)
                with util.WorkingDirectory("abc") as cwd2:
                    self.assertEqual(Path.cwd(), root / "abc")
                    self.assertEqual(cwd2, root / "abc")
                self.assertEqual(Path.cwd(), root)
            self.assertEqual(Path.cwd(), cwd0)

    def test_number_format_fmt(self) -> None:
        """
        Ensure that :class:`NumberFormat` formats values correctly and rejects invalid precision.
        """
        self.assertEqual(util.NumberFormat.FLOATING.fmt(np.float64(1.23456), 2), "1.23")
        self.assertEqual(util.NumberFormat.SCIENTIFIC.fmt(np.float64(123.0), 2), "1.23E+02")
        with self.assertRaises(EleanorError):
            _ = util.NumberFormat.FLOATING.fmt(np.float64(1.23), -1)

    def test_log_rng(self) -> None:
        """
        Ensure that :func:`log_rng` produces expected numeric outputs.
        """
        low, high = util.log_rng(np.float64(100.0), np.float64(0.1))
        self.assertAlmostEqual(low, np.log10(90.0))
        self.assertAlmostEqual(high, np.log10(110.0))

    def test_hash_file_and_hash_dir(self) -> None:
        """
        Ensure that file and directory hashes are deterministic and reflect content changes.
        """
        with TemporaryDirectory() as root:
            p1 = join(root, "a.txt")
            p2 = join(root, "b.txt")
            with open(p1, "wb") as f:
                f.write(b"abc")
            with open(p2, "wb") as f:
                f.write(b"def")

            expected = hashlib.sha256(b"abc").hexdigest()
            self.assertEqual(util.hash_file(p1), expected)

            h1 = util.hash_dir(root)
            h2 = util.hash_dir(root)
            self.assertEqual(h1, h2)

            with open(p2, "wb") as f:
                f.write(b"xyz")
            self.assertNotEqual(util.hash_dir(root), h1)

    def test_hash_dir_with_nested_subdirectory(self) -> None:
        """
        Ensure that :func:`hash_dir` recursively includes nested subdirectory contents.
        """
        with TemporaryDirectory() as root:
            sub = join(root, "sub")
            os.mkdir(sub)
            with open(join(sub, "nested.txt"), "wb") as f:
                f.write(b"nested")
            with open(join(root, "top.txt"), "wb") as f:
                f.write(b"top")

            h1 = util.hash_dir(root)
            with open(join(sub, "nested.txt"), "wb") as f:
                f.write(b"changed")
            h2 = util.hash_dir(root)
            self.assertNotEqual(h1, h2)

    def test_find_files_prefix_and_suffix(self) -> None:
        """
        Ensure that :func:`find_files` matches files correctly for both prefix and suffix modes.
        """
        with TemporaryDirectory() as root:
            root = Path(root)
            (root / "sub").mkdir()
            names = ["alpha.txt", "beta.txt", "a_config.json", "sub/alpha.cfg"]
            for name in names:
                path = root / name
                with open(path, "w") as f:
                    f.write("x")

            suffix_names, suffix_paths = util.find_files(".txt", location=root, str_loc="suffix")
            self.assertEqual(sorted(suffix_names), [Path("alpha.txt"), Path("beta.txt")])
            self.assertEqual(len(suffix_paths), 2)

            prefix_names, prefix_paths = util.find_files("alpha", location=root, str_loc="prefix")
            self.assertEqual(sorted(prefix_names), [Path("alpha.cfg"), Path("alpha.txt")])
            self.assertEqual(len(prefix_paths), 2)

            names0, paths0 = util.find_files("alpha", location=root, str_loc="middle")
            self.assertEqual(names0, [])
            self.assertEqual(paths0, [])

    def test_convert_to_number(self) -> None:
        """
        Ensure that :func:`convert_to_number` converts valid values and fails invalid ones.
        """
        self.assertEqual(util.convert_to_number("2"), 2)
        self.assertAlmostEqual(util.convert_to_number("2.5"), np.float64(2.5))
        with self.assertRaises(EleanorError):
            util.convert_to_number("not-a-number")

    def test_is_list_of(self) -> None:
        """
        Ensure that :func:`is_list_of` validates element types and None handling correctly.
        """
        self.assertTrue(util.is_list_of([1, 2, 3], int))
        self.assertFalse(util.is_list_of([1, "2", 3], int))
        self.assertFalse(util.is_list_of(None, int))

    def test_parse_date(self) -> None:
        """
        Ensure that :func:`parse_date` parses valid ISO strings and raises on invalid input.
        """
        self.assertEqual(util.parse_date("2025-01-02"), datetime.date(2025, 1, 2))
        parsed_dt = util.parse_date("2025-01-02T03:04:05")
        self.assertEqual(parsed_dt, datetime.datetime(2025, 1, 2, 3, 4, 5))
        with self.assertRaises(ValueError):
            util.parse_date("bad-date")

    def test_convert_to_number_numpy_floating_passthrough(self) -> None:
        """
        Ensure that existing numpy floating values pass through unchanged when already typed.
        """
        value = np.float64(1.25)
        result = util.convert_to_number(value)
        self.assertIsInstance(result, np.float64)


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        (util.NumberFormat.SCIENTIFIC, "1.23E+03"),
        (util.NumberFormat.FLOATING, "1234.57"),
        (util.NumberFormat.ADAPTIVE, "1.2e+03"),
    ],
)
def test_number_format_members(fmt: util.NumberFormat, expected: str) -> None:
    assert fmt.fmt(np.float64(1234.5678), precision=2) == expected


@pytest.mark.parametrize("fmt", list(util.NumberFormat))
def test_number_format_rejects_negative_precision(fmt: util.NumberFormat) -> None:
    with pytest.raises(EleanorError, match="invalid precision -1 < 0"):
        _ = fmt.fmt(np.float64(1.0), precision=-1)


@pytest.mark.parametrize(
    ("show_value", "show_type", "expected"),
    [
        (False, True, "port must be an integer, got str"),
        (True, False, "port must be an integer, got '5432'"),
        (True, True, "port must be an integer, got '5432' of type str"),
        (False, False, "port must be an integer"),
    ],
)
def test_raise_field_error_message(show_value: bool, show_type: bool, expected: str) -> None:
    with pytest.raises(EleanorError) as excinfo:
        util.raise_field_error("5432", "port", "must be an integer", show_value=show_value, show_type=show_type)
    assert str(excinfo.value) == expected


def test_raise_field_error_chains_error_context() -> None:
    cause = ValueError("bad")
    with pytest.raises(EleanorError) as excinfo:
        util.raise_field_error("x", "field", "is invalid", error_context=cause)
    assert excinfo.value.__cause__ is cause


def test_raise_field_error_keeps_implicit_context_without_error_context() -> None:
    with pytest.raises(EleanorError) as excinfo:
        try:
            raise ValueError("bad")
        except ValueError:
            util.raise_field_error("x", "field", "is invalid")
    assert isinstance(excinfo.value.__context__, ValueError)
    assert not excinfo.value.__suppress_context__


@pytest.mark.parametrize(
    ("parse", "kind"),
    [(util.require_uuid_id, "a UUID"), (util.require_int_id, "an integer")],
)
def test_require_id_reports_the_offending_value(parse: object, kind: str) -> None:
    assert callable(parse)
    with pytest.raises(EleanorError) as excinfo:
        _ = parse("not-an-id", "order")
    assert str(excinfo.value) == f"order id must be {kind}, got 'not-an-id'"
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_require_reports_only_the_missing_field() -> None:
    with pytest.raises(EleanorError) as excinfo:
        _ = util.require(None, "kernel")
    assert str(excinfo.value) == "kernel is required"


@pytest.mark.parametrize(
    ("check", "value", "expected"),
    [
        (util.require_int, "1", "field must be an integer, got str"),
        (util.require_opt_int, True, "field must be an integer or None, got bool"),
        (util.require_str, 1, "field must be a string, got int"),
        (util.require_opt_str, 1, "field must be a string or None, got int"),
        (util.require_path, 1, "field must be a string or Path, got int"),
        (util.require_opt_path, 1, "field must be a string, Path or None, got int"),
        (util.require_dict, [], "field must be a dictionary, got list"),
        (util.require_opt_dict, [], "field must be a dictionary or None, got list"),
        (util.require_float, "1.0", "field must be a floating-point number, got str"),
        (util.require_bool, 1, "field must be a boolean, got int"),
        (util.require_opt_bool, 1, "field must be a boolean or None, got int"),
        (util.guard_is_bool, 1, "field must be a boolean, got int"),
        (util.guard_is_float, "1.0", "field must be a floating-point number, got str"),
        (util.guard_is_int, 1.0, "field must be an integer, got float"),
        (util.guard_is_int_or_none, 1.0, "field must be an integer or None, got float"),
        (util.guard_is_str, 1, "field must be a string, got int"),
        (util.guard_is_str_or_none, 1, "field must be a string or None, got int"),
        (util.guard_is_path, "x", "field must be a Path, got str"),
        (util.guard_is_path_or_none, "x", "field must be a Path or None, got str"),
        (util.guard_is_dict, [], "field must be a dictionary, got list"),
        (util.guard_is_uuid, "x", "field must be a UUID, got str"),
        (util.guard_is_uuid_or_none, "x", "field must be a UUID or None, got str"),
    ],
)
def test_field_checks_report_expected_and_actual_type(check: object, value: object, expected: str) -> None:
    assert callable(check)
    with pytest.raises(EleanorError) as excinfo:
        _ = check(value, "field")
    assert str(excinfo.value) == expected


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (util.guard_is_instance, "field must have type Path, got str"),
        (util.guard_is_instance_or_none, "field must have type Path or None, got str"),
    ],
)
def test_instance_guards_report_expected_and_actual_type(check: object, expected: str) -> None:
    assert callable(check)
    with pytest.raises(EleanorError) as excinfo:
        _ = check("x", Path, "field")
    assert str(excinfo.value) == expected
