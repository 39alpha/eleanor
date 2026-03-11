from collections import deque
from types import SimpleNamespace
from unittest import mock

from eleanor.config import DatabaseConfig
from eleanor.exceptions import EleanorException
from eleanor.sailor import Sailor

from .common import TestCase


class TestSailor(TestCase):
    """
    Tests of the eleanor.sailor module.
    """

    def test_dispatch_requires_config(self):
        """
        Ensure that :meth:`Sailor.dispatch` rejects missing database configuration.
        """
        sailor = Sailor(kernel=mock.Mock(), config=None)
        with self.assertRaises(EleanorException):
            sailor.dispatch([])

    def test_dispatch_list_points_writes_ids_and_progress(self):
        """
        Ensure that list dispatch writes all points and reports progress for each successful point.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sailor = Sailor(kernel=mock.Mock(), config=cfg)

        points = [SimpleNamespace(id=10, exit_code=0), SimpleNamespace(id=11, exit_code=0)]
        progress = mock.Mock()

        class FakeYeoman:
            def __init__(self, _config):
                self.write = mock.Mock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        yeoman = FakeYeoman(cfg)
        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=yeoman),
            mock.patch.object(Sailor, "work", side_effect=points) as work_mock,
        ):
            ids = sailor.dispatch([object(), object()], progress=progress, success_sampling=False)

        self.assertEqual(ids, [10, 11])
        self.assertEqual(work_mock.call_count, 2)
        self.assertEqual(yeoman.write.call_count, 2)
        progress.put.assert_has_calls([mock.call(True), mock.call(True)])

    def test_dispatch_success_sampling_filters_progress(self):
        """
        Ensure that success-sampling mode only reports progress for zero exit-code points.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sailor = Sailor(kernel=mock.Mock(), config=cfg)

        points = [SimpleNamespace(id=1, exit_code=0), SimpleNamespace(id=2, exit_code=1)]
        progress = mock.Mock()

        class FakeYeoman:
            def __init__(self, _config):
                self.write = mock.Mock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        yeoman = FakeYeoman(cfg)
        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=yeoman),
            mock.patch.object(Sailor, "work", side_effect=points),
        ):
            ids = sailor.dispatch([object(), object()], progress=progress, success_sampling=True)

        self.assertEqual(ids, [1, 2])
        progress.put.assert_called_once_with(True)

    def test_dispatch_single_point_and_missing_id_error(self):
        """
        Ensure that single-point dispatch returns one id and fails if inserted id is missing.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sailor = Sailor(kernel=mock.Mock(), config=cfg)

        class FakeYeoman:
            def __init__(self, _config):
                self.write = mock.Mock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        good = SimpleNamespace(id=7, exit_code=0)
        bad = SimpleNamespace(id=None, exit_code=0)

        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=FakeYeoman(cfg)),
            mock.patch.object(Sailor, "work", return_value=good),
        ):
            self.assertEqual(sailor.dispatch(object()), [7])

        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=FakeYeoman(cfg)),
            mock.patch.object(Sailor, "work", return_value=bad),
        ):
            with self.assertRaises(EleanorException):
                sailor.dispatch(object())

    def test_dispatch_list_missing_id_raises(self):
        """
        Ensure that list dispatch raises when any inserted point is missing an id.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sailor = Sailor(kernel=mock.Mock(), config=cfg)

        class FakeYeoman:
            def __init__(self, _config):
                self.write = mock.Mock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        bad = SimpleNamespace(id=None, exit_code=0)
        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=FakeYeoman(cfg)),
            mock.patch.object(Sailor, "work", return_value=bad),
        ):
            with self.assertRaises(EleanorException):
                sailor.dispatch([object()])

    def test_dispatch_single_point_reports_progress(self):
        """
        Ensure that single-point dispatch reports progress when requested.
        """
        cfg = DatabaseConfig(database="db", username="u", password="p")
        sailor = Sailor(kernel=mock.Mock(), config=cfg)
        progress = mock.Mock()

        class FakeYeoman:
            def __init__(self, _config):
                self.write = mock.Mock()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        good = SimpleNamespace(id=8, exit_code=0)
        with (
            mock.patch("eleanor.sailor.Yeoman", return_value=FakeYeoman(cfg)),
            mock.patch.object(Sailor, "work", return_value=good),
        ):
            ids = sailor.dispatch(object(), progress=progress)
        self.assertEqual(ids, [8])
        progress.put.assert_called_once_with(True)

    def test_work_success_and_scratch(self):
        """
        Ensure that successful work sets timing, outputs, and optional scratch collection.
        """
        kernel = mock.Mock()
        kernel.run.return_value = ["eq"]
        sailor = Sailor(kernel=kernel, config=None)

        vs_point = SimpleNamespace()
        out = sailor.work(vs_point, scratch=False)
        self.assertIs(out, vs_point)
        self.assertEqual(vs_point.exit_code, 0)
        self.assertEqual(vs_point.es_points, ["eq"])
        self.assertTrue(hasattr(vs_point, "start_date"))
        self.assertTrue(hasattr(vs_point, "complete_date"))
        kernel.copy_data.assert_not_called()

        kernel.reset_mock()
        vs_point2 = SimpleNamespace()
        out2 = sailor.work(vs_point2, scratch=True)
        self.assertIs(out2, vs_point2)
        kernel.copy_data.assert_called_once_with(vs_point2)
        self.assertTrue(hasattr(vs_point2, "scratch"))
        self.assertIsInstance(vs_point2.scratch.zip, bytes)

    def test_work_handles_eleonor_exception_and_generic_exception(self):
        """
        Ensure that work captures exceptions and sets exit codes for Eleanor and non-Eleanor errors.
        """
        kernel = mock.Mock()
        sailor = Sailor(kernel=kernel, config=None)

        kernel.run.side_effect = EleanorException("boom", code=9)
        vs_point = SimpleNamespace()
        out = sailor.work(vs_point, verbose=False)
        self.assertIs(out, vs_point)
        self.assertEqual(vs_point.exit_code, 9)
        self.assertIsInstance(vs_point.exception, EleanorException)
        kernel.copy_data.assert_called_with(vs_point)

        kernel.reset_mock()
        kernel.run.side_effect = RuntimeError("oops")
        vs_point2 = SimpleNamespace(exit_code=0)
        out2 = sailor.work(vs_point2, verbose=False)
        self.assertIs(out2, vs_point2)
        self.assertEqual(vs_point2.exit_code, -1)
        self.assertIsInstance(vs_point2.exception, RuntimeError)

    def test_work_verbose_prints_traceback_to_stderr(self):
        """
        Ensure that verbose mode prints traceback information to stderr on work failures.
        """
        kernel = mock.Mock()
        kernel.run.side_effect = RuntimeError("oops")
        sailor = Sailor(kernel=kernel, config=None)
        vs_point = SimpleNamespace(exit_code=0)

        with mock.patch("eleanor.sailor.print_exception") as print_mock:
            sailor.work(vs_point, verbose=True)

        self.assertGreaterEqual(print_mock.call_count, 2)

    def test_collect_scratch_success_and_failure(self):
        """
        Ensure scratch collection returns zipped bytes and falls back to null-byte payload on errors.
        """
        from tempfile import TemporaryDirectory
        from os.path import join

        with TemporaryDirectory() as tmp:
            with open(join(tmp, "a.txt"), "w") as f:
                f.write("abc")
            scratch = Sailor.collect_scratch(tmp)
            self.assertIsNotNone(scratch)
            self.assertTrue(isinstance(scratch.zip, bytes) and len(scratch.zip) > 0)

        with mock.patch("eleanor.sailor.zipfile.ZipFile", side_effect=RuntimeError("zip error")):
            scratch = Sailor.collect_scratch(".")
        self.assertEqual(scratch.zip, bytes("\0", "ascii"))
