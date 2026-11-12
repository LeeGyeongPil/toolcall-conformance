import pytest

from toolcall_conformance import i18n

from toolcall_conformance.checks import all_checks
from toolcall_conformance.mock import MockServer
from toolcall_conformance.runner import run_targets
from toolcall_conformance.targets import Target


@pytest.fixture(scope="session")
def server():
    with MockServer() as srv:
        yield srv


@pytest.fixture(scope="session")
def matrix(server):
    """{mode: {check_id: CheckResult}} for every mock mode (one run shared by all tests)."""
    from toolcall_conformance.mock import MODES

    targets = [Target(name=m, base_url=server.url(m), model="mock") for m in MODES]
    results = run_targets(targets, all_checks(), timeout=30)
    return {tr.target.name: {r.check: r for r in tr.results} for tr in results}


@pytest.fixture(autouse=True)
def pin_english(monkeypatch):
    """Tests run in English whatever the developer's locale is; ko tests opt in explicitly."""
    monkeypatch.setenv("TOOLCALL_CONFORMANCE_LANG", "en")
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    i18n.set_lang(None)
    yield
    i18n.set_lang(None)
