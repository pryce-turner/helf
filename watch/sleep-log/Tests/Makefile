# Host build of the SDK-free parts (SleepPolicy, RecordWriter). No SDK or
# ARM toolchain needed:  make -C watch/sleep-log/Tests
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O1
LIBS     := ../Software/Libs
FIXTURE  := ../../../backend/tests/fixtures/sleep_log_v1.bin

test: build/test_main
	./build/test_main

# Regenerates the fixture Helf's decoder test reads. Commit the result.
fixture: build/test_main
	./build/test_main --fixture $(FIXTURE)

build/test_main: test_main.cpp $(LIBS)/Source/SleepPolicy.cpp $(LIBS)/Source/RecordWriter.cpp $(wildcard $(LIBS)/Header/*.hpp)
	mkdir -p build
	$(CXX) $(CXXFLAGS) -I$(LIBS)/Header -o $@ test_main.cpp $(LIBS)/Source/SleepPolicy.cpp $(LIBS)/Source/RecordWriter.cpp

clean:
	rm -rf build

.PHONY: test fixture clean
