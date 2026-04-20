from pkgutil import extend_path
from typing import TYPE_CHECKING

__path__ = list(extend_path(__path__, __name__))
from .version import *

__all__ = ['Eleanor']
if TYPE_CHECKING:
    from .eleanor import Eleanor


def __getattr__(name: str):
    if name == 'Eleanor':
        from .eleanor import Eleanor
        return Eleanor
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
