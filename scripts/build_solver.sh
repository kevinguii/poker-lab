#!/usr/bin/env bash
# Builds the TexasSolver console binary into vendor/TexasSolver/install.
#
# TexasSolver is AGPL-3.0. We deliberately do NOT copy its code into this repo:
# it is cloned into ./vendor (gitignored) and run as a separate process. Personal,
# local use is fine; if you ever host this app for other people, read its README
# licensing notes first (it asks for a commercial license for network services).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor/TexasSolver"
JOBS="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)}"

for tool in git cmake make; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done

mkdir -p "$ROOT/vendor"
if [ ! -d "$DEST/.git" ]; then
  git clone --depth 1 --branch console https://github.com/bupticybee/TexasSolver.git "$DEST"
fi

cd "$DEST"
# The Python bindings (pybind11) are not used by the console solver and its CMake needs distutils, which Python 3.12+ removed.
sed -i.bak -E 's|^(include_directories\(ext/pybind11/include\))|#\1|; s|^(add_subdirectory\(ext/pybind11\))|#\1|' CMakeLists.txt && rm -f CMakeLists.txt.bak
mkdir -p build
cd build
# The bundled googletest predates CMake 4, which dropped support for cmake_minimum_required < 3.5.
CMAKE_ARGS=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5)
if [ "$(uname)" = "Darwin" ]; then
  # Apple clang has no OpenMP; use Homebrew's libomp (keg-only, so CMake cannot find it by itself).
  command -v brew >/dev/null || { echo "macOS needs Homebrew's libomp: brew install libomp" >&2; exit 1; }
  OMP="$(brew --prefix libomp 2>/dev/null)"
  [ -d "$OMP/lib" ] || { echo "missing libomp: brew install libomp" >&2; exit 1; }
  OMP_FLAGS="-Xpreprocessor -fopenmp -I$OMP/include"
  CMAKE_ARGS+=(
    "-DOpenMP_C_FLAGS=$OMP_FLAGS" "-DOpenMP_CXX_FLAGS=$OMP_FLAGS"
    -DOpenMP_C_LIB_NAMES=omp -DOpenMP_CXX_LIB_NAMES=omp
    "-DOpenMP_omp_LIBRARY=$OMP/lib/libomp.dylib"
    "-DCMAKE_EXE_LINKER_FLAGS=-L$OMP/lib -lomp -Wl,-rpath,$OMP/lib"
  )
fi
cmake "${CMAKE_ARGS[@]}" ..
cmake --build . --target console_solver --parallel "$JOBS"
cmake --install .

echo
echo "Solver ready: $DEST/install/console_solver"
