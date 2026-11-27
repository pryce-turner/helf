# The service's sources (all of Libs/Source) and the headers both processes
# share. The GUI compiles only Bac.cpp from here (DRINKS_GUI_SOURCES), for the
# standard-drink arithmetic on its confirmation page; the service does the rest.
file(GLOB_RECURSE LIBS_SOURCES CONFIGURE_DEPENDS
    ${CMAKE_CURRENT_LIST_DIR}/Source/*.cpp
)

set(LIBS_INCLUDE_DIRS
    ${CMAKE_CURRENT_LIST_DIR}/Header
)

set(DRINKS_GUI_SOURCES
    ${CMAKE_CURRENT_LIST_DIR}/Source/Bac.cpp
)
