import json
import os

import pytest

pytest.importorskip("pytest_playwright", reason="pytest-playwright is installed in CI/dev extras")

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_SMOKE") != "1",
    reason="browser smoke is opt-in; set RUN_BROWSER_SMOKE=1",
)


@pytest.mark.django_db(transaction=True)
def test_healthz_is_reachable_in_browser(page, live_server):
    response = page.goto(f'{live_server.url}/healthz/')

    assert response is not None
    assert response.status == 200
    body = page.locator('body').inner_text()
    payload = json.loads(body)
    assert payload['status'] == 'ok'
