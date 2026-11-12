"""Render a complete ``temp.cpp`` translation unit for a program image.

The generated source embeds the exact ``image.to_bytes()`` payload and its
PWBM metadata in byte arrays and calls
``pwb::run_embedded_image_with_meta``. The text lives in an in-memory
``io.StringIO`` buffer and this module never writes a file.
"""

from __future__ import annotations

import io
import zlib
from dataclasses import dataclass

from ..image import ProgramImage
from .bundle import build_bundle
from .meta import build_meta


HEADER_COMMENT = "// Generated from a Powang PWB1 image. Do not edit."
BYTES_PER_LINE = 12


@dataclass(frozen=True)
class SourceOptions:
    """Knobs for the generated translation unit.

    ``entry_label`` is reserved for a future multi entry layout. The N0 unit
    always runs the image entry code, so the label does not appear in the
    generated text yet.
    """

    entry_label: str = "program"
    emit_crc: bool = True
    emit_meta: bool = True
    emit_bundle: bool = True


def _write_byte_array(buffer: io.StringIO, name: str, data: bytes) -> None:
    buffer.write(f"alignas(8) const std::uint8_t {name}[] = {{\n")
    for start in range(0, len(data), BYTES_PER_LINE):
        chunk = data[start : start + BYTES_PER_LINE]
        tokens = ", ".join(f"0x{byte:02X}" for byte in chunk)
        buffer.write(f"    {tokens},\n")
    buffer.write("};\n")


def render_temp_cpp_into(
    buffer: io.StringIO,
    image: ProgramImage,
    options: SourceOptions | None = None,
) -> None:
    """Render the translation unit into ``buffer`` as many small chunks."""
    if options is None:
        options = SourceOptions()
    data = image.to_bytes()
    meta = build_meta(image) if options.emit_meta else b""
    bundle = build_bundle(image) if options.emit_bundle else b""
    buffer.write(HEADER_COMMENT)
    buffer.write("\n\n")
    buffer.write("#include <cstddef>\n")
    buffer.write("#include <cstdint>\n")
    buffer.write('\n#include "pwb/host.hpp"\n')
    buffer.write('#include "pwb/vm.hpp"\n')
    buffer.write("\nnamespace {\n\n")
    _write_byte_array(buffer, "kPwbImage", data)
    buffer.write("\nconstexpr std::size_t kPwbImageSize = sizeof(kPwbImage);\n")
    if options.emit_crc:
        checksum = zlib.crc32(data) & 0xFFFFFFFF
        buffer.write(
            "[[maybe_unused]] constexpr std::uint32_t kPwbImageCrc = "
            f"0x{checksum:08X};\n"
        )
    if options.emit_meta:
        buffer.write("\n")
        _write_byte_array(buffer, "kPwbMeta", meta)
        buffer.write("\nconstexpr std::size_t kPwbMetaSize = sizeof(kPwbMeta);\n")
    if options.emit_bundle:
        buffer.write("\n")
        _write_byte_array(buffer, "kPwbBundle", bundle)
        buffer.write(
            "\nconstexpr std::size_t kPwbBundleSize = "
            "sizeof(kPwbBundle);\n"
        )
        buffer.write(
            "\n[[maybe_unused]] constexpr auto kPwbLegacyEntry = "
            "&pwb::run_embedded_image_with_meta;\n"
        )
    buffer.write("\n} // namespace\n\n")
    buffer.write("int main() {\n")
    buffer.write("    pwb::StdoutHost host;\n")
    if options.emit_bundle:
        buffer.write(
            "    return pwb::run_embedded_bundle_with_meta("
            "kPwbBundle, kPwbBundleSize, host);\n"
        )
    elif options.emit_meta:
        buffer.write(
            "    return pwb::run_embedded_image_with_meta("
            "kPwbImage, kPwbImageSize, kPwbMeta, kPwbMetaSize, host);\n"
        )
    else:
        buffer.write(
            "    return pwb::run_embedded_image("
            "kPwbImage, kPwbImageSize, host);\n"
        )
    buffer.write("}\n")


def render_temp_cpp_buffer(
    image: ProgramImage,
    options: SourceOptions | None = None,
) -> io.StringIO:
    """Render into a fresh in-memory buffer positioned at the start."""
    buffer = io.StringIO()
    render_temp_cpp_into(buffer, image, options)
    buffer.seek(0)
    return buffer


def render_temp_cpp(
    image: ProgramImage,
    options: SourceOptions | None = None,
) -> str:
    """Return the complete translation unit as text."""
    return render_temp_cpp_buffer(image, options).getvalue()


def render_bundle_cpp(
    bundle: bytes,
    options: SourceOptions | None = None,
) -> str:
    """Render a translation unit for a prebuilt PWBB bundle."""
    if options is None:
        options = SourceOptions()
    buffer = io.StringIO()
    buffer.write(HEADER_COMMENT)
    buffer.write("\n\n")
    buffer.write("#include <cstddef>\n")
    buffer.write("#include <cstdint>\n")
    buffer.write('\n#include "pwb/host.hpp"\n')
    buffer.write('#include "pwb/vm.hpp"\n')
    buffer.write("\nnamespace {\n\n")
    _write_byte_array(buffer, "kPwbBundle", bundle)
    buffer.write(
        "\nconstexpr std::size_t kPwbBundleSize = sizeof(kPwbBundle);\n"
    )
    buffer.write("\n} // namespace\n\n")
    buffer.write("int main() {\n")
    buffer.write("    pwb::StdoutHost host;\n")
    buffer.write(
        "    return pwb::run_embedded_bundle_with_meta("
        "kPwbBundle, kPwbBundleSize, host);\n"
    )
    buffer.write("}\n")
    return buffer.getvalue()
