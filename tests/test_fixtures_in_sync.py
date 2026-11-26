import json

import pytest

from tests.js_fixtures import OUT, build


@pytest.mark.parametrize("name, payload", build().items())
def test_ui_fixtures_match_the_real_api(name, payload):
    stored = json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))
    assert stored == payload, "API shape changed: run `python -m tests.js_fixtures` and re-run the UI tests"
