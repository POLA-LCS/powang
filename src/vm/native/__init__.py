"""Python support code for the native C++17 runtime.

The N0 slice contains the checked-in opcode header generator, the in-memory
``temp.cpp`` source generator, the integrated g++ driver, the runtime paths
resolver and the executable loader. The native CLI lives in ``src/vm/cli.py``.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
