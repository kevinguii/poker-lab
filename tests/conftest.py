import json
import sys
from pathlib import Path

import pytest

from pokerlab.spot import Spot

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parent))  # lets tests `import trees`


@pytest.fixture(scope="session")
def river_tree() -> dict:
    """Real TexasSolver output for a tiny river spot (see tests/fixtures)."""
    return json.loads((FIXTURES / "river_tree.json").read_text())


@pytest.fixture(scope="session")
def river_spot() -> Spot:
    return Spot.from_dict(json.loads((FIXTURES / "river_spot.json").read_text()))
