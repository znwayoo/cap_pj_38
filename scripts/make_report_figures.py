"""Redraw the report's Chapter 4 figures into artifacts/report_figures/; standalone or auto-run by run_all.py."""
import warnings; warnings.filterwarnings("ignore")
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
import config
from src import progress

ART = config.ARTIFACTS
OUT = ART / "report_figures"

# Artifact each figure needs, mapped to the stage that produces it, for a clear missing-input error.
REQUIRED = {
    ART / "vulnerability_extended" / "metrics_comparison.csv": "stage 4 (vulnerability)",
    ART / "vulnerability_extended" / "ablation.csv": "stage 4 (vulnerability)",
    ART / "vulnerability_extended" / "curves_by_model.csv": "stage 4 (vulnerability)",
    ART / "vulnerability_extended" / "quantile_bands.csv": "stage 4 (vulnerability)",
    config.CURVE_FAMILY: "stage 1 (harmonisation)",
    ART / "hazard" / "hazard_coastal_comparison.csv": "stage 2 (coastal hazard)",
    ART / "hazard" / "hazard_fluvial_comparison.csv": "stage 2 (fluvial hazard)",
    ART / "exposure" / "exposure_confusion_matrix.csv": "stage 3 (exposure)",
    ART / "deployment" / "dublin_sa_geometry.json": "stage 5 (deployment)",
    ART / "deployment" / "dublin_damage_by_sa.csv": "stage 5 (deployment)",
}

# --- palette (light mode, validated colorblind-safe) ---
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
CAT5 = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA]           # up to 5 categories
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e6e2"
TYPES = ["Detached", "Semi-Detached", "Bungalow", "Terrace", "Apartment"]
TYPE_COLOR = dict(zip(TYPES, CAT5))

plt.rcParams.update({
    "figure.dpi": 200, "savefig.dpi": 200, "figure.facecolor": "white", "savefig.facecolor": "white",
    "font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": False,
    "axes.spines.top": False, "axes.spines.right": False,
})


def _finish(ax):
    ax.tick_params(length=0)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)


def save(fig, name):
    p = OUT / name
    fig.savefig(p, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    progress.kv("wrote", p.name)


# ---------------------------------------------------------------- Fig 1: model R2
def fig_model_r2():
    df = pd.read_csv(ART / "vulnerability_extended" / "metrics_comparison.csv").sort_values("R2")
    is_base = df["model"].str.startswith("Baseline")
    colors = [ORANGE if b else BLUE for b in is_base]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    y = np.arange(len(df))
    ax.barh(y, df["R2"], color=colors, height=0.66, zorder=3)
    for yi, v in zip(y, df["R2"]):
        ax.text(v + 0.004, yi, f"{v:.3f}", va="center", ha="left", fontsize=9, color=INK)
    ax.set_yticks(y); ax.set_yticklabels(df["model"])
    ax.set_xlabel("Coefficient of determination (R²), 15 grouped splits")
    ax.set_xlim(0, max(df["R2"]) * 1.18)
    ax.set_title("Held-out R² by model", pad=26)
    ax.legend(handles=[Patch(color=ORANGE, label="Univariable baseline"),
                       Patch(color=BLUE, label="Machine-learning model")],
              loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2,
              frameon=False, fontsize=9)
    _finish(ax)
    save(fig, "fig_4_3_model_r2.png")


# ---------------------------------------------------------------- Fig 2: ablation
def fig_ablation():
    df = pd.read_csv(ART / "vulnerability_extended" / "ablation.csv")
    labels = ["Flood depth\nonly", "Depth +\ndwelling type", "Depth + all\nstructural features"]
    colors = [BLUE, BLUE, ORANGE]
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    x = np.arange(len(df))
    ax.bar(x, df["R2_mean"], color=colors, width=0.6, zorder=3,
           yerr=df["R2_std"], capsize=4, ecolor=MUTED, error_kw={"lw": 1})
    for xi, v in zip(x, df["R2_mean"]):
        ax.text(xi, v + 0.012, f"{v:.3f}", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("R² (random forest, same splits)")
    ax.set_ylim(0, 0.48)
    ax.set_title("Adding structural features lowers held-out R² (under synthetic labels)")
    _finish(ax)
    save(fig, "fig_4_4_ablation.png")


# ------------------------------------------------- Fig 3: curves by type (label/GAM/RF)
def fig_curves_by_type():
    curves = pd.read_csv(ART / "vulnerability_extended" / "curves_by_model.csv")
    ref = pd.read_csv(config.CURVE_FAMILY)
    label = (ref.groupby(["canonical_type", "depth_m"])["damage_ratio"].mean().reset_index())
    panels = [("Reference curve (training target)", label, "damage_ratio"),
              ("GAM (deployed curve)", curves[curves.model == "GAM"], "damage_ratio"),
              ("Random forest", curves[curves.model == "RandomForest"], "damage_ratio")]
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.9), sharey=True)
    for ax, (title, d, col) in zip(axes, panels):
        for t in TYPES:
            sub = d[d.canonical_type == t].sort_values("depth_m")
            ax.plot(sub["depth_m"], sub[col], color=TYPE_COLOR[t], lw=2, label=t, zorder=3)
        ax.set_title(title); ax.set_xlabel("Flood depth (m)"); ax.set_ylim(0, 1)
        _finish(ax)
    axes[0].set_ylabel("Damage ratio")
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=5,
                   frameon=False, fontsize=9)
    fig.suptitle("Depth-damage curves by dwelling type",
                 fontsize=12, fontweight="bold", y=1.02)
    save(fig, "fig_4_6_curves_by_type.png")


# ---------------------------------------------------------------- Fig 4: hazard AUC
def fig_hazard_auc():
    c = pd.read_csv(ART / "hazard" / "hazard_coastal_comparison.csv")
    fl = pd.read_csv(ART / "hazard" / "hazard_fluvial_comparison.csv")
    order = ["Logistic regression", "Random forest", "Gradient boosting"]
    coastal = c.set_index("model")["roc_auc_mean"].reindex(order)
    fluv = fl[fl.task == "fluvial terrain + river"].set_index("model")["roc_auc_mean"].reindex(order)
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    x = np.arange(len(order)); w = 0.38
    ax.bar(x - w / 2, coastal, width=w, color=BLUE, label="Coastal (terrain)", zorder=3)
    ax.bar(x + w / 2, fluv, width=w, color=ORANGE, label="Fluvial (terrain + river distance)", zorder=3)
    for xi, v in zip(x - w / 2, coastal):
        ax.text(xi, v + 0.012, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    for xi, v in zip(x + w / 2, fluv):
        ax.text(xi, v + 0.012, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    ax.axhline(0.5, color=MUTED, lw=1, ls=":", zorder=1)
    ax.text(len(order) - 0.5, 0.51, "chance", fontsize=8, color=MUTED, ha="right")
    ax.set_xticks(x); ax.set_xticklabels(order)
    ax.set_ylabel("Held-out ROC AUC"); ax.set_ylim(0, 1.08)
    ax.set_title("Held-out ROC AUC by method")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              frameon=False, fontsize=9)
    _finish(ax)
    save(fig, "fig_4_1_hazard_auc.png")


# ---------------------------------------------------------------- Fig 5: quantile band
def fig_quantile_band():
    q = pd.read_csv(ART / "vulnerability_extended" / "quantile_bands.csv")
    q = q[q.breakdown == "dwelling type"]
    fig, axes = plt.subplots(1, 5, figsize=(12.5, 3.2), sharey=True)
    for ax, t in zip(axes, TYPES):
        sub = q[q.group == t].sort_values("depth_m")
        ax.fill_between(sub["depth_m"], sub["q10"], sub["q90"], color=BLUE, alpha=0.18, zorder=2)
        ax.plot(sub["depth_m"], sub["q50"], color=BLUE, lw=2, zorder=3)
        ax.set_title(t, fontsize=11); ax.set_xlabel("Depth (m)"); ax.set_ylim(0, 1)
        _finish(ax)
    axes[0].set_ylabel("Damage ratio")
    axes[0].legend(handles=[plt.Line2D([], [], color=BLUE, lw=2, label="Median (q50)"),
                            Patch(color=BLUE, alpha=0.18, label="q10–q90 band")],
                   loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Quantile predictive band by dwelling type",
                 fontsize=12, fontweight="bold", y=1.04)
    save(fig, "fig_4_5_quantile_band.png")


# ---------------------------------------------------------------- Fig 6: Dublin map
def fig_dublin_map():
    try:
        import geopandas as gpd
        from shapely.geometry import shape
    except Exception as e:
        progress.kv("skipped Dublin map", f"geopandas unavailable: {e}")
        return
    geo = json.loads((ART / "deployment" / "dublin_sa_geometry.json").read_text())
    df = pd.read_csv(ART / "deployment" / "dublin_damage_by_sa.csv")
    df["key"] = df["key"].astype(str)
    dmg = dict(zip(df["key"], df["m2_mid"]))
    recs = []
    for feat in geo["features"]:
        k = str(feat["properties"].get("key", feat.get("id")))
        recs.append({"key": k, "m2": dmg.get(k, 0.0), "geometry": shape(feat["geometry"])})
    gdf = gpd.GeoDataFrame(recs, crs="EPSG:4326")
    flooded = gdf[gdf.m2 > 0]
    fig, ax = plt.subplots(figsize=(7.6, 7.0))
    gdf.plot(ax=ax, color="#f2f2ee", edgecolor="white", linewidth=0.2, zorder=1)
    flooded.plot(ax=ax, column="m2", cmap="Blues", edgecolor="white", linewidth=0.2,
                 legend=True, zorder=2, vmin=0,
                 legend_kwds={"label": "Damaged floor-area equivalent (m²)", "shrink": 0.5})
    if len(flooded):
        minx, miny, maxx, maxy = flooded.total_bounds
        px, py = (maxx - minx) * 0.15, (maxy - miny) * 0.15
        ax.set_xlim(minx - px, maxx + px); ax.set_ylim(miny - py, maxy + py)
    ax.set_axis_off()
    ax.set_title("Dublin coastal 100-year flood: damaged floor area by small area (GAM curve)",
                 fontsize=11, fontweight="bold")
    save(fig, "fig_4_7_dublin_map.png")


# ---------------------------------------------------------------- Fig 7: confusion matrix
def fig_confusion():
    cm = pd.read_csv(ART / "exposure" / "exposure_confusion_matrix.csv", index_col=0)
    norm = cm.div(cm.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(6.0, 5.2))
    im = ax.imshow(norm.values, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(cm.columns))); ax.set_xticklabels(cm.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(cm.index))); ax.set_yticklabels(cm.index)
    ax.set_xlabel("Predicted type"); ax.set_ylabel("True type")
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            v = norm.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color="white" if v > 0.5 else INK, fontsize=9)
    ax.set_title("Confusion matrix: row-normalised recall by dwelling type")
    cb = fig.colorbar(im, ax=ax, shrink=0.8); cb.outline.set_visible(False)
    ax.tick_params(length=0)
    save(fig, "fig_4_2_exposure_confusion.png")


def _rel(p):
    try:
        return p.relative_to(config.REPO)
    except ValueError:
        return p


def missing_inputs():
    return {p: stage for p, stage in REQUIRED.items() if not p.exists()}


def main() -> int:
    with progress.stage("REPORT FIGURES: draw Chapter 4 figures from the latest run"):
        missing = missing_inputs()
        if missing:
            progress.step("cannot draw figures; some pipeline outputs are missing:")
            for p, stage in missing.items():
                progress.kv(f"  needs {stage}", _rel(p))
            progress.step("run the full pipeline (python run_all.py) or re-run the stage above, "
                          "then run this script again.")
            return 1
        OUT.mkdir(parents=True, exist_ok=True)
        for name, fn in [("model R²", fig_model_r2), ("ablation", fig_ablation),
                         ("curves by type", fig_curves_by_type), ("hazard AUC", fig_hazard_auc),
                         ("quantile band", fig_quantile_band), ("Dublin map", fig_dublin_map),
                         ("confusion matrix", fig_confusion)]:
            with progress.spinner(f"drawing {name}"):
                fn()
        progress.kv("figures written to", _rel(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
