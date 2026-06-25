# firmware/host_test/CMakeLists.txt
cmake_minimum_required(VERSION 3.16)
project(gemscanner_fw_host_tests C)
enable_testing()
set(CMAKE_C_STANDARD 11)

set(COMPONENTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../components)

# Helper: add a host test that compiles a pure component + its test file.
function(add_pure_test test_name component)
  add_executable(${test_name} ${ARGN})
  target_include_directories(${test_name} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${COMPONENTS_DIR}/${component}/include)
  add_test(NAME ${test_name} COMMAND ${test_name})
endfunction()

# Scaffold test needs no component.
add_executable(test_scaffold test_scaffold.c)
target_include_directories(test_scaffold PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
add_test(NAME test_scaffold COMMAND test_scaffold)

add_pure_test(test_command_parser command_parser
  ${COMPONENTS_DIR}/command_parser/command_parser.c
  test_command_parser.c)
