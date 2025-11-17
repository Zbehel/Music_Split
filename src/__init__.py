"""
Music Source Separator Package
"""

from .separator import MusicSeparator, get_separator, clear_cache, get_best_device

__version__ = "2.0.0"
__all__ = ["MusicSeparator", "get_separator", "clear_cache", "get_best_device"]