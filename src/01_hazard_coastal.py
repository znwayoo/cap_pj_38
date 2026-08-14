"""Stage 2 (coastal): predict 100-year coastal flooding over Dublin from DEM elevation and slope."""
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
from src import progress
from src.cv import cv_scores

BBOX = (712000, 728000, 730000, 745000)


def main():
    with progress.stage("STAGE 2 HAZARD: coastal flood from terrain, method comparison"):
        progress.step("reading Copernicus DEM and deriving slope")
        with rasterio.open(config.DEM_TIF) as d:
            dem = d.read(1).astype(float)
            dtr = d.transform
            dnod = d.nodata
        dem[dem == dnod] = np.nan
        gy, gx = np.gradient(dem, 30.0)              # 30 m cells
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))

        rng = np.random.default_rng(42)
        n = 20000
        xs = rng.uniform(BBOX[0], BBOX[2], n)
        ys = rng.uniform(BBOX[1], BBOX[3], n)
        with progress.spinner("sampling 20,000 points; labelling from OPW coastal depth"):
            with rasterio.open(config.COASTAL_TIF) as f:
                depth = np.array([v[0] for v in f.sample(np.c_[xs, ys])], float)
                fnod = f.nodata
        depth[depth == fnod] = 0
        label = (depth >= 0.2).astype(int)

        inv = ~dtr
        cols = np.floor((inv.a * xs + inv.b * ys + inv.c)).astype(int)
        rows = np.floor((inv.d * xs + inv.e * ys + inv.f)).astype(int)
        ok = (rows >= 0) & (rows < dem.shape[0]) & (cols >= 0) & (cols < dem.shape[1])
        elev = np.full(n, np.nan)
        slp = np.full(n, np.nan)
        elev[ok] = dem[rows[ok], cols[ok]]
        slp[ok] = slope[rows[ok], cols[ok]]

        m = ~np.isnan(elev) & ~np.isnan(slp)
        X = np.c_[elev[m], slp[m]]
        y = label[m]
        progress.kv("samples", len(y))
        progress.kv("flooded", f"{int(y.sum())} ({100 * y.mean():.1f}%)")
        progress.kv("mean elevation flooded vs dry",
                    f"{X[y == 1, 0].mean():.1f} m vs {X[y == 0, 0].mean():.1f} m")

        cv = StratifiedKFold(5, shuffle=True, random_state=0)
        models = {
            "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)),
            "Random forest":       RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced", random_state=0),
            "Gradient boosting":   HistGradientBoostingClassifier(random_state=0),
        }
        progress.step("method comparison (ROC AUC, 5-fold):")
        results = []
        for name, mdl in models.items():
            auc = cv_scores(mdl, X, y, cv, "roc_auc", name)
            progress.kv(name, f"AUC {auc.mean():.3f} +/- {auc.std():.3f}")
            results.append({"task": "coastal from terrain", "model": name,
                            "roc_auc_mean": float(auc.mean()), "roc_auc_std": float(auc.std())})

        out = config.ARTIFACTS / "hazard"
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_csv(out / "hazard_coastal_comparison.csv", index=False)
        progress.kv("wrote", out / "hazard_coastal_comparison.csv")

        with progress.spinner("fitting Random forest for feature importance"):
            rf = models["Random forest"].fit(X, y)
        progress.kv("RF feature importance", "elevation %.2f, slope %.2f" % tuple(rf.feature_importances_))


if __name__ == "__main__":
    main()
