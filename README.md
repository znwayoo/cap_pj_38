# Project 38: Irish residential flood hazard and depth-damage modelling

Project 38 builds dwelling-type-resolved flood hazard and depth-damage curves for Irish residential buildings, with banded uncertainty, and applies them to a Dublin worked example. This repository holds the full modelling pipeline: it composes open Irish flood-hazard and building-stock data into those curves and generates every result table and figure in the report's Chapter 4 directly from the source data.

The interactive report app can be found here : https://capstone38.streamlit.app/

## What is here

- `src/` the pipeline in six numbered stages, run in report Chapter 4 order (hazard, exposure, vulnerability, then the Dublin deployment; data and harmonisation first):
  - `00_harmonisation.py` build the reference-curve family and BER exposure profiles
  - `01_hazard_coastal.py` coastal flood from terrain (method comparison)
  - `02_hazard_fluvial.py` fluvial flood with a distance-to-river feature
  - `03_exposure_classifier.py` fine dwelling-type classifier
  - `04_vulnerability_model.py` trained depth-damage models (logic in `src/vulnerability.py`)
  - `05_deployment_dublin.py` apply the curve to Dublin small areas, euro band
  - `06_report.py` collect the headline results into a summary
- `run_all.py` run every stage in order with a data preflight and a pass/fail summary; on a clean run it also draws the report figures
- `prepare_data.py` download and standardise the datasets (see `docs/01_data_sources.md`)
- `scripts/make_report_figures.py` redraw the Chapter 4 figures from the latest run
- `docs/` data sources, harmonisation method, methodology, results (the plain-English write-up)
- `tests/` pipeline tests
- `artifacts/` where the pipeline writes its result tables and figures (generated, not tracked)

## Quickstart

Use a virtual environment. Python 3.11+ works; Python 3.13 is recommended to reproduce the numbers as closely as possible.

```
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# download the datasets per docs/01_data_sources.md, then:
python prepare_data.py                                   # download open sources, standardise, validate
python run_all.py                                        # regenerate all results and figures, with progress feedback
python -m pytest -q                                      # optional: verify
```

`prepare_data.py --check` validates the data layout without downloading or moving anything.

`run_all.py` runs the six stages and, only if every stage passes, draws the report figures into `artifacts/report_figures/`. If a stage fails it stops and skips the figures. You can also redraw the figures on their own at any time after a successful run:

```
python scripts/make_report_figures.py
```

That script refuses to run and tells you which stage to re-run if a required result is missing.

## Reproducibility and the two moving sources

Each stage reads its file paths from `config.py` and prints its progress as it runs. With Python 3.13 and the versions pinned in `requirements.txt`, `run_all.py` reproduces the report's Chapter 4 results, including the Dublin worked example: 379 small areas flood, about 536,810 m2 of damaged floor-area equivalent, and a source-disagreement band of roughly 136,000 to 782,000 m2.

Two inputs move over time, so a fresh run can differ from the report by a fraction of a percent:

- The SEAI Building Energy Rating register is updated continuously. A fresh download shifts the exposure, vulnerability and deployment numbers, in practice by under about 0.2 percent on the headline figures and up to roughly 1 to 2 percent on some individual model scores.
- The fluvial stage pulls OpenStreetMap watercourses live from the Overpass API, so the fluvial ROC AUC row reflects the watercourse data on the day you run it.

Every model ranking and every conclusion in the report is unchanged by this drift; only the third-decimal figures move. Everything else (coastal hazard, the reference curves, census, boundaries, elevation and the OPW depth rasters) comes from fixed inputs and reproduces exactly.
