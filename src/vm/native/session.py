"""Shared file setup and bundle build for the native file path.

The native runtime has no source parser or module loader. Everything an
imported module needs is compiled here, on the Python side, and carried in the
``PWBB`` bundle before the state is closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ...error import PowangError
from ...config import load_config, load_project_config
from ...pkg.installer import load_package_config, require_packages_ready
from ...runtime import get_file_content
from ...state import fresh_state, set_state
from ..compiler import compile_source
from ..image import ProgramImage
from .bundle import build_bundle
from .loader import NativeRunResult, run_native


@dataclass
class NativeFileSession:
    """One compiled entry image plus the bundle built from its graph."""

    state: Any
    image: ProgramImage
    bundle: bytes
    entry_path: Path


def prepare_state(path: str | Path) -> Any:
    """Create the state used by the native file path."""
    state = fresh_state()
    state.engine = "vm"
    path_text = str(path)
    if not load_project_config(state, path_text):
        load_config(state, path_text)
    load_package_config(state, path_text)
    require_packages_ready(state)
    state.paths["RELATIVE"] = Path(path).resolve()
    state.paths["ABSOLUTE"] = Path(__file__).resolve().parents[3] / "powang.py"
    return state


def compile_native_file(
    path: str | Path,
    *,
    check: bool = True,
) -> NativeFileSession:
    """Compile a file and build its module bundle while the state is live."""
    entry_path = Path(path).resolve()
    state = prepare_state(path)
    set_state(state)
    try:
        content = get_file_content(str(path))
        try:
            image = compile_source(
                content,
                path=path,
                module_name=Path(path).stem,
                check=check,
                state=state,
            )
        except PowangError as error:
            ## run_program gives an entry compile or check error the same
            ## top-level line as a runtime error.
            if error.line is None:
                raise error.with_line(
                    content.count("\n") + 1) from None
            raise
        bundle = build_bundle(image, state)
    finally:
        state.close()
    return NativeFileSession(
        state=state,
        image=image,
        bundle=bundle,
        entry_path=entry_path,
    )


def run_native_file(
    path: str | Path,
    args: Sequence[str] = (),
    *,
    input_text: str | None = None,
    timeout: float = 60.0,
) -> NativeRunResult:
    """Compile and run one Powang file on the native runtime."""
    session = compile_native_file(path)
    return run_native(
        session.image,
        args,
        input_text=input_text,
        timeout=timeout,
        bundle=session.bundle,
        use_cache=True,
    )
