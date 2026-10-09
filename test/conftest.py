"""Session-wide isolation from the developer's eleanor environment.

``config_options`` resolves the default ``--config`` from ``$XDG_CONFIG_HOME``
when ``eleanor.cli`` is imported, so the environment has to be scrubbed here,
before any test module is collected, rather than in a fixture.
"""

import os
import shutil
import tempfile

_XDG_CONFIG_HOME = tempfile.mkdtemp(prefix="eleanor-test-xdg-")
os.environ["XDG_CONFIG_HOME"] = _XDG_CONFIG_HOME
for _name in ("ELEANOR_CONFIG", "ELEANOR_DATABASE"):
    _ = os.environ.pop(_name, None)


def pytest_unconfigure() -> None:
    shutil.rmtree(_XDG_CONFIG_HOME, ignore_errors=True)
