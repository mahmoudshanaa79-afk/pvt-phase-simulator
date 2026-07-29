# PVT Phase Simulator

Development foundation for a Python 3.12 PVT phase simulator.

Milestone 0 covers only the development environment and project setup. Petroleum
property and equation-of-state calculations are intentionally not implemented yet.

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
