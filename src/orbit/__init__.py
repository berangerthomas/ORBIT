"""
ORBIT — Organized Repositories Based on Images Timing.

Organize photos into structured directories based on EXIF metadata.
"""

__version__ = "0.1.0"

from orbit.core import Orbit
from orbit.errors import OrbitResult, ProcessingError

__all__ = ["Orbit", "OrbitResult", "ProcessingError"]
