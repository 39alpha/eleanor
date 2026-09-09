import io
import sys
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from traceback import print_exception
from typing import Unpack

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.kernel.exceptions import EleanorKernelError
from eleanor.kernel.interface import AbstractKernel
from eleanor.output.interface import ChunkResult, ComputeResult, ErrorInfo, SinkBinding, SinkChunkResult
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
        bindings: Sequence[SinkBinding],
        sim_progress: ProgressHandle | None = None,
        out_progress: Mapping[str, ProgressHandle] | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> ChunkResult:
        """Run the kernel over ``points``, then reduce the results via every sink."""
        compute_results: list[ComputeResult] = []

        point_list = points if isinstance(points, list) else [points]

        for point in point_list:
            vs_point = self.work(point, *args, **kwargs)
            exception: Exception | None = vs_point.exception
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

        # Every sink prepares before any sink commits, so no sink can observe
        # the compute graph as another sink's commit left it.
        prepared_batches = [
            (binding, binding.sink.prepare_batch(binding.order_id, compute_results)) for binding in bindings
        ]

        results: list[SinkChunkResult] = []
        for binding, prepared in prepared_batches:
            if binding.commit_in_worker:
                progress = None if out_progress is None else out_progress.get(binding.name)
                outcomes = binding.sink.commit_batch(binding.order_id, prepared, progress=progress)
                results.append(SinkChunkResult(name=binding.name, outcomes=outcomes))
            else:
                results.append(SinkChunkResult(name=binding.name, prepared=prepared))

        return ChunkResult(point_count=len(point_list), sinks=results)

    def work(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> vs.Point:
        scratch = kwargs.get("scratch", False)
        verbose = kwargs.get("verbose", False)

        with TemporaryDirectory(prefix="eleanor_") as tempdir, WorkingDirectory(tempdir):
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
                if isinstance(e, EleanorKernelError):
                    vs_point.exit_code = e.code
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
