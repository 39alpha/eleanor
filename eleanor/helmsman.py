import os
from multiprocessing import Pool

from .kernel.interface import AbstractKernel
from .models import VSPoint
from .sailor import sailor
from .yeoman import Yeoman


class Helmsman:
    kernel: AbstractKernel

    def __init__(self, kernel: AbstractKernel):
        self.kernel = kernel

    def __call__(self, vs_point: VSPoint, *args, **kwargs):
        with Yeoman() as yeoman:
            sailor(self.kernel, yeoman, vs_point, *args, **kwargs)
            yeoman.commit()

    def run(self, vs_points: list[VSPoint], *args, num_cores: int | None = os.cpu_count(), **kwargs):
        N = len(vs_points)
        if num_cores is None or num_cores == 1:
            for vs_point in vs_points:
                self(vs_point, *args, **kwargs)
        else:
            with Pool(processes=num_cores - 1, initializer=Yeoman.dispose) as pool:
                pool.starmap(self, zip(vs_points, [args] * N, [kwargs] * N))
