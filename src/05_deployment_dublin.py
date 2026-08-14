"""Stage 5: apply the depth-damage curve to Dublin small areas under the OPW 100-year coastal flood and write per-area damage plus map geometry."""
import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
from src import progress

# Rebuild cost is reported as a band across illustrative EUR/m2 levels, not a single figure.
RATES = [2000, 2500, 3000, 3500]
RATE_CENTRAL = 2500.0     # illustrative headline level only
CURVE_MODEL = "GAM"       # the deployed curve: the trained GAM, banded by source disagreement
BBOX = (712000, 728000, 730000, 745000)  # E,N Dublin city + coast


def curve_at(df, t, depth, col):
    s = df[df.canonical_type == t].sort_values("depth_m")
    return float(np.interp(depth, s.depth_m, s[col]))


def main():
    with progress.stage("STAGE 5 DEPLOY: apply curve to Dublin, euro band"):
        needed = {
            config.ARTIFACTS / "vulnerability_extended" / "curves_by_model.csv": "stage 4 (vulnerability)",
            config.CURVE_FAMILY: "stage 1 (harmonisation)",
            config.HARMONISED_DIR / "irish_exposure_ber_profiles.csv": "stage 1 (harmonisation)",
        }
        missing = {p: s for p, s in needed.items() if not p.exists()}
        if missing:
            progress.step("missing upstream outputs; run the earlier stages first (or python run_all.py):")
            for p, s in missing.items():
                progress.kv(f"  needs {s}", p.relative_to(config.REPO))
            return
        _models = pd.read_csv(config.ARTIFACTS / "vulnerability_extended/curves_by_model.csv")
        curve = (_models[_models.model == CURVE_MODEL]
                 .rename(columns={"damage_ratio": "curve_mid"})[["canonical_type", "depth_m", "curve_mid"]])
        if curve.empty:
            raise SystemExit(f"no {CURVE_MODEL} curve found; run the vulnerability stage first")
        band = (pd.read_csv(config.CURVE_FAMILY)
                .groupby(["canonical_type", "depth_m"]).damage_ratio
                .agg(band_lower="min", band_upper="max").reset_index())

        progress.step("bridging coarse SAPS types to fine types via BER county proportions")
        prof = pd.read_csv(config.HARMONISED_DIR / "irish_exposure_ber_profiles.csv")
        dub = prof[prof.countyname.astype(str).str.contains("Dublin", case=False, na=False)]
        house = dub[dub.canonical.isin(["Detached", "Semi-Detached", "Terrace", "Bungalow"])]
        hb_share = (house.groupby("canonical").n.sum() / house.n.sum()).to_dict()
        area_by_type = dub.groupby("canonical").median_floor_area_m2.median().to_dict()
        progress.kv("Dublin house/bungalow split", {k: round(v, 3) for k, v in hb_share.items()})

        with progress.spinner("reading Dublin small areas and SAPS dwelling counts"):
            sa = gpd.read_file(config.SAPS_GPKG, bbox=BBOX, engine="pyogrio")
            saps = pd.read_csv(config.SAPS_CSV,
                               usecols=["GEOGID", "T6_1_HB_H", "T6_1_FA_H"], dtype={"GEOGID": str})
        saps["T6_1_HB_H"] = pd.to_numeric(saps["T6_1_HB_H"], errors="coerce")
        saps["T6_1_FA_H"] = pd.to_numeric(saps["T6_1_FA_H"], errors="coerce")
        sa["key"] = sa["SA_PUB2022"].astype(str)
        sa = sa.merge(saps, left_on="key", right_on="GEOGID", how="left").fillna({"T6_1_HB_H": 0, "T6_1_FA_H": 0})
        progress.kv("Dublin small areas in bbox", len(sa))

        progress.step("sampling OPW 100-year coastal depth per small area")
        with rasterio.open(config.COASTAL_TIF) as src:
            win = src.window(*BBOX)
            arr = src.read(1, window=win)
            tr = src.window_transform(win)
            nod = src.nodata
        arr = np.where((arr == nod) | (arr < 0), np.nan, arr)
        depths, ffrac = [], []
        for geom in progress.progress(sa.geometry, desc="masking small areas", total=len(sa)):
            try:
                m = geometry_mask([geom], out_shape=arr.shape, transform=tr, invert=True)
                cell = arr[m]
                flooded_cells = cell[(~np.isnan(cell)) & (cell >= 0.2)]
                depths.append(float(flooded_cells.mean()) if flooded_cells.size else 0.0)
                ffrac.append(float(flooded_cells.size / max(cell.size, 1)))
            except Exception:
                depths.append(0.0)
                ffrac.append(0.0)
        sa["flood_depth_m"] = depths
        sa["flood_frac"] = ffrac

        def damaged_m2(row, df, col):
            d = row.flood_depth_m
            if d < 0.2 or row.flood_frac <= 0:
                return 0.0
            tot = 0.0
            for t, share in hb_share.items():
                n = row.T6_1_HB_H * share * row.flood_frac
                tot += n * area_by_type.get(t, 90) * curve_at(df, t, d, col)
            n_ap = row.T6_1_FA_H * row.flood_frac
            tot += n_ap * area_by_type.get("Apartment", 70) * curve_at(df, "Apartment", d, col)
            return tot

        with progress.spinner("applying the damage curve to each small area"):
            for df_, col, name in [(curve, "curve_mid", "m2_mid"),
                                   (band, "band_lower", "m2_lo"), (band, "band_upper", "m2_hi")]:
                sa[name] = sa.apply(lambda r, d=df_, c=col: damaged_m2(r, d, c), axis=1)
        for m2c, eurc in [("m2_lo", "dmg_lo"), ("m2_mid", "dmg_eur"), ("m2_hi", "dmg_hi")]:
            sa[eurc] = sa[m2c] * RATE_CENTRAL

        flooded = sa[sa.m2_mid > 0]
        m2_mid, m2_lo, m2_hi = sa.m2_mid.sum(), sa.m2_lo.sum(), sa.m2_hi.sum()
        progress.kv("flooded small areas", len(flooded))
        progress.kv(f"damaged floor-area equivalent ({CURVE_MODEL})",
                    f"{m2_mid:,.0f} m2 (band {m2_lo:,.0f} to {m2_hi:,.0f} m2)")
        progress.kv("illustrative euro headline",
                    f"EUR {m2_mid * RATE_CENTRAL / 1e6:.0f}M at {RATE_CENTRAL:.0f}/m2 "
                    f"(band {m2_lo * RATE_CENTRAL / 1e6:.0f} to {m2_hi * RATE_CENTRAL / 1e6:.0f}M)")
        progress.kv("euro envelope",
                    f"EUR {m2_lo * min(RATES) / 1e6:.0f}M to {m2_hi * max(RATES) / 1e6:.0f}M "
                    f"(rebuild {min(RATES)}-{max(RATES)}/m2, illustrative)")

        out = config.ARTIFACTS / "deployment"
        out.mkdir(parents=True, exist_ok=True)
        sa[["key", "T6_1_HB_H", "T6_1_FA_H", "flood_depth_m", "flood_frac",
            "m2_lo", "m2_mid", "m2_hi", "dmg_lo", "dmg_eur", "dmg_hi"]].to_csv(
                out / "dublin_damage_by_sa.csv", index=False)

        # small-area geometry (EPSG:4326) for the Dublin map; id = SA key
        with progress.spinner("writing small-area geometry (GeoJSON)"):
            geo = sa[["key", "geometry"]].to_crs(4326)
            gj = json.loads(geo.to_json())
            for feat in gj["features"]:
                feat["id"] = feat["properties"]["key"]
            (out / "dublin_sa_geometry.json").write_text(json.dumps(gj))

        png = out / "dublin_damage_map.png"
        with progress.spinner("rendering the Dublin damage map"):
            fig, ax = plt.subplots(figsize=(11, 11))
            sa.plot(ax=ax, color="#eeeeee", edgecolor="#cccccc", linewidth=0.2)
            if len(flooded):
                flooded.plot(ax=ax, column="dmg_eur", cmap="Reds", legend=True, edgecolor="#600", linewidth=0.3,
                             legend_kwds={"label": "estimated residential damage (EUR)", "shrink": 0.5})
            ax.set_title(f"Trained {CURVE_MODEL} curve applied to Dublin, 100-year coastal flood\n"
                         f"{len(flooded)} small areas flood; {m2_mid / 1e3:.0f}k m2 damaged-equivalent "
                         f"(curve band {m2_lo / 1e3:.0f}k to {m2_hi / 1e3:.0f}k)", fontsize=10)
            ax.set_axis_off()
            plt.savefig(str(png), dpi=130, bbox_inches="tight")
        progress.kv("wrote", "dublin_damage_by_sa.csv and dublin_damage_map.png")


if __name__ == "__main__":
    main()
