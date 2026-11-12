#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#include "pwb/disasm.hpp"
#include "pwb/error.hpp"
#include "pwb/host.hpp"
#include "pwb/image.hpp"
#include "pwb/opcodes_generated.hpp"
#include "pwb/verifier.hpp"
#include "pwb/vm.hpp"

namespace {

void usage() {
    std::cerr
        << "usage: pwb_native <command> [image]\n"
        << "commands:\n"
        << "  run <image.pwb>     run the embedded image\n"
        << "  disasm <image.pwb>  print the entry code disassembly\n"
        << "  verify <image.pwb>  verify the image\n"
        << "  version             print the runtime version\n";
}

bool read_file(const char* path, std::vector<std::uint8_t>& bytes) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return false;
    }
    bytes.assign(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>());
    return true;
}

void enable_binary_stdout() {
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY);
#endif
}

} // namespace

int main(int argc, char** argv) {
    enable_binary_stdout();
    if (argc < 2) {
        usage();
        return 2;
    }
    const std::string command = argv[1];
    if (command == "version") {
        if (argc != 2) {
            usage();
            return 2;
        }
        std::cout << "PWB " << pwb::generated::kFormatVersion << " "
                  << pwb::generated::kLanguageVersion << "\n";
        return 0;
    }
    if (command != "run" && command != "disasm" && command != "verify") {
        usage();
        return 2;
    }
    if (argc != 3) {
        usage();
        return 2;
    }
    std::vector<std::uint8_t> bytes;
    if (!read_file(argv[2], bytes)) {
        std::cerr << "native image error: cannot read " << argv[2] << "\n";
        return 1;
    }
    if (command == "run") {
        pwb::StdoutHost host;
        return pwb::run_embedded_image(bytes.data(), bytes.size(), host);
    }
    try {
        const pwb::Image image = pwb::parse_image(bytes.data(), bytes.size());
        pwb::verify_image(image);
        if (command == "disasm") {
            std::cout << pwb::disassemble_code(
                image.codes[image.entry_code], &image);
        } else {
            std::cout << "ok\n";
        }
        return 0;
    } catch (const pwb::ImageError& error) {
        std::cerr << "native image error: " << error.what() << "\n";
        return 1;
    } catch (const pwb::VerificationError& error) {
        std::cerr << "native verifier error: " << error.what() << "\n";
        return 1;
    }
}
