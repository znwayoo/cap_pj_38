"""Stage 3: classify fine dwelling type (Detached, Bungalow, Semi-Detached, Terrace, Apartment) from BER attributes to refine the coarse census House/Apartment split."""
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
from src import progress
from src.cv import cv_oof_predict

BER_COLS = ["countyname", "dwellingtypedescr", "groundfloorarea(sq_m)", "nostoreys",
            "year_of_construction", "firstwalltype_description"]


def canonical(row):
    t = str(row["dwellingtypedescr"]).strip()
    if t == "Detached house":
        return "Bungalow" if row["storeys"] == 1 else "Detached"
    if t == "Semi-detached house":
        return "Semi-Detached"
    if t in ("Mid-terrace house", "End of terrace house"):
        return "Terrace"
    if t in ("Ground-floor apartment", "Mid-floor apartment", "Top-floor apartment",
             "Apartment", "Maisonette", "Basement Dwelling"):
        return "Apartment"
    if t == "House":
        return "Detached"
    return "Other"


def main():
    with progress.stage("STAGE 3 EXPOSURE: dwelling-type classifier, method comparison"):
        out = config.ARTIFACTS / "exposure"
        out.mkdir(parents=True, exist_ok=True)

        with progress.spinner(f"reading BER attributes from {config.BER_CSV.name} (~1.4M rows)"):
            ber = pd.read_csv(config.BER_CSV, usecols=BER_COLS, dtype=str)
        with progress.spinner("classifying dwelling type and sampling training rows"):
            ber["area"] = pd.to_numeric(ber["groundfloorarea(sq_m)"], errors="coerce")
            ber["storeys"] = pd.to_numeric(ber["nostoreys"], errors="coerce")
            ber["year"] = pd.to_numeric(ber["year_of_construction"], errors="coerce")
            ber["canonical"] = ber.apply(canonical, axis=1)
            ber = ber[ber["canonical"] != "Other"].copy()

            ber["masonry"] = ber["firstwalltype_description"].astype(str).str.contains(
                "Cavity|Stone|Block|brick|Brick|Concrete", case=False, na=False).astype(int)
            ber = ber[(ber["area"].between(20, 1000)) & (ber["year"].between(1700, 2026))]

            # stratified 120k sample (full set is 1.4M rows) for speed, fixed seed for reproducibility
            ber = pd.concat([g.sample(min(len(g), 24000), random_state=0)
                             for _, g in ber.groupby("canonical")], ignore_index=True)
        progress.kv("training rows", f"{len(ber):,}")
        for canon, count in ber["canonical"].value_counts().items():
            progress.kv(f"  class {canon}", f"{count:,}")

        num = ["area", "storeys", "year", "masonry"]
        cat = ["countyname"]
        for c in num:
            ber[c] = ber[c].astype("float64")
        ber["countyname"] = ber["countyname"].astype(str)
        y = ber["canonical"].to_numpy(dtype=object)

        pre = ColumnTransformer([
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                              ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), cat),
        ])
        X = ber[num + cat].reset_index(drop=True)

        cv = StratifiedKFold(5, shuffle=True, random_state=0)
        models = {
            "Logistic regression": Pipeline([("pre", pre), ("clf", LogisticRegression(
                max_iter=2000, class_weight="balanced"))]),
            "Random forest": Pipeline([("pre", pre), ("clf", RandomForestClassifier(
                n_estimators=300, min_samples_leaf=5, class_weight="balanced", n_jobs=-1, random_state=0))]),
            "Gradient boosting": Pipeline([("pre", pre), ("clf", HistGradientBoostingClassifier(random_state=0))]),
        }

        labels = sorted(np.unique(y))
        progress.step("method comparison (5-fold, macro-F1 and accuracy):")
        best_name, best_f1, best_pred = None, -1, None
        results = []
        cm_rows = []  # long-format confusion matrix per model, so any model's matrix can be shown
        for name, mdl in models.items():
            pred = cv_oof_predict(mdl, X, y, cv, name)
            f1 = f1_score(y, pred, average="macro")
            acc = accuracy_score(y, pred)
            progress.kv(name, f"macro-F1 {f1:.3f}  accuracy {acc:.3f}")
            results.append({"model": name, "macro_f1": float(f1), "accuracy": float(acc)})
            cm = confusion_matrix(y, pred, labels=labels)
            for i, tt in enumerate(labels):
                for j, pp in enumerate(labels):
                    cm_rows.append({"model": name, "true_type": tt,
                                    "predicted_type": pp, "count": int(cm[i, j])})
            if f1 > best_f1:
                best_name, best_f1, best_pred = name, f1, pred

        pd.DataFrame(results).to_csv(out / "exposure_method_comparison.csv", index=False)
        pd.DataFrame(cm_rows).to_csv(out / "exposure_confusion_by_model.csv", index=False)
        progress.kv("best method", f"{best_name} (macro-F1 {best_f1:.3f})")

        cm = confusion_matrix(y, best_pred, labels=labels)
        cm_df = pd.DataFrame(cm, index=labels, columns=labels)
        cm_df.to_csv(out / "exposure_confusion_matrix.csv")

        with progress.spinner("fitting Random forest for feature importance"):
            rf = models["Random forest"].fit(X, y)
        ohe = rf.named_steps["pre"].named_transformers_["cat"].named_steps["oh"]
        feat_names = num + list(ohe.get_feature_names_out(cat))
        imp = pd.Series(rf.named_steps["clf"].feature_importances_, index=feat_names).sort_values(ascending=False)
        progress.step("top feature signals (RF):")
        print(imp.head(8).round(3).to_string())
        imp.to_csv(out / "exposure_feature_importance.csv", header=["importance"])

        mdir = out / "saved_models"
        mdir.mkdir(parents=True, exist_ok=True)
        joblib.dump(rf, mdir / "exposure_random_forest.joblib")
        joblib.dump({"num": num, "cat": cat, "labels": labels}, mdir / "_exposure_meta.joblib")
        progress.kv("saved classifier",
                    f"{(mdir / 'exposure_random_forest.joblib').stat().st_size / 1e6:.1f} MB (gitignored)")


if __name__ == "__main__":
    main()
