"""Compatibility wrapper for historical imports.

This project keeps the RMVPE implementation under infer.lib.rmvpe, but older code
still imports it as infer.rmvpe. Re-export the implementation here so both import
styles work without changing the rest of the codebase.
"""

from infer.lib.rmvpe import *  # noqa: F401,F403
