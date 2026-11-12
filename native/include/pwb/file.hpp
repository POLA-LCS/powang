// File values for the native runtime.

#pragma once

#include <fstream>
#include <memory>
#include <string>

namespace pwb {

struct FileObject {
    std::string path;
    std::string mode;
};

struct FileStream {
    std::unique_ptr<std::fstream> stream;
    std::string mode;
};

} // namespace pwb
