# Results

All numbers below come from running the code in this repository on real Irish data. Re-run any stage to reproduce them; they are written to `artifacts/`.

## Vulnerability model (the core deliverable)

Trained on raw flood depth (the axis the reference curves use and Grant Thornton asked for), validated with 15 repeated grouped train-test splits:

| Model | MAE | RMSE | R2 | bias |
|---|---|---|---|---|
| GAM (best model, deployed curve) | 0.177 | 0.218 | 0.409 | 0.001 |
| Baseline (best univariable curve) | 0.176 | 0.219 | 0.406 | 0.000 |
| CatBoost | 0.179 | 0.221 | 0.395 | -0.001 |
| XGBoost (benchmark) | 0.182 | 0.226 | 0.367 | -0.000 |
| Random Forest (primary) | 0.183 | 0.226 | 0.364 | -0.001 |
| Baseline (OLS, depth only) | 0.185 | 0.227 | 0.361 | 0.000 |
| Bayesian ridge (secondary) | 0.185 | 0.227 | 0.360 | 0.001 |
| LightGBM | 0.183 | 0.227 | 0.358 | -0.001 |
| Quantile Random Forest | 0.180 | 0.232 | 0.331 | 0.014 |

The secondary model is a Bayesian ridge regressor. A Linear-Gaussian Bayesian network was considered but is degenerate on this design: the one-hot dwelling-type columns leave the joint covariance singular, so the Bayesian ridge is used and reported as such.

Result: no multivariable model beats the univariable baseline. The best univariable curve (R2 0.406) is level with the best model (GAM 0.409) and beats every tree ensemble, including the primary Random Forest (0.364). Feature importance and a direct ablation agree that flood depth is the only real predictor: a Random Forest on flood depth alone scores 0.410, adding dwelling type leaves it at 0.410, and adding the structural features (area, storeys, age, masonry) lowers it to 0.364. The ablation uses the same splits, seed and forest settings as the main table, and its full-feature row reproduces the Random Forest score exactly. It is written to `artifacts/vulnerability_extended/ablation.csv`. This follows from the harmonised reference curves being a function of depth and, weakly, dwelling type only. All models are essentially unbiased. R2 here measures fidelity to the synthetic curve family, not real losses, so it is not comparable to the Bles et al. (2026) R2 of 0.39 on real data. The contribution is a reproducible, uncertainty-banded, dwelling-type-resolved curve pipeline from open data; demonstrating multivariable value requires real Irish loss records, which do not exist.

Damage ratio at 1 m flood depth, by dwelling type, against what the labels contain:

| Type | label (mean of the 4 sources) | Middlesex alone | GAM | Random Forest |
|---|---|---|---|---|
| Detached | 0.434 | 0.113 | 0.438 | 0.485 |
| Semi-Detached | 0.435 | 0.117 | 0.433 | 0.482 |
| Bungalow | 0.446 | 0.163 | 0.440 | 0.426 |
| Terrace | 0.434 | 0.113 | 0.435 | 0.359 |
| Apartment | 0.432 | 0.106 | 0.416 | 0.304 |
| **spread across types** | **0.014** | **0.057** | **0.024** | **0.181** |

Only the Middlesex curve varies by dwelling type; the three JRC curves are type-invariant (spread exactly 0.000 each). Because each dwelling is assigned a random source, the label the models learn has a type spread of only 0.014 at 1 m. GAM reproduces that (0.024). The Random Forest does not: its 0.181 spread is roughly thirteen times what the labels contain, and it inverts the ordering (Middlesex ranks Bungalow highest and Detached fourth; the forest ranks Detached highest and Bungalow third). That separation is the forest fitting noise on the structural attributes, the same effect the ablation shows when those attributes drop R2 from 0.410 to 0.364. The type differences a Random Forest appears to find are therefore not evidence of type-dependent vulnerability, and the deployed curve uses GAM for this reason.

## Hazard layer

| Task | Logistic | Random forest | Gradient boosting |
|---|---|---|---|
| Coastal flood from terrain (ROC AUC) | 0.776 | 0.977 | 0.978 |
| Fluvial, terrain only (ROC AUC) | 0.709 | 0.753 | 0.800 |
| Fluvial + distance-to-river (ROC AUC) | 0.937 | 0.939 | 0.922 |

Coastal flooding is elevation-driven and the tree methods win decisively. Fluvial flooding needs a river-proximity feature: adding distance-to-river lifts AUC from 0.80 to about 0.94, because Dublin's rivers run through elevated ground so elevation alone fails. The fluvial stage builds its distance-to-river feature from live OpenStreetMap watercourses (Overpass API), so those two rows are a snapshot of that data on the run date; the coastal row uses only the DEM and reproduces offline.

## Exposure layer

Fine dwelling-type classifier, macro-F1: logistic 0.726, random forest 0.771, gradient boosting 0.766. Written to `artifacts/exposure/exposure_method_comparison.csv`. Reliable for Bungalow, Apartment and Detached; the Semi-Detached vs Terrace boundary is weaker and carries extra uncertainty. This layer is validated on its own and is not wired into the Dublin deployment.

## Deployment (Dublin worked example)

Applying the trained GAM curve to real Dublin small areas under the OPW 100-year coastal flood: 379 small areas flood; 536,810 m2 of damaged floor-area equivalent (the firm, data-derived output), source-disagreement band 136,027 to 782,435 m2. Euro is reported as a band across illustrative rebuild rates (SCSI not openly available): envelope about EUR 272M to 2,739M across 2,000 to 3,500 EUR/m2, illustrative headline EUR 1,342M at 2,500 EUR/m2. Damage concentrates on Sandymount, Ringsend, the Liffey mouth and Clontarf, Dublin's coastal flood-risk areas.

## Limitations

- Supervision is synthetic (no paired Irish loss data), so the vulnerability model reproduces the harmonised curve surface with realistic scatter. The real test comes when Irish loss labels (Storm Babet wrack-marks, future claims) replace the synthetic ones.
- Type resolution is weak: only the Middlesex source curve varies by dwelling type, so the models have almost no type signal to learn and the univariable curve is as good as the multivariable models.
- Pluvial flooding and SCSI rebuild cost are out of scope (verified unobtainable), documented in `docs/03_methodology.md`.
