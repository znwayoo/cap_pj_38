# Methodology and model choices

The project builds a composed, multi-layer framework: a **hazard** layer (where and how deep it floods), an **exposure** layer (what dwelling types are there), and a **vulnerability** layer (the depth-damage curve). Each layer is its own ML task. This document states the model choices for each layer.

## Guiding constraints (from the literature review)

1. No object-level Irish flood-loss records exist, so supervision is synthetic (harmonised international curves as labels; Wagenaar et al. 2021 transfer).
2. Multivariable methods beat univariable depth-only curves, but must stay interpretable and auditable for a risk-advisory audience.
3. Every output is a band, not a point (McGrath et al. 2019; Gnan et al. 2022).

## Vulnerability layer (the core deliverable): staged architecture

Implemented in `src/04_vulnerability_model.py` (logic in the importable `src/vulnerability.py`):

| Stage | Method | Role | Implemented as |
|---|---|---|---|
| 1 Baseline | univariable depth-damage family: linear, polynomial, square-root | reference to beat | best spec by cross-validated RMSE, reported alongside plain OLS |
| 2 Primary | Random Forest regressor, multivariable | main predictor | `RandomForestRegressor` |
| 3 Benchmark | XGBoost | like-for-like vs prior GT model | `xgboost` |
| 3b Boosting comparators | LightGBM, CatBoost | test whether the boosting result depends on the implementation | `lightgbm`, `catboost` |
| 4 Curve output | GAM, smooth monotone curves | hazard-curve reporting form | `pygam`, monotone spline on flood depth |
| 5 Predictive band | Quantile Random Forest | model-based q10/q50/q90 uncertainty | `RandomForestRegressor` per-tree quantiles |
| 6 Secondary | Bayesian ridge | explicit uncertainty, transfer (Wagenaar et al. 2018) | `sklearn` BayesianRidge |

A two-stage damage-occurrence gate (a classifier for whether damage occurs, feeding a regressor for magnitude, the Bles et al. structure) and a Tweedie-loss boosting variant were prototyped in an earlier script and removed. Both exist to handle zero-inflation in real claims data. Under synthetic curve supervision damage is a deterministic function of depth, so there are no zero-damage cases to gate on and neither method can be validated. They are recorded as the structure to adopt once real Irish claims data exists.

**Transfer layer (Wagenaar et al. 2021):** training rows are reweighted to the Irish dwelling-stock proportions, so the aggregate curve reflects the national mix, not the training sample. This needs only the Irish predictor distribution, not Irish loss records.

**Uncertainty layer (McGrath et al. 2019):** the label is not a single line. Each dwelling is assigned one plausible reference curve at random, so the training labels carry the true cross-source scatter; the model learns the conditional mean and the band is the residual spread (low/median/high).

**Feature set:** dwelling type, floor area, storeys, construction age, wall masonry, and **flood depth** (the raw hazard-map depth, the axis the reference curves use). Flood depth is the dominant and effectively the only real predictor under the synthetic labels: an ablation shows a Random Forest on flood depth alone scores higher than the full feature set, because the reference curves encode depth and, weakly, dwelling type only. An earlier depth-above-floor feature with assumed floor heights was removed as unsupported (Ireland has no measured floor heights); see `docs/02_harmonisation_method.md` and `docs/04_results_so_far.md`. Floor elevation is not abandoned as an idea, it is deferred: it belongs as a separate refinement layered on top of the flood-depth model, and it becomes testable only once measured per-building floor heights exist, as they do in Paulik et al. (2024) and Gnan et al. (2022).

**Validation:** repeated grouped train-test splits by dwelling (Paulik et al. 2024), reporting MAE, RMSE, R2 and mean bias. R2 here measures fidelity to the synthetic curve family, not to real losses, so it is not directly comparable to the Bles et al. (2026) R2 of 0.39 on real NFIP data. The meaningful comparison is the primary model against the univariable baseline.

## Hazard layer

Implemented in `src/01_hazard_coastal.py` and `src/02_hazard_fluvial.py`. Predicts flood occurrence from terrain, comparing logistic regression, random forest and gradient boosting (ROC AUC). Coastal flooding is elevation-driven; fluvial flooding needs a distance-to-river feature (from OpenStreetMap), because rivers run through elevated ground. Rainfall (Met Éireann) is a national-scale feature. Pluvial flooding is out of scope: no open pluvial flood-extent labels exist in Ireland.

## Exposure layer

Implemented in `src/03_exposure_classifier.py`. A fine dwelling-type classifier (logistic / random forest / gradient boosting) that disaggregates the coarse CSO small-area type split into canonical types, so the vulnerability curve can be placed spatially.

## Deployment

Implemented in `src/05_deployment_dublin.py`. Applies the vulnerability curve to real Dublin small areas under the real OPW 100-year coastal flood, producing a per-area damaged-floor-area-equivalent and a euro band. Euro is a band across illustrative rebuild rates because the SCSI rebuild-cost table is not openly machine-readable; the damaged-area and spatial pattern are the firm outputs.

## Two documented exclusions (needs-first discipline)

- **Pluvial flooding:** the OPW open portal distributes only fluvial and coastal; the pluvial layer is view-only. Scoped out, rainfall kept as a national feature.
- **SCSI rebuild cost:** not openly machine-readable, so euro is a band rather than a single figure.

Both are logged as verified "cannot obtain, using proxy X because Y", not silent omissions.
