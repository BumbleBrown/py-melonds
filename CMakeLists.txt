cmake_minimum_required(VERSION 3.15)
project(py-melonds VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(MELONDS_ENABLE_JIT  "Enable JIT recompiler" OFF)
option(MELONDS_VERBOSE_LOG "Print all log output"  OFF)

if(MELONDS_VERBOSE_LOG)
    add_compile_definitions(MELONDS_VERBOSE_LOG)
endif()

set(MELONDS_SRC "${CMAKE_SOURCE_DIR}/melonDS/src")

# NDS.cpp includes version.h which melonDS normally generates during its own build.
# We generate a minimal stub so it compiles as a submodule.
if(NOT EXISTS "${MELONDS_SRC}/version.h")
    file(WRITE "${MELONDS_SRC}/version.h"
        "#pragma once\n"
        "#define MELONDS_VERSION \"1.0\"\n"
        "#define MELONDS_VERSION_MAJOR 1\n"
        "#define MELONDS_VERSION_MINOR 0\n"
        "#define MELONDS_VERSION_BASE \"1.0\"\n"
    )
endif()

set(MELONDS_CORE_SOURCES
    ${MELONDS_SRC}/ARCodeFile.cpp
    ${MELONDS_SRC}/ARDatabaseDAT.cpp
    ${MELONDS_SRC}/AREngine.cpp
    ${MELONDS_SRC}/ARM.cpp
    ${MELONDS_SRC}/ARMInterpreter.cpp
    ${MELONDS_SRC}/ARMInterpreter_ALU.cpp
    ${MELONDS_SRC}/ARMInterpreter_Branch.cpp
    ${MELONDS_SRC}/ARMInterpreter_LoadStore.cpp
    ${MELONDS_SRC}/ARM_InstrInfo.cpp
    ${MELONDS_SRC}/CP15.cpp
    ${MELONDS_SRC}/CRC32.cpp
    ${MELONDS_SRC}/DMA.cpp
    ${MELONDS_SRC}/DMA_Timings.cpp
    ${MELONDS_SRC}/DSi.cpp
    ${MELONDS_SRC}/DSi_AES.cpp
    ${MELONDS_SRC}/DSi_Camera.cpp
    ${MELONDS_SRC}/DSi_DSP.cpp
    ${MELONDS_SRC}/DSi_I2C.cpp
    ${MELONDS_SRC}/DSi_I2S.cpp
    ${MELONDS_SRC}/DSi_NAND.cpp
    ${MELONDS_SRC}/DSi_NDMA.cpp
    ${MELONDS_SRC}/DSi_NWifi.cpp
    ${MELONDS_SRC}/DSi_SD.cpp
    ${MELONDS_SRC}/DSi_SPI_TSC.cpp
    ${MELONDS_SRC}/FATIO.cpp
    ${MELONDS_SRC}/FATStorage.cpp
    ${MELONDS_SRC}/FreeBIOS.cpp
    ${MELONDS_SRC}/GBACart.cpp
    ${MELONDS_SRC}/GBACartMotionPak.cpp
    ${MELONDS_SRC}/GPU.cpp
    ${MELONDS_SRC}/GPU2D.cpp
    ${MELONDS_SRC}/GPU2D_Soft.cpp
    ${MELONDS_SRC}/GPU3D.cpp
    ${MELONDS_SRC}/GPU3D_Soft.cpp
    ${MELONDS_SRC}/GPU3D_Texcache.cpp
    ${MELONDS_SRC}/GPU_Soft.cpp
    ${MELONDS_SRC}/Mic.cpp
    ${MELONDS_SRC}/NDS.cpp
    ${MELONDS_SRC}/NDSCart.cpp
    ${MELONDS_SRC}/ROMList.cpp
    ${MELONDS_SRC}/RTC.cpp
    ${MELONDS_SRC}/SPI.cpp
    ${MELONDS_SRC}/SPI_Firmware.cpp
    ${MELONDS_SRC}/SPU.cpp
    ${MELONDS_SRC}/Savestate.cpp
    ${MELONDS_SRC}/Utils.cpp
    ${MELONDS_SRC}/Wifi.cpp
    ${MELONDS_SRC}/WifiAP.cpp
    ${MELONDS_SRC}/NDSCart/CartCommon.cpp
    ${MELONDS_SRC}/NDSCart/CartHomebrew.cpp
    ${MELONDS_SRC}/NDSCart/CartR4.cpp
    ${MELONDS_SRC}/NDSCart/CartRetail.cpp
    ${MELONDS_SRC}/NDSCart/CartRetailBT.cpp
    ${MELONDS_SRC}/NDSCart/CartRetailIR.cpp
    ${MELONDS_SRC}/NDSCart/CartRetailNAND.cpp
    ${MELONDS_SRC}/NDSCart/CartSD.cpp
    ${MELONDS_SRC}/DSP_HLE/AACUcode.cpp
    ${MELONDS_SRC}/DSP_HLE/G711Ucode.cpp
    ${MELONDS_SRC}/DSP_HLE/GraphicsUcode.cpp
    ${MELONDS_SRC}/DSP_HLE/UcodeBase.cpp
    ${MELONDS_SRC}/tiny-AES-c/aes.c
    ${MELONDS_SRC}/xxhash/xxhash.c
    ${MELONDS_SRC}/blip-buf/blip_buf.c
    ${MELONDS_SRC}/fatfs/ff.c
    ${MELONDS_SRC}/fatfs/ffunicode.c
    ${MELONDS_SRC}/fatfs/ffsystem.c
    ${MELONDS_SRC}/sha1/sha1.c
    ${MELONDS_SRC}/teakra/src/ahbm.cpp
    ${MELONDS_SRC}/teakra/src/apbp.cpp
    ${MELONDS_SRC}/teakra/src/btdmp.cpp
    ${MELONDS_SRC}/teakra/src/dma.cpp
    ${MELONDS_SRC}/teakra/src/memory_interface.cpp
    ${MELONDS_SRC}/teakra/src/mmio.cpp
    ${MELONDS_SRC}/teakra/src/processor.cpp
    ${MELONDS_SRC}/teakra/src/timer.cpp
    ${MELONDS_SRC}/teakra/src/teakra.cpp
    ${MELONDS_SRC}/teakra/src/disassembler.cpp
    ${MELONDS_SRC}/teakra/src/parser.cpp
)

if(MELONDS_ENABLE_JIT AND (CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64"))
    list(APPEND MELONDS_CORE_SOURCES
        ${MELONDS_SRC}/ARMJIT.cpp
        ${MELONDS_SRC}/ARMJIT_Global.cpp
        ${MELONDS_SRC}/ARMJIT_Memory.cpp
        ${MELONDS_SRC}/ARMJIT_x64/ARMJIT_Compiler.cpp
        ${MELONDS_SRC}/ARMJIT_x64/ARMJIT_ALU.cpp
        ${MELONDS_SRC}/ARMJIT_x64/ARMJIT_LoadStore.cpp
        ${MELONDS_SRC}/ARMJIT_x64/ARMJIT_Branch.cpp
    )
    add_compile_definitions(JIT_ENABLED)
else()
    set(MELONDS_ENABLE_JIT OFF)
endif()

add_library(melonds SHARED
    src/melonds_interface.cpp
    src/platform_headless.cpp
    ${MELONDS_CORE_SOURCES}
)

set_target_properties(melonds PROPERTIES PREFIX "")

target_include_directories(melonds PRIVATE
    ${MELONDS_SRC}
    ${MELONDS_SRC}/NDSCart
    ${MELONDS_SRC}/DSP_HLE
    ${MELONDS_SRC}/teakra/src
    ${MELONDS_SRC}/teakra/include
    ${MELONDS_SRC}/fatfs
    ${MELONDS_SRC}/sha1
    ${CMAKE_SOURCE_DIR}/src
)

target_compile_definitions(melonds PRIVATE
    MELONDS_VERSION="py-melonds-0.1"
)

if(MSVC)
    target_compile_options(melonds PRIVATE /W0)
else()
    target_compile_options(melonds PRIVATE -w)
endif()

# Copy the built library into the Python package directory
add_custom_command(TARGET melonds POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        $<TARGET_FILE:melonds>
        "${CMAKE_SOURCE_DIR}/python/melonds/$<TARGET_FILE_NAME:melonds>"
    COMMENT "Copying melonds library to python/melonds/"
)

message(STATUS "")
message(STATUS "py-melonds build configuration:")
message(STATUS "  JIT enabled : ${MELONDS_ENABLE_JIT}")
message(STATUS "  Verbose log : ${MELONDS_VERBOSE_LOG}")
message(STATUS "")
