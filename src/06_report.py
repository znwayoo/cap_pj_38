"""Stage 6 (report): collect headline results into artifacts/summary/results.md and results.csv."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from src import progress

A = config.ARTIFACTS


def _read(rel):
    path = A / rel
    return pd.read_csv(path) if path.exists() else None


def collect():
    """Return a list of (section, metric, value) rows pulled from the stage artifacts."""
    rows = []

    dep = _read("deployment/dublin_damage_by_sa.csv")
    if dep is not None:
        flooded = int((dep["m2_mid"] > 0).sum())
        rows += [
            ("Deployment (Dublin, 100-year coastal)", "flooded small areas", f"{flooded:,}"),
            ("Deployment (Dublin, 100-year coastal)", "damaged floor-area equivalent (m2)",
             f"{dep['m2_mid'].sum():,.0f}  (band {dep['m2_lo'].sum():,.0f} to {dep['m2_hi'].sum():,.0f})"),
            ("Deployment (Dublin, 100-year coastal)", "estimated residential damage (EUR, central rate)",
             f"{dep['dmg_eur'].sum():,.0f}  (band {dep['dmg_lo'].sum():,.0f} to {dep['dmg_hi'].sum():,.0f})"),
        ]

    for task, rel in [("coastal", "hazard/hazard_coastal_comparison.csv"),
                      ("fluvial", "hazard/hazard_fluvial_comparison.csv")]:
        h = _read(rel)
        if h is not None:
            best = h.loc[h["roc_auc_mean"].idxmax()]
            rows.append((f"Hazard model ({task})", "best method (ROC AUC)",
                         f"{best['model']} — {best['roc_auc_mean']:.3f}"))

    ex = _read("exposure/exposure_method_comparison.csv")
    if ex is not None:
        best = ex.loc[ex["macro_f1"].idxmax()]
        rows.append(("Exposure classifier", "best method (macro-F1)",
                     f"{best['model']} — {best['macro_f1']:.3f}"))

    vm = _read("vulnerability_extended/metrics_comparison.csv")
    if vm is not None:
        best = vm.loc[vm["R2"].idxmax()]
        rows.append(("Vulnerability models", "best model (R2)",
                     f"{best['model']} — {best['R2']:.4f}"))
        gam = vm[vm["model"] == "GAM"]
        if not gam.empty:
            rows.append(("Vulnerability models", "deployed model GAM (R2)",
                         f"{gam.iloc[0]['R2']:.4f}"))

    return rows


def main():
    with progress.stage("STAGE 6 REPORT: collect headline results"):
        rows = collect()
        out = A / "summary"
        out.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(rows, columns=["section", "metric", "value"]).to_csv(
            out / "results.csv", index=False)

        lines = ["# Results summary", "",
                 "Headline numbers from the latest pipeline run. Regenerate with `python run_all.py`.", ""]
        current = None
        for section, metric, value in rows:
            if section != current:
                lines += ["", f"## {section}", ""]
                current = section
            lines.append(f"- {metric}: **{value}**")
        (out / "results.md").write_text("\n".join(lines) + "\n")

        for _, metric, value in rows:
            progress.kv(metric, value)
        progress.kv("wrote", "artifacts/summary/results.md and results.csv")


if __name__ == "__main__":
    main()
