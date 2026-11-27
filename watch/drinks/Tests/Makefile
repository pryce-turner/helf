# Host build of the SDK-free parts of Drinks (Bac, DrinkLog, Steps). No SDK or
# ARM toolchain needed:  make -C watch/drinks/Tests
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O1
LIBS     := ../Software/Libs

test: build/test_main
	./build/test_main

build/test_main: test_main.cpp $(LIBS)/Source/Bac.cpp $(LIBS)/Source/DrinkLog.cpp $(wildcard $(LIBS)/Header/*.hpp)
	mkdir -p build
	$(CXX) $(CXXFLAGS) -I$(LIBS)/Header -o $@ test_main.cpp $(LIBS)/Source/Bac.cpp $(LIBS)/Source/DrinkLog.cpp

clean:
	rm -rf build

.PHONY: test clean
