@echo off
REM scripts/build_win64.bat
REM Builds melonds.dll on Windows using MSYS2 MinGW64.
REM Run this from the repo root in an MSYS2 MinGW64 terminal,
REM or from a standard Windows command prompt if cmake is on PATH.

echo Building py-melonds for Windows x64...

if not exist build mkdir build
cd build

cmake .. -DCMAKE_BUILD_TYPE=Release -DMELONDS_ENABLE_JIT=OFF
if errorlevel 1 (
    echo CMake configure failed.
    exit /b 1
)

cmake --build . --parallel
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

cd ..
echo.
echo Done. Library copied to python\melonds\melonds.dll
