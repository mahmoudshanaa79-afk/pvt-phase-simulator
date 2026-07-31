# PVT Phase Simulator

Python 3.12 foundation for a PVT phase simulator.

The current implementation covers pure-methane Peng–Robinson parameters,
compressibility roots, fugacity coefficients, and stable-root selection. Mixtures,
flash calculations, phase envelopes, depletion, and the user interface remain
future work.

## Requirements

- Python 3.12
- `uv`
- Git

## Setup

From the project root:

```powershell
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run streamlit --version
```

The Python package uses the `src` layout and is installed from
`src/pvt_phase_simulator`.
