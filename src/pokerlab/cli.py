"""``pokerlab`` command: start the local app."""

from __future__ import annotations

import argparse

import uvicorn

from .api import create_app
from .solver import find_solver_dir


def main() -> None:
    p = argparse.ArgumentParser(prog="pokerlab", description="Local poker study app")
    p.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1: this app has no auth")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()

    if find_solver_dir() is None:
        print("! TexasSolver not found. Run scripts/build_solver.sh (browsing cached solves still works).")
    print(f"pokerlab running on http://{args.host}:{args.port}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
