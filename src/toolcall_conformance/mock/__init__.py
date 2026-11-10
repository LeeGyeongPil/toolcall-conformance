"""Built-in mock server that reproduces known tool-call deviations on the wire."""

from .faults import MODES, Fault
from .server import MockServer

__all__ = ["MODES", "Fault", "MockServer"]
