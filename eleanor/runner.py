import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from traceback import print_exception
from typing import Unpack

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.exceptions import EleanorException
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.interface import AbstractKernel
from eleanor.output.interface import AbstractOutputSink, ComputeResult, ErrorInfo, WriteOutcome
from eleanor.progress import ProgressHandle
from eleanor.typing import EleanorKwargs, StrPath
from eleanor.util import WorkingDirectory


class Runner:
    kernel: AbstractKernel

    def __init__(self, kernel: AbstractKernel) -> None:
        self.kernel = kernel

    def dispatch(
        self,
        points: vs.Point | list[vs.Point],
        *args: object,
        sink: AbstractOutputSink | None = None,
        order_id: int | None = None,
        sim_progress: ProgressHandle | None = None,
        out_progress: ProgressHandle | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[ComputeResult] | list[WriteOutcome]:
        """Run the kernel over ``points`` and, if ``sink`` is provided, write the
        resulting :class:`ComputeResult` payloads through it in-process.

        When a ``sink`` is passed, :meth:`OutputSink.write_batch` runs inside
        the worker and the return value is the resulting
        :class:`WriteOutcome` list. Callers should only supply a ``sink`` that
        returns ``True`` from :meth:`OutputSink.supports_worker_writes`.

        When ``sim_progress`` is supplied, ``tick()`` is called once per point
        as soon as its kernel compute step returns, giving single-point
        precision on the simulation bar. When ``out_progress`` is supplied and
        a ``sink`` is active, the handle is forwarded to
        :meth:`OutputSink.write_batch` so the sink can report per-row (or
        per-batch) write progress at whatever cadence suits its storage
        model.
        """
        compute_results: list[ComputeResult] = []

        point_list: list[vs.Point]
        if isinstance(points, list):
            point_list = points
        else:
            point_list = [points]

        for point in point_list:
            vs_point = self.work(point, *args, **kwargs)
            exception: Exception | None = getattr(vs_point, "exception", None)
            error = None if exception is None else ErrorInfo.from_exception(exception)
            if exception is not None:
                vs_point.exception = None

            compute_results.append(
                ComputeResult(
                    point=vs_point,
                    error=error,
                ),
            )

            if sim_progress is not None:
                sim_progress.tick()

        if sink is not None:
            if order_id is None:
                raise EleanorException("Runner.dispatch requires order_id when sink is provided")
            return sink.write_batch(order_id, compute_results, progress=out_progress)
        return compute_results

    def work(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> vs.Point:
        scratch = kwargs.get("scratch", False)
        verbose = kwargs.get("verbose", False)

        with TemporaryDirectory(prefix="eleanor_") as tempdir:
            with WorkingDirectory(tempdir):
                vs_point.start_date = datetime.now()
                es_points: list[es.Point] = []
                try:
                    es_points = self.kernel.run(vs_point, *args, **kwargs)
                    if scratch:
                        self.kernel.copy_data(vs_point)
                        vs_point.scratch = Runner.collect_scratch(tempdir)
                    vs_point.exit_code = 0
                except Exception as e:
                    self.kernel.copy_data(vs_point)
                    with Path("traceback.txt").open("w") as file:
                        print_exception(e, file=file)
                    if verbose:
                        print_exception(e, file=sys.stderr)
                    vs_point.scratch = Runner.collect_scratch(tempdir)
                    vs_point.exception = e
                    if isinstance(e, EleanorKernelException):
                        code = getattr(e, "code", None)
                        vs_point.exit_code = code if isinstance(code, int) else -1
                    else:
                        vs_point.exit_code = -1

                vs_point.es_points = es_points
                vs_point.complete_date = datetime.now()

                return vs_point

    @staticmethod
    def collect_scratch(dir: StrPath) -> vs.Scratch | None:
        try:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
                for filename in Path(dir).iterdir():
                    zip.write(filename, filename.name)
            return vs.Scratch(zip=buffer.getvalue())
        except Exception:
            return vs.Scratch(zip=bytes("\0", "ascii"))
