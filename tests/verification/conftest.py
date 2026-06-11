"""Shared pytest configuration for the verification suite.

The behavioural scenarios (``test_s*_*.py``) each drive a full JuPedSim run via
``scenario.run_scenario``.  The fast, single-seed assertions run by default; the
expensive ensemble (multi-seed / large-population) assertions are marked
``slow`` and co-located in the same files, so ``pytest tests/verification`` gives
the CI signal and ``pytest -m slow tests/verification`` adds the dose-response.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: ensemble / large-population behavioural checks (opt in with -m slow)",
    )
