import datetime
import hashlib
import os
from os.path import join
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import eleanor.util as util
import numpy as np
from eleanor.exceptions import EleanorError


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
            root = Path(root)
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
        self.assertEqual(
            util.NumberFormat.SCIENTIFIC.fmt(np.float64(123.0), 2), "1.23E+02"
        )
        with self.assertRaises(EleanorError):
            _ = util.NumberFormat.FLOATING.fmt(np.float64(1.23), -1)

    def test_log_rng_and_norm_list(self) -> None:
        """
        Ensure that :func:`log_rng` and :func:`norm_list` produce expected numeric outputs.
        """
        low, high = util.log_rng(np.float64(100.0), np.float64(0.1))
        self.assertAlmostEqual(low, np.log10(90.0))
        self.assertAlmostEqual(high, np.log10(110.0))

        normalized = util.norm_list(np.array([2.0, 4.0, 6.0]))
        self.assertEqual(normalized, [0.0, 0.5, 1.0])

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

            suffix_names, suffix_paths = util.find_files(
                ".txt", location=root, str_loc="suffix"
            )
            self.assertEqual(
                sorted(suffix_names), [Path("alpha.txt"), Path("beta.txt")]
            )
            self.assertEqual(len(suffix_paths), 2)

            prefix_names, prefix_paths = util.find_files(
                "alpha", location=root, str_loc="prefix"
            )
            self.assertEqual(
                sorted(prefix_names), [Path("alpha.cfg"), Path("alpha.txt")]
            )
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
        self.assertTrue(util.is_list_of([1, None, 3], int, allowNone=True))
        self.assertFalse(util.is_list_of([1, "2", 3], int))
        self.assertTrue(util.is_list_of(None, int, allowNone=True))
        self.assertFalse(util.is_list_of(None, int, allowNone=False))

    def test_parse_date(self) -> None:
        """
        Ensure that :func:`parse_date` parses valid ISO strings and raises on invalid input.
        """
        self.assertEqual(util.parse_date("2025-01-02"), datetime.date(2025, 1, 2))
        parsed_dt = util.parse_date("2025-01-02T03:04:05")
        self.assertEqual(parsed_dt, datetime.datetime(2025, 1, 2, 3, 4, 5))
        with self.assertRaises(ValueError):
            util.parse_date("bad-date")

    def test_chunks(self) -> None:
        """
        Ensure that :func:`chunks` partitions lists correctly and errors on invalid divisors.
        """
        self.assertEqual(list(util.chunks([1, 2, 3, 4, 5], 2)), [[1, 2, 3], [4, 5]])
        self.assertEqual(list(util.chunks([1, 2, 3], 5)), [[1], [2], [3]])
        with self.assertRaises(ZeroDivisionError):
            list(util.chunks([1, 2, 3], 0))

    def test_mapreduce(self) -> None:
        """
        Ensure that :func:`mapreduce` applies the mapper and reducer over the provided iterable.
        """
        value = util.mapreduce(lambda x: x * x, lambda a, b: a + b, [1, 2, 3], 0)
        self.assertEqual(value, 14)

    def test_convert_to_number_numpy_floating_passthrough(self) -> None:
        """
        Ensure that existing numpy floating values pass through unchanged when already typed.
        """
        value = np.float64(1.25)
        result = util.convert_to_number(value)
        self.assertIsInstance(result, np.float64)

    def test_is_list_of_with_tuple_and_allow_none(self) -> None:
        """
        Ensure that :func:`is_list_of` accepts tuple type constraints with optional None values.
        """
        self.assertTrue(util.is_list_of([1, None, 2.0], (int, float), allowNone=True))
