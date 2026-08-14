"""Stage 2 (fluvial): predict 100-year fluvial flooding over Dublin from elevation, slope, and distance to the nearest OpenStreetMap watercourse."""
import pathlib
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
from src import progress
from src.cv import cv_scores

BBOX = (712000, 728000, 730000, 745000)  # Dublin, ITM


# Overpass often returns 429/504; try mirrors in turn, most reliable first.
OVERPASS_ENDPOINTS = (
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def fetch_watercourses(attempts: int = 3):
    to_ll = Transformer.from_crs(2157, 4326, always_xy=True)
    lon0, lat0 = to_ll.transform(BBOX[0], BBOX[1])
    lon1, lat1 = to_ll.transform(BBOX[2], BBOX[3])
    south, north = min(lat0, lat1), max(lat0, lat1)
    west, east = min(lon0, lon1), max(lon0, lon1)
    q = (f'[out:json][timeout:90];way["waterway"~"river|stream|canal"]'
         f'({south},{west},{north},{east});out geom;')
    hdr = {"User-Agent": "capstone-flood-research/1.0"}
    # Retry across mirrors with a short backoff so one transient timeout does not fail the stage.
    last = None
    for attempt in range(1, attempts + 1):
        for url in OVERPASS_ENDPOINTS:
            try:
                # (connect, read): fail fast if a mirror is down, but allow a slow query to run.
                r = requests.post(url, data={"data": q}, headers=hdr, timeout=(10, 120))
                r.raise_for_status()
                els = r.json()["elements"]
                lons, lats = [], []
                for e in els:
                    for p in e.get("geometry", []):
                        lons.append(p["lon"])
                        lats.append(p["lat"])
                return els, lons, lats
            except Exception as exc:
                last = exc
        if attempt < attempts:
            time.sleep(5 * attempt)
    raise RuntimeError(
        f"Overpass unreachable after {attempts} rounds over {len(OVERPASS_ENDPOINTS)} mirrors "
        f"(last error: {last}). Re-run when the service is responsive.")


def main():
    with progress.stage("STAGE 2 HAZARD: fluvial flood + distance-to-river"):
        with progress.spinner("fetching OSM watercourses from Overpass (needs internet)"):
            els, lons, lats = fetch_watercourses()
        progress.kv("OSM waterway ways", len(els))
        progress.kv("river vertices", len(lons))
        to_itm = Transformer.from_crs(4326, 2157, always_xy=True)
        rx, ry = to_itm.transform(np.array(lons), np.array(lats))
        river_tree = cKDTree(np.c_[rx, ry])

        progress.step("reading DEM and deriving slope")
        with rasterio.open(config.DEM_TIF) as d:
            dem = d.read(1).astype(float)
            dtr = d.transform
            dnod = d.nodata
        dem[dem == dnod] = np.nan
        gy, gx = np.gradient(dem, 30.0)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))

        _sample_sp = progress.spin_start("sampling points; labelling from OPW fluvial depth tiles")
        rng = np.random.default_rng(42)
        n = 20000
        xs = rng.uniform(BBOX[0], BBOX[2], n)
        ys = rng.uniform(BBOX[1], BBOX[3], n)
        to_ig = Transformer.from_crs(2157, 29903, always_xy=True)
        xi, yi = to_ig.transform(xs, ys)
        depth = np.zeros(n)
        igbb = (xi.min(), yi.min(), xi.max(), yi.max())
        fluv = sorted(config.FLUVIAL_DIR.glob("*_0100_*.tif"))
        for f in fluv:
            with rasterio.open(f) as rr:
                b = rr.bounds
                if b.right < igbb[0] or b.left > igbb[2] or b.top < igbb[1] or b.bottom > igbb[3]:
                    continue
                inside = (xi >= b.left) & (xi <= b.right) & (yi >= b.bottom) & (yi <= b.top)
                if inside.sum() == 0:
                    continue
                vals = np.array([v[0] for v in rr.sample(np.c_[xi[inside], yi[inside]])], float)
                nod = rr.nodata
                if nod is not None:
                    vals[vals == nod] = 0
                vals[vals < 0] = 0
                depth[inside] = np.maximum(depth[inside], np.nan_to_num(vals))
        label = (depth >= 0.2).astype(int)

        inv = ~dtr
        cols = np.floor((inv.a * xs + inv.b * ys + inv.c)).astype(int)
        rows = np.floor((inv.d * xs + inv.e * ys + inv.f)).astype(int)
        ok = (rows >= 0) & (rows < dem.shape[0]) & (cols >= 0) & (cols < dem.shape[1])
        elev = np.full(n, np.nan)
        slp = np.full(n, np.nan)
        elev[ok] = dem[rows[ok], cols[ok]]
        slp[ok] = slope[rows[ok], cols[ok]]
        dist_river, _ = river_tree.query(np.c_[xs, ys])
        progress.spin_stop(_sample_sp)

        m = ~np.isnan(elev) & ~np.isnan(slp)
        y = label[m]
        X_terrain = np.c_[elev[m], slp[m]]
        X_river = np.c_[elev[m], slp[m], dist_river[m]]
        progress.kv("samples", len(y))
        progress.kv("flooded (fluvial)", f"{int(y.sum())} ({100 * y.mean():.2f}%)")
        progress.kv("mean distance-to-river flooded vs dry",
                    f"{dist_river[m][y == 1].mean():.0f} m vs {dist_river[m][y == 0].mean():.0f} m")

        cv = StratifiedKFold(5, shuffle=True, random_state=0)
        models = {
            "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)),
            "Random forest":       RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced", random_state=0),
            "Gradient boosting":   HistGradientBoostingClassifier(random_state=0),
        }
        results = []
        for tag, Xf in [("fluvial terrain only", X_terrain), ("fluvial terrain + river", X_river)]:
            progress.step(f"method comparison, {tag} (ROC AUC, 5-fold):")
            for name, mdl in models.items():
                auc = cv_scores(mdl, Xf, y, cv, "roc_auc", name)
                progress.kv(name, f"AUC {auc.mean():.3f} +/- {auc.std():.3f}")
                results.append({"task": tag, "model": name,
                                "roc_auc_mean": auc.mean(), "roc_auc_std": auc.std()})

        with progress.spinner("fitting Random forest for feature importance"):
            rf = models["Random forest"].fit(X_river, y)
        progress.kv("RF feature importance (elev, slope, dist_river)",
                    "%.2f, %.2f, %.2f" % tuple(rf.feature_importances_))

        out = config.ARTIFACTS / "hazard"
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_csv(out / "hazard_fluvial_comparison.csv", index=False)
        pd.DataFrame([{
            "n_samples": int(len(y)),
            "n_flooded": int(y.sum()),
            "flooded_rate_pct": round(100 * float(y.mean()), 4),
            "dist_river_flooded_m": round(float(dist_river[m][y == 1].mean()), 1),
            "dist_river_dry_m": round(float(dist_river[m][y == 0].mean()), 1),
            "imp_elev": round(float(rf.feature_importances_[0]), 4),
            "imp_slope": round(float(rf.feature_importances_[1]), 4),
            "imp_dist_river": round(float(rf.feature_importances_[2]), 4),
            "osm_ways": int(len(els)),
        }]).to_csv(out / "hazard_fluvial_summary.csv", index=False)
        progress.kv("wrote", "hazard_fluvial_comparison.csv and hazard_fluvial_summary.csv")


if __name__ == "__main__":
    main()
