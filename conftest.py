import pytest

@pytest.fixture(autouse=True)
def offline_cost_defaults(monkeypatch):
    monkeypatch.setenv("MAX_AI_REVISIONS", "0")
    monkeypatch.setenv("MAX_PAID_CALLS_PER_JOB", "12")

@pytest.fixture(autouse=True)
def legacy_plan_mode(monkeypatch):
    monkeypatch.setenv("ENABLE_ACTION_PLAN", "0")
