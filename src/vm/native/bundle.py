"""Deterministic PWBB bundle builder for the native runtime.

The bundle carries the entry PWB1 image, its PWBM metadata and, from N4.1b,
every reachable imported module image. The native runtime parses the bundle
and runs the entry image. The raw single-image path stays available.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..image import ProgramImage
from .meta import build_meta, parse_meta


BUNDLE_MAGIC = b"PWBB"
BUNDLE_VERSION = 1
BUNDLE_FLAG_PROJECT = 1 << 0

_EXPORT_KINDS: dict[str, int] = {
    "variable": 0,
    "function": 1,
    "type": 2,
}
_EXPORT_KIND_NAMES: dict[int, str] = {
    value: key for key, value in _EXPORT_KINDS.items()
}


@dataclass(frozen=True)
class BundleImport:
    image_module_index: int
    target_module_id: int
    alias: str
    wildcard: bool
    explicit_alias: bool


@dataclass(frozen=True)
class BundleModule:
    module_id: int
    name: str
    path: str
    identity: str
    image_module_index: int
    bind_project: bool
    status: int
    image: bytes
    meta: bytes
    imports: tuple[BundleImport, ...]
    exports: tuple[tuple[str, str], ...]
    error_kind: str = ""
    error_message: str = ""
    error_text: str = ""


@dataclass(frozen=True)
class BundleProject:
    modules: tuple[str, ...]
    paths: tuple[str, ...]
    log_level: str
    allow_system: bool
    engine: str


@dataclass(frozen=True)
class Bundle:
    entry_module: int
    entry_path: str
    entry_source_line_count: int
    modules: tuple[BundleModule, ...]
    project: BundleProject | None
    digest: bytes

    def to_bytes(self) -> bytes:
        """Serialize this bundle deterministically."""
        payload = bytearray()
        payload += BUNDLE_MAGIC
        _u16(payload, BUNDLE_VERSION)
        _u16(payload, BUNDLE_FLAG_PROJECT if self.project is not None else 0)
        _u32(payload, self.entry_module)
        _u32(payload, len(self.modules))
        _string(payload, self.entry_path)
        _u32(payload, self.entry_source_line_count)
        if self.project is not None:
            _write_project(payload, self.project)
        for module in self.modules:
            _write_module(payload, module)
        digest = hashlib.sha256(payload).digest()
        payload += digest
        return bytes(payload)


def _u8(out: bytearray, value: int) -> None:
    out += struct.pack("<B", value & 0xFF)


def _u16(out: bytearray, value: int) -> None:
    out += struct.pack("<H", value)


def _u32(out: bytearray, value: int) -> None:
    out += struct.pack("<I", value)


def _string(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    _u32(out, len(raw))
    out += raw


def _bytes(out: bytearray, data: bytes) -> None:
    _u32(out, len(data))
    out += data


def _write_project(out: bytearray, project: BundleProject) -> None:
    _u32(out, len(project.modules))
    for name in project.modules:
        _string(out, name)
    _u32(out, len(project.paths))
    for path in project.paths:
        _string(out, path)
    _string(out, project.log_level)
    _u8(out, 1 if project.allow_system else 0)
    out += b"\x00\x00\x00"
    _string(out, project.engine)


def _write_module(out: bytearray, module: BundleModule) -> None:
    _u32(out, module.module_id)
    _u32(out, module.image_module_index)
    _u8(out, module.status)
    _u8(out, 1 if module.bind_project else 0)
    out += b"\x00\x00"
    _string(out, module.name)
    _string(out, module.path)
    _string(out, module.identity)
    if module.status == 0:
        _bytes(out, module.image)
        _bytes(out, module.meta)
        _u32(out, len(module.imports))
        for item in module.imports:
            _u32(out, item.image_module_index)
            _u32(out, item.target_module_id)
            flags = (1 if item.wildcard else 0) | (
                2 if item.explicit_alias else 0
            )
            _u8(out, flags)
            out += b"\x00\x00\x00"
            _string(out, item.alias)
        _u32(out, len(module.exports))
        for name, kind in module.exports:
            _string(out, name)
            _u8(out, _EXPORT_KINDS[kind])
        return
    _string(out, module.error_kind)
    _string(out, module.error_message)
    _string(out, module.error_text)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, count: int, what: str) -> bytes:
        if count < 0 or self.offset + count > len(self.data):
            raise ValueError(
                f"truncated PWBB bundle while reading {what} "
                f"at offset {self.offset}"
            )
        chunk = self.data[self.offset : self.offset + count]
        self.offset += count
        return chunk

    def u8(self, what: str) -> int:
        return struct.unpack("<B", self.take(1, what))[0]

    def u16(self, what: str) -> int:
        return struct.unpack("<H", self.take(2, what))[0]

    def u32(self, what: str) -> int:
        return struct.unpack("<I", self.take(4, what))[0]

    def string(self, what: str) -> str:
        raw = self.take(self.u32(f"{what} length"), what)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"invalid UTF-8 in {what}: {error}") from error

    def bytes(self, what: str) -> bytes:
        return self.take(self.u32(f"{what} length"), what)

    def remaining(self) -> int:
        return len(self.data) - self.offset


def build_bundle(image: ProgramImage, state: Any = None) -> bytes:
    """Build the PWBB payload for one entry image and its module graph."""
    return build_bundle_from_image(image, state).to_bytes()


def build_bundle_from_image(
    image: ProgramImage, state: Any = None
) -> Bundle:
    """Build the structured bundle used by tests and diagnostics."""
    del state
    module = image.module_info(image.entry_module)
    entry = BundleModule(
        module_id=0,
        name=module.name,
        path=module.path,
        identity=module.path,
        image_module_index=image.entry_module,
        bind_project=False,
        status=0,
        image=image.to_bytes(),
        meta=build_meta(image),
        imports=(),
        exports=tuple(module.exports),
    )
    return Bundle(
        entry_module=0,
        entry_path=module.path,
        entry_source_line_count=0,
        modules=(entry,),
        project=None,
        digest=b"",
    )


def parse_bundle(data: bytes) -> Bundle:
    """Parse a PWBB payload for tests and diagnostics."""
    if len(data) < 32:
        raise ValueError("PWBB bundle is shorter than its digest")
    payload = data[:-32]
    digest = data[-32:]
    if hashlib.sha256(payload).digest() != digest:
        raise ValueError("PWBB bundle digest mismatch")
    reader = _Reader(payload)
    if reader.take(4, "magic") != BUNDLE_MAGIC:
        raise ValueError("invalid PWBB magic")
    version = reader.u16("version")
    if version != BUNDLE_VERSION:
        raise ValueError(f"unsupported PWBB version: {version}")
    flags = reader.u16("flags")
    entry_module = reader.u32("entry module")
    module_count = reader.u32("module count")
    entry_path = reader.string("entry path")
    entry_source_line_count = reader.u32("entry source line count")
    project = None
    if flags & BUNDLE_FLAG_PROJECT:
        modules = tuple(
            reader.string("project module")
            for _ in range(reader.u32("project module count"))
        )
        paths = tuple(
            reader.string("project path")
            for _ in range(reader.u32("project path count"))
        )
        log_level = reader.string("project log level")
        allow_system = bool(reader.u8("project allow system"))
        reader.take(3, "project reserved")
        engine = reader.string("project engine")
        project = BundleProject(
            modules, paths, log_level, allow_system, engine
        )
    modules: list[BundleModule] = []
    for index in range(module_count):
        module_id = reader.u32("module id")
        if module_id != index:
            raise ValueError(
                f"PWBB module id {module_id} does not equal index {index}"
            )
        image_module_index = reader.u32("module image index")
        status = reader.u8("module status")
        bind_project = bool(reader.u8("module bind project"))
        reader.take(2, "module reserved")
        name = reader.string("module name")
        path = reader.string("module path")
        identity = reader.string("module identity")
        if status == 0:
            image = reader.bytes("module image")
            meta = reader.bytes("module metadata")
            _validate_module(image, meta, name)
            imports = tuple(
                _read_import(reader)
                for _ in range(reader.u32("module import count"))
            )
            exports = tuple(
                (
                    reader.string("module export name"),
                    _read_export_kind(reader),
                )
                for _ in range(reader.u32("module export count"))
            )
            modules.append(BundleModule(
                module_id=module_id,
                name=name,
                path=path,
                identity=identity,
                image_module_index=image_module_index,
                bind_project=bind_project,
                status=status,
                image=image,
                meta=meta,
                imports=imports,
                exports=exports,
            ))
            continue
        error_kind = reader.string("module error kind")
        error_message = reader.string("module error message")
        error_text = reader.string("module error text")
        modules.append(BundleModule(
            module_id=module_id,
            name=name,
            path=path,
            identity=identity,
            image_module_index=image_module_index,
            bind_project=bind_project,
            status=status,
            image=b"",
            meta=b"",
            imports=(),
            exports=(),
            error_kind=error_kind,
            error_message=error_message,
            error_text=error_text,
        ))
    if reader.remaining() != 0:
        raise ValueError(
            f"trailing bytes in PWBB bundle: {reader.remaining()}"
        )
    if entry_module >= len(modules):
        raise ValueError("PWBB entry module is out of range")
    return Bundle(
        entry_module=entry_module,
        entry_path=entry_path,
        entry_source_line_count=entry_source_line_count,
        modules=tuple(modules),
        project=project,
        digest=digest,
    )


def _read_import(reader: _Reader) -> BundleImport:
    image_module_index = reader.u32("import image module index")
    target_module_id = reader.u32("import target module id")
    flags = reader.u8("import flags")
    reader.take(3, "import reserved")
    alias = reader.string("import alias")
    return BundleImport(
        image_module_index=image_module_index,
        target_module_id=target_module_id,
        alias=alias,
        wildcard=bool(flags & 1),
        explicit_alias=bool(flags & 2),
    )


def _read_export_kind(reader: _Reader) -> str:
    value = reader.u8("export kind")
    kind = _EXPORT_KIND_NAMES.get(value)
    if kind is None:
        raise ValueError(f"unknown PWBB export kind: {value}")
    return kind


def _validate_module(image: bytes, meta: bytes, name: str) -> None:
    parsed = ProgramImage.from_bytes(image)
    if parsed.format_version != ProgramImage().format_version:
        raise ValueError(f"module '{name}' has an unsupported image version")
    block = parse_meta(meta)
    expected = hashlib.sha256(image).digest()
    if block.image_hash != expected:
        raise ValueError(
            f"module '{name}' metadata hash does not match its image"
        )
