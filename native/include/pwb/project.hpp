// Build-time project snapshot exposed to native modules.

#pragma once

#include <string>
#include <vector>

namespace pwb {

struct ProjectObject {
    std::vector<std::string> module_names;
    std::vector<std::string> paths;
    std::string log_level = "info";
    bool allow_system = false;
    std::string engine = "tree";
};

} // namespace pwb
