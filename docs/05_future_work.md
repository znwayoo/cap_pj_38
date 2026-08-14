# Scope boundaries and future work

This document states what the study deliberately leaves out and what would extend it. Each item is a defined next step, not a gap to be closed within the current data and scope.

## Out of scope (with the reason)

- **Pluvial (rainfall) flooding.** The OPW open portal distributes fluvial and coastal flood extents and depths, but the pluvial layer is view-only and not downloadable. The hazard layer is therefore scoped to fluvial and coastal, with Met Eireann rainfall retained as a national feature. A supervised pluvial model in the same form as the coastal and fluvial layers becomes possible once the pluvial extents are obtained.
- **Absolute euro from a single rebuild-cost source.** The SCSI rebuild-cost table is not openly machine-readable, so euro is reported as a band across illustrative rebuild rates rather than a single figure. The damaged floor-area equivalent and the spatial pattern are the firm, data-derived outputs; a verified free rate can replace the illustrative band later.

## Future work (what real Irish loss data would unlock)

- **Real depth-and-loss labels.** Supervision is currently synthetic (harmonised international curves as labels), because no paired object-level Irish depth-and-loss records are public. With real labels (for example Storm Babet wrack-mark surveys or future insurance claims), the vulnerability model can be validated against real losses and can test whether structural features add predictive value, which the international literature reports they do (Wagenaar et al. 2017, Paulik et al. 2024).
- **Damage-occurrence structure for real claims.** A two-stage occurrence gate (a classifier for whether damage occurs, feeding a magnitude regressor) and a Tweedie-loss boosting variant address the zero-inflation of real claims data. Under synthetic curve supervision damage is a deterministic function of depth, so there are no zero-damage cases to gate on and neither method can be validated; both are the structure to adopt once real claims exist.
- **Full sample-selection-bias correction.** The transfer step currently reweights training rows toward the national dwelling-stock proportions (the label-free representativeness approach of Wagenaar et al. 2021). The full sample-selection-bias correction with synthetic resampling is designed but not implemented, and becomes meaningful once real labels are present.
- **Floor-height refinement.** Depth above floor level (Paulik et al. 2024, Gnan et al. 2022) uses measured per-building floor heights, which Ireland does not currently have. The model evaluates curves at raw flood depth for that reason; depth above floor is a refinement to layer on once measured floor heights exist.
- **National extension.** The hazard and deployment layers are demonstrated on Dublin. Extending them nationally needs a national DEM mosaic and national watercourses, and forward-looking banded expected annual loss needs the CFRAM future-climate-scenario depth layers from the open portal.
