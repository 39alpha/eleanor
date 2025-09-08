from multiprocessing import Process
from multiprocessing.managers import SyncManager
from queue import Queue

from .typing import Optional
from .util import Progress
from .variable_space import Point
from .yeoman import Yeoman


class YeomanActor(object):
    queue: Queue[Optional[Point]]
    process: Process
    yeoman: Yeoman
    progress: Optional[Progress]
    success_only_progress: bool

    def __init__(
        self,
        manager: SyncManager,
        *args,
        progress: Optional[Progress] = None,
        success_only_progress: bool = False,
        **kwargs,
    ):
        self.yeoman = Yeoman(*args, **kwargs)
        self.queue = manager.Queue()
        self.progress = progress
        self.success_only_progress = success_only_progress
        self.process = Process(target=self.listen)
        self.process.start()

    def listen(self):
        with self.yeoman as yeoman:
            while True:
                point = self.queue.get()
                if point is None:
                    self.queue.task_done()
                    break

                yeoman.write(point)

                show_progress = not self.success_only_progress or point.exit_code == 0
                if self.progress is not None and show_progress:
                    self.progress.queue.put_nowait(True)

                self.queue.task_done()

    def join(self):
        self.queue.join()
