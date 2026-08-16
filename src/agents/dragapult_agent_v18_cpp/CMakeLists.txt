# Secondary build path -- documentation / IDE support / local smoke-testing
# on a machine that actually has CMake + a C++ compiler (this dev machine has
# neither, see README.md). The submission itself does NOT depend on this
# file: main_v17.py compiles cpp/v17_agent.cpp directly with a single g++
# invocation (see compile.sh) rather than shelling out to CMake, since a
# one-command build is the smallest possible thing that can fail on an
# unknown Kaggle grading container.
cmake_minimum_required(VERSION 3.15)
project(v18_mcts CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O3")

add_library(v18_mcts SHARED cpp/v17_agent.cpp)
set_target_properties(v18_mcts PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(UNIX AND NOT APPLE)
  target_link_libraries(v18_mcts dl)
endif()
