# Intentionally minimal: src-layout + editable install (pip install -e '.[dev]')
# make the `feedsmith` package importable in tests. Pytest also adds `src` to
# the path via [tool.pytest.ini_options] pythonpath in pyproject.toml.
#
# Each test file is self-contained and defines its own fakes (FakeFetcher,
# FakeSink, fake clocks/posters). No shared fixtures live here on purpose.
