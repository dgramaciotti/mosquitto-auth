cmake_minimum_required(VERSION 3.20)
project(auth_plugin C)

# Allow user to specify where mosquitto headers are
option(MOSQUITTO_INCLUDE_DIR "Path to mosquitto include directory" "")

if (MOSQUITTO_INCLUDE_DIR)
    message(STATUS "Using Mosquitto headers from: ${MOSQUITTO_INCLUDE_DIR}")
else()
    # Try common locations (will work inside mosquitto source tree or install)
    find_path(MOSQUITTO_INCLUDE_DIR mosquitto.h
        PATHS
            /usr/include
            /usr/local/include
            /opt/homebrew/include
            ${CMAKE_SOURCE_DIR}/../mosquitto/include
    )
endif()

if (NOT MOSQUITTO_INCLUDE_DIR)
    message(FATAL_ERROR "Could not find mosquitto headers. Please set -DMOSQUITTO_INCLUDE_DIR=/path/to/mosquitto/include")
endif()

# Find libcurl
find_package(CURL REQUIRED)

# Add plugin as shared module
add_library(auth_plugin MODULE plugin.c)

target_include_directories(auth_plugin PRIVATE
    ${MOSQUITTO_INCLUDE_DIR}
    ${CURL_INCLUDE_DIRS}
)

# Link against libcurl
target_link_libraries(auth_plugin PRIVATE CURL::libcurl)

# On macOS, use dynamic lookup (dylib)
if(APPLE)
    set_target_properties(auth_plugin PROPERTIES
        LINK_FLAGS "-undefined dynamic_lookup"
        SUFFIX ".dylib"
    )
else()
    # On Linux, build as .so
    set_target_properties(auth_plugin PROPERTIES
        SUFFIX ".so"
    )
endif()
