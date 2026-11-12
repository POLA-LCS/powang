cmake_minimum_required(VERSION 3.16)
project(pwb_native_runtime LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(pwb_runtime STATIC
    src/opcodes.cpp
    src/image.cpp
    src/verifier.cpp
    src/disasm.cpp
    src/bigint.cpp
    src/meta.cpp
    src/sha256.cpp
    src/bundle.cpp
    src/errors.cpp
    src/modules.cpp
    src/tasks.cpp
    src/object.cpp
    src/vm.cpp
    src/host.cpp)

target_include_directories(pwb_runtime
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

if(MSVC)
    target_compile_options(pwb_runtime PRIVATE /W4)
else()
    target_compile_options(pwb_runtime PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(pwb_native src/main.cpp)
target_link_libraries(pwb_native PRIVATE pwb_runtime)

if(MSVC)
    target_compile_options(pwb_native PRIVATE /W4)
else()
    target_compile_options(pwb_native PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()

add_executable(pwb_native_tests
    tests/test_bigint.cpp
    tests/test_value.cpp
    tests/test_bundle.cpp
    tests/test_errors.cpp
    tests/test_tasks.cpp)
target_link_libraries(pwb_native_tests PRIVATE pwb_runtime)

if(MSVC)
    target_compile_options(pwb_native_tests PRIVATE /W4)
else()
    target_compile_options(pwb_native_tests PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_test(NAME pwb_native_tests COMMAND pwb_native_tests)
