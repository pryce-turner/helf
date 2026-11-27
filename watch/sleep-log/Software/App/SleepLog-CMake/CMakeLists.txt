# SleepLog — an autostarted Glance: a service with no GUI (plan 0024).
# Structure follows the SDK's GlanceSteps example: a service and no GUI.
cmake_minimum_required(VERSION 3.21)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/build")

# App configuration
set(APP_NAME "SleepLog")
set(APP_USER_NAME "Sleep Log")
# The on-watch name may change; the file name the install flow keys on stays.
set(APP_FILE_NAME "SleepLog")
# A Glance, because it is the only type the SDK packs without a GUI:
# app_merging.py refuses a Utility with no .gui ("required for type Utility").
# The type only decides where the app shows; autostart is a separate flag the
# kernel honours for any type (App::Manager::autoRun), so the service still
# starts at boot and stays resident. The glance is a one-line status tile.
set(APP_TYPE "Glance")
# Started at boot with no GUI and left resident (service-lifecycle.md §3.2).
set(APP_AUTOSTART On)
# A Glance needs no launcher icons (the packer zero-fills them).
set(APP_USE_ICONS Off)
set(DEV_ID "HELF")
# md5("SleepLog")[:16], per sdk-setup.md.
set(APP_ID "64313DF28C1B15C8")
set(RESOURCES_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../../Resources")
set(OUTPUT_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../../Output")
set(LIBS_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../Libs")

# Sets the toolchain before project()
include($ENV{UNA_SDK}/cmake/una-app.cmake)
include($ENV{UNA_SDK}/cmake/una-sdk.cmake)
include(${LIBS_PATH}/libs.cmake)

project(${APP_NAME})

una_app_setup_version(BUILD_VERSION ${CMAKE_CURRENT_SOURCE_DIR})

set(SERVICE_SOURCES
    ${LIBS_SOURCES}
    ${UNA_SDK_SOURCES_COMMON}
    ${UNA_SDK_SOURCES_SERVICE}
)
set(SERVICE_INCLUDE_DIRS
    ${LIBS_INCLUDE_DIRS}
    ${UNA_SDK_INCLUDE_DIRS_COMMON}
    ${UNA_SDK_INCLUDE_DIRS_SERVICE}
)
una_app_build_service(${APP_NAME}Service.elf)

una_app_build_app()
