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
mkdir -p build
cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j"$JOBS" install

echo
echo "Solver ready: $DEST/install/console_solver"
