import pkgutil
from typing import cast

__path__ = cast(list[str], pkgutil.extend_path(__path__, __name__))
