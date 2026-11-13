"""Locate or build the native runtime library and executable.

The CMake build is idempotent and fast when the runtime is current. Missing
tools and failed commands raise ``NativeBuildError`` with the captured output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .compiler import CompileResult, NativeBuildError


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
NATIVE_DIR = REPOSITORY_ROOT / "native"


def _is_source_checkout() -> bool:
    return (REPOSITORY_ROOT / "pyproject.toml").is_file()


def _default_build_dir() -> Path:
    """Use the checkout build directory or a writable temp directory.

    A wheel install has no writable repository root. The native sources are
    packaged under ``native/``, so the build cache moves to the system temp
    directory in that case.
    """
    if _is_source_checkout():
        return REPOSITORY_ROOT / "build" / "native"
    return Path(tempfile.gettempdir()) / "powang-native-build"


BUILD_DIR = Path(
    os.environ.get("POWANG_NATIVE_BUILD_DIR") or _default_build_dir()
)
INCLUDE_DIR = NATIVE_DIR / "include"

RUNTIME_LIBRARY = "libpwb_runtime.a"
RUNTIME_EXECUTABLE = "pwb_native.exe"
BUILD_TIMEOUT = 300.0


@dataclass(frozen=True)
class RuntimePaths:
    """Absolute paths to one built native runtime."""

    build_dir: Path
    include_dir: Path
    library: Path
    executable: Path


_RUNTIME_CACHE: RuntimePaths | None = None


def _require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise NativeBuildError(
            f"required build tool '{name}' was not found on PATH. "
            "Install cmake, ninja and g++ before building the native runtime."
        )


def _run_build_command(command: list[str]) -> None:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BUILD_TIMEOUT,
        )
    except FileNotFoundError as error:
        raise NativeBuildError(
            f"required build tool '{command[0]}' was not found on PATH"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise NativeBuildError(
            f"native build timed out after {BUILD_TIMEOUT:g} seconds: "
            f"{' '.join(command)}"
        ) from error
    duration = time.perf_counter() - started
    if completed.returncode != 0:
        result = CompileResult(
            ok=False,
            command=tuple(command),
            output=BUILD_DIR,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration=duration,
        )
        raise NativeBuildError(
            f"native build command failed: {' '.join(command)}", result,
        )


def _native_sources() -> list[Path]:
    """Return every source that must be older than the built library."""
    sources = [NATIVE_DIR / "CMakeLists.txt"]
    sources.extend((NATIVE_DIR / "include").rglob("*.hpp"))
    sources.extend((NATIVE_DIR / "src").rglob("*.cpp"))
    return [path for path in sources if path.is_file()]


def _runtime_is_current(library: Path | None) -> bool:
    """A cached runtime is current when no native source is newer."""
    if library is None or not library.is_file():
        return False
    try:
        library_mtime = library.stat().st_mtime_ns
        for source in _native_sources():
            if source.stat().st_mtime_ns > library_mtime:
                return False
    except OSError:
        return False
    return True


def _locate(name: str, preferred: Path) -> Path | None:
    if preferred.is_file():
        return preferred
    for candidate in sorted(BUILD_DIR.rglob(name)):
        if candidate.is_file():
            return candidate
    return None


def ensure_runtime(*, rebuild: bool = False) -> RuntimePaths:
    """Return the built runtime paths, configuring and building when needed."""
    global _RUNTIME_CACHE
    if (not rebuild and _RUNTIME_CACHE is not None
            and _runtime_is_current(_RUNTIME_CACHE.library)):
        return _RUNTIME_CACHE
    _require_tool("cmake")
    _require_tool("g++")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    configure_needed = rebuild or not (BUILD_DIR / "CMakeCache.txt").exists()
    if (not rebuild and _RUNTIME_CACHE is not None
            and not _runtime_is_current(_RUNTIME_CACHE.library)):
        # The cached library is older than a native source, so force a
        # configure step before the build.
        configure_needed = True
    if configure_needed:
        _require_tool("ninja")
        configure = [
            "cmake",
            "-S",
            str(NATIVE_DIR),
            "-B",
            str(BUILD_DIR),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_CXX_COMPILER=g++",
        ]
        if not _is_source_checkout():
            configure.append("-DPWB_BUILD_TESTS=OFF")
        _run_build_command(configure)
    _run_build_command(
        ["cmake", "--build", str(BUILD_DIR), "--config", "Release"]
    )
    library = _locate(RUNTIME_LIBRARY, BUILD_DIR / RUNTIME_LIBRARY)
    if library is None:
        raise NativeBuildError(
            f"native runtime library '{RUNTIME_LIBRARY}' is missing under "
            f"{BUILD_DIR}. Run the cmake build first."
        )
    executable = _locate(
        RUNTIME_EXECUTABLE, BUILD_DIR / RUNTIME_EXECUTABLE
    )
    if executable is None:
        executable = _locate("pwb_native", BUILD_DIR / "pwb_native")
    if executable is None:
        raise NativeBuildError(
            f"native executable '{RUNTIME_EXECUTABLE}' is missing under "
            f"{BUILD_DIR}. Run the cmake build first."
        )
    _RUNTIME_CACHE = RuntimePaths(
        build_dir=library.parent,
        include_dir=INCLUDE_DIR,
        library=library,
        executable=executable,
    )
    return _RUNTIME_CACHE
