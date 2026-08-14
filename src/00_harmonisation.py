"""Stage 1: build the harmonised BER exposure profiles and common-grid reference damage curves used by the later stages."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from tqdm import tqdm

import config
from src import progress

GRID = np.array([0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])

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
        return "Detached"   # low confidence, flagged below
    return "Other"


def interp(depths, ratios):
    d = np.asarray(depths, float)
    r = np.asarray(ratios, float)
    ok = ~np.isnan(d) & ~np.isnan(r)
    d, r = d[ok], r[ok]
    order = np.argsort(d)
    return np.clip(np.interp(GRID, d[order], r[order], left=0), 0, 1)


def num(x):
    return pd.to_numeric(str(x).replace("​", "").replace("%", "").strip(), errors="coerce")


def build_exposure_profiles():
    with progress.spinner(f"reading BER dwellings from {config.BER_CSV.name} (~1.4M rows)"):
        ber = pd.read_csv(config.BER_CSV, usecols=BER_COLS, dtype=str)
    progress.kv("BER rows read", f"{len(ber):,}")
    ber["area"] = pd.to_numeric(ber["groundfloorarea(sq_m)"], errors="coerce")
    ber["storeys"] = pd.to_numeric(ber["nostoreys"], errors="coerce")
    ber["year"] = pd.to_numeric(ber["year_of_construction"], errors="coerce")

    tqdm.pandas(desc="  classifying dwelling type", ncols=78, file=sys.stdout)
    ber["canonical"] = ber.progress_apply(canonical, axis=1)
    ber["age_band"] = pd.cut(ber["year"], [0, 1945, 1980, 2100],
                             labels=["pre_1945", "1945_1980", "post_1980"])

    with progress.spinner("building county x dwelling-type profiles"):
        prof = ber.groupby(["countyname", "canonical"]).agg(
            n=("canonical", "size"),
            median_floor_area_m2=("area", "median"),
            pct_masonry=("firstwalltype_description", lambda s: 100 * s.astype(str).str.contains(
                "Cavity|Stone|Block|brick|Brick|Concrete", case=False, na=False).mean()),
            pct_pre1945=("age_band", lambda s: 100 * (s == "pre_1945").mean()),
        ).reset_index()
    prof.to_csv(config.EXPOSURE_PROFILES, index=False)
    progress.kv("county x type profiles", len(prof))
    for canon, count in ber["canonical"].value_counts().items():
        progress.kv(f"  dwellings {canon}", f"{count:,}")


def build_curve_family():
    _cf_sp = progress.spin_start("building reference-curve family (Middlesex + JRC)")
    fam = []

    # Middlesex per-type value ratios (MCM/FHRC lineage; the only per-type source).
    mid = pd.read_csv(config.MIDDLESEX_CSV, skiprows=2, encoding="utf-8")
    mid.columns = [str(c).replace("​", "").strip() for c in mid.columns]
    mid = mid.rename(columns={mid.columns[0]: "depth"})
    mid["depth"] = mid["depth"].apply(num)
    mid = mid[mid["depth"].notna()]
    midmap = {"Detached": "Detached", "Semi-Detached": "Semi-Detached", "Terrace": "Terrace",
              "Bungalow": "Bungalow", "Flat": "Apartment"}
    for col, canon in midmap.items():
        if col in mid.columns:
            r = interp(mid["depth"].values, mid[col].apply(num).values / 100.0)
            for d, v in zip(GRID, r):
                fam.append(("Middlesex", canon, "value_ratio", d, round(float(v), 4)))

    # JRC Huizinga continental residential curves (Europe, N. America, Oceania) from the Excel.
    hz = pd.read_excel(config.JRC_XLSX, sheet_name="Damage functions", header=None)
    start = hz.index[hz[0].astype(str).str.strip() == "Residential buildings"][0]
    block = hz.iloc[start:start + 9]            # depths 0,0.5,1,1.5,2,3,4,5,6
    hz_depth = pd.to_numeric(block[1], errors="coerce").values
    jrc_cols = {"JRC_Europe": 2, "JRC_NorthAmerica": 3, "JRC_Oceania": 7}
    for src, col in jrc_cols.items():
        vals = pd.to_numeric(block[col], errors="coerce").values
        rj = interp(hz_depth, vals)
        for canon in ["Detached", "Bungalow", "Semi-Detached", "Terrace", "Apartment"]:
            for d, v in zip(GRID, rj):
                fam.append((src, canon, "value_ratio", d, round(float(v), 4)))

    fam_df = pd.DataFrame(fam, columns=["source", "canonical_type", "metric", "depth_m", "damage_ratio"])
    fam_df.to_csv(config.CURVE_FAMILY, index=False)
    progress.spin_stop(_cf_sp)
    progress.kv("curve family rows", len(fam_df))
    progress.kv("sources", sorted(fam_df.source.unique()))

    vr = fam_df[(fam_df.metric == "value_ratio") & (fam_df.depth_m == 1.0)]
    progress.step("value-ratio spread at 1.0 m depth (the uncertainty prior):")
    print(vr.groupby("canonical_type").damage_ratio.agg(["min", "median", "max"]).round(3).to_string())


def main():
    with progress.stage("STAGE 1 DATA: harmonise BER + build reference-curve family"):
        build_exposure_profiles()
        build_curve_family()


if __name__ == "__main__":
    main()
