import re
from unittest import TestCase, mock

import eleanor.timing as timing_mod
from eleanor.timing import DispatchTimings


class _FakeClock:
    """Monotonic stand-in for ``time.perf_counter`` advanced by the test."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestDispatchTimingsDisabled(TestCase):
    """A disabled accumulator must never read the clock or record anything."""

    def test_disabled_context_managers_do_not_read_the_clock(self) -> None:
        timings = DispatchTimings()
        with mock.patch.object(
            timing_mod.time, "perf_counter", side_effect=AssertionError("clock read")
        ):
            with timings.measure():
                pass
            with timings.generating():
                pass
            with timings.submitting():
                pass
            with timings.waiting(in_flight=1, num_workers=4):
                pass
            with timings.writing(in_flight=1, num_workers=4):
                pass
            timings.count_chunk(10)

        self.assertEqual(timings.elapsed_s, 0.0)
        self.assertEqual(timings.generate_s, 0.0)
        self.assertEqual(timings.submit_s, 0.0)
        self.assertEqual(timings.wait_s, 0.0)
        self.assertEqual(timings.starved_s, 0.0)
        self.assertEqual(timings.write_s, 0.0)
        self.assertEqual(timings.chunks, 0)
        self.assertEqual(timings.points, 0)


class TestDispatchTimingsAccumulation(TestCase):
    """Each context manager accumulates into exactly one counter."""

    def setUp(self) -> None:
        self.clock = _FakeClock()
        patcher = mock.patch.object(timing_mod.time, "perf_counter", self.clock)
        _ = patcher.start()
        self.addCleanup(patcher.stop)
        self.timings = DispatchTimings(enabled=True)

    def test_each_category_accumulates_independently(self) -> None:
        with self.timings.generating():
            self.clock.advance(1.0)
        with self.timings.submitting():
            self.clock.advance(2.0)
        with self.timings.writing(in_flight=4, num_workers=4):
            self.clock.advance(4.0)

        self.assertEqual(self.timings.generate_s, 1.0)
        self.assertEqual(self.timings.submit_s, 2.0)
        self.assertEqual(self.timings.write_s, 4.0)
        self.assertEqual(self.timings.wait_s, 0.0)

    def test_categories_accumulate_across_repeated_use(self) -> None:
        for _ in range(3):
            with self.timings.generating():
                self.clock.advance(0.5)

        self.assertEqual(self.timings.generate_s, 1.5)

    def test_counters_still_accumulate_when_the_body_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.timings.writing(in_flight=4, num_workers=4):
                self.clock.advance(3.0)
                raise RuntimeError("boom")

        self.assertEqual(self.timings.write_s, 3.0)

    def test_measure_records_elapsed(self) -> None:
        with self.timings.measure():
            self.clock.advance(9.0)

        self.assertEqual(self.timings.elapsed_s, 9.0)

    def test_count_chunk_tracks_chunks_and_points(self) -> None:
        self.timings.count_chunk(4)
        self.timings.count_chunk(6)

        self.assertEqual(self.timings.chunks, 2)
        self.assertEqual(self.timings.points, 10)


class TestDispatchTimingsStarvation(TestCase):
    """``starved_s`` is the idleness lower bound and must be exact."""

    def setUp(self) -> None:
        self.clock = _FakeClock()
        patcher = mock.patch.object(timing_mod.time, "perf_counter", self.clock)
        _ = patcher.start()
        self.addCleanup(patcher.stop)
        self.timings = DispatchTimings(enabled=True)

    def test_wait_with_fewer_chunks_than_workers_is_charged(self) -> None:
        with self.timings.waiting(in_flight=3, num_workers=4):
            self.clock.advance(2.0)

        self.assertEqual(self.timings.wait_s, 2.0)
        self.assertEqual(self.timings.starved_s, 2.0)

    def test_wait_with_enough_chunks_is_not_charged(self) -> None:
        with self.timings.waiting(in_flight=4, num_workers=4):
            self.clock.advance(2.0)

        self.assertEqual(self.timings.wait_s, 2.0)
        self.assertEqual(self.timings.starved_s, 0.0)

    def test_a_write_that_drains_the_pool_is_charged(self) -> None:
        """Serial-sink worker idleness accrues during the write, not the wait.

        The parent is not blocked on the executor at all here -- it is inside
        ``write_batch`` with less work outstanding than there are workers.
        Classifying only wait time would report zero.
        """
        with self.timings.writing(in_flight=1, num_workers=4):
            self.clock.advance(9.0)

        self.assertEqual(self.timings.write_s, 9.0)
        self.assertEqual(self.timings.wait_s, 0.0)
        self.assertEqual(self.timings.starved_s, 9.0)

    def test_a_write_with_the_pool_still_loaded_is_not_charged(self) -> None:
        with self.timings.writing(in_flight=10, num_workers=4):
            self.clock.advance(9.0)

        self.assertEqual(self.timings.write_s, 9.0)
        self.assertEqual(self.timings.starved_s, 0.0)

    def test_starvation_accumulates_across_both_wait_and_write(self) -> None:
        with self.timings.waiting(in_flight=1, num_workers=4):
            self.clock.advance(2.0)
        with self.timings.writing(in_flight=1, num_workers=4):
            self.clock.advance(3.0)

        self.assertEqual(self.timings.starved_s, 5.0)

    def test_starvation_is_a_strict_subset_of_wait_plus_write(self) -> None:
        with self.timings.waiting(in_flight=8, num_workers=4):
            self.clock.advance(5.0)
        with self.timings.waiting(in_flight=1, num_workers=4):
            self.clock.advance(3.0)

        self.assertEqual(self.timings.wait_s, 8.0)
        self.assertEqual(self.timings.starved_s, 3.0)


class TestDispatchTimingsDerivedFields(TestCase):
    """``accounted_s`` / ``unaccounted_s`` must not double-count starvation."""

    def test_accounted_excludes_starvation(self) -> None:
        timings = DispatchTimings(
            enabled=True,
            generate_s=1.0,
            submit_s=2.0,
            wait_s=4.0,
            starved_s=3.0,
            write_s=8.0,
            elapsed_s=16.0,
        )

        self.assertEqual(timings.accounted_s, 15.0)
        self.assertEqual(timings.unaccounted_s, 1.0)

    def test_unaccounted_is_floored_at_zero(self) -> None:
        timings = DispatchTimings(enabled=True, write_s=5.0, elapsed_s=1.0)

        self.assertEqual(timings.unaccounted_s, 0.0)


class TestDispatchTimingsSummary(TestCase):
    """The rendered table is user-facing; keep it parseable and safe."""

    def test_summary_reports_every_category_and_the_totals(self) -> None:
        timings = DispatchTimings(
            enabled=True,
            generate_s=1.0,
            submit_s=2.0,
            wait_s=4.0,
            starved_s=3.0,
            write_s=2.0,
            chunks=7,
            points=70,
            elapsed_s=10.0,
        )

        summary = timings.summary()

        self.assertIn("70 point(s) in 7 chunk(s)", summary)
        self.assertIn("10.00s wall clock", summary)
        for label in ("generate", "submit", "wait", "write", "unaccounted", "starved"):
            self.assertIn(label, summary)
        # Percentages are of elapsed: wait is 4/10, starved 3/10.
        self.assertIn("40.0%", summary)
        self.assertIn("30.0%", summary)

    def test_summary_does_not_divide_by_zero_on_an_empty_run(self) -> None:
        summary = DispatchTimings(enabled=True).summary()

        self.assertIn("0 point(s) in 0 chunk(s)", summary)
        self.assertIn("--", summary)

    def test_summary_numeric_columns_are_aligned(self) -> None:
        timings = DispatchTimings(enabled=True, wait_s=4.0, starved_s=3.0, elapsed_s=10.0)

        # Anchor on the numeric field itself, not on a literal "s " -- some
        # labels ("idle workers") contain that substring. The section rule
        # carries no number and is skipped.
        matches = [
            (row, re.search(r"\d+\.\d\ds", row)) for row in timings.summary().splitlines()[1:]
        ]
        numeric = [(row, match) for row, match in matches if match is not None]
        columns = {match.end() for _row, match in numeric}

        self.assertEqual(len(numeric), 6, "expected six numeric rows")
        self.assertEqual(len(columns), 1, f"misaligned seconds column: {[r for r, _ in numeric]}")
