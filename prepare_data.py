"""Prepare datasets into the layout config.py expects; --check validates only. See docs/01_data_sources.md."""
import shutil
import ssl
import sys
import urllib.request
import zipfile
from dataclasses import dataclass

import config

# Use certifi's CA bundle for HTTPS; some Python installs (macOS) lack a system bundle.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()


def _download(url: str, dest) -> None:
    with urllib.request.urlopen(url, timeout=300, context=_SSL_CTX) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def _is_gpkg(path) -> bool:
    """Check the SQLite magic bytes; the OSi portal returns a 'Pending' JSON while it builds the file."""
    with open(path, "rb") as f:
        return f.read(16).startswith(b"SQLite format 3\x00")


def _download_generated(url: str, dest, attempts: int = 12, wait: int = 20) -> None:
    """Poll the OSi on-demand GeoPackage until the real file arrives, then give up for the manual drop."""
    import time
    for i in range(attempts):
        _download(url, dest)
        if _is_gpkg(dest):
            return
        if i == 0:
            print("      portal is generating the file; waiting for it to finish...")
        time.sleep(wait)
    raise ValueError(f"portal did not finish generating the GeoPackage after {attempts} tries")


@dataclass(frozen=True)
class Spec:
    label: str            # data/downloads/<label>/
    dest: object          # standardised config path
    ext: str              # expected file extension in the drop folder
    url: str = None       # direct URL if auto-downloadable
    note: str = ""


# Direct-URL downloads or a single dropped file; ber/middlesex/coastal/fluvial/dem use prepare_* below.
SPECS = [
    Spec("saps", config.SAPS_CSV, ".csv",
         url="https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_Small_Area_UR_171024.csv",
         note="CSO Census 2022 SAPS (small-area level)"),
    Spec("saps_boundaries", config.SAPS_GPKG, ".gpkg",
         url="https://data-osi.opendata.arcgis.com/api/download/v1/items/"
             "70a33cbb8bd7406da0d571be28624721/geoPackage?layers=0",
         note="OSi small-area boundaries (GeoPackage; portal generates on demand)"),
    Spec("jrc", config.JRC_XLSX, ".xlsx",
         url="https://publications.jrc.ec.europa.eu/repository/bitstream/JRC105688/copy_of_global_flood_depth-damage_functions__30102017.xlsx",
         note="JRC Huizinga 2017 curves"),
    Spec("rainfall", config.RAINFALL_TXT, ".txt",
         url="https://www.met.ie/cms/assets/uploads/2024/07/IE_RR_8110_V2.zip",
         note="Met Eireann 1981-2010 gridded rainfall (zip)"),
]

# ber/middlesex convert their drops; coastal/fluvial extract the Dublin 100-year tiles from OPW zips.
COASTAL_URL = ("https://s3.eu-west-1.amazonaws.com/catalogue.floodinfo.opw/"
               "ncfhm_itm_dep_c_c_2yr_5yr_20yr_50yr_100yr.zip")
COASTAL_MEMBER = "ncfhm_itm_dep_c_c_0100_f_00.tif"
FLUVIAL_URL = ("https://s3.eu-west-1.amazonaws.com/catalogue.floodinfo.opw/"
               "nifm/nifm_dep_f_c_0020_0100_1000.zip")
FLUVIAL_MEMBERS = ("ing_07_dep_f_c_d_0100_f_01.tif",
                   "ing_08_dep_f_c_d_0100_f_01.tif",
                   "ing_09_dep_f_c_d_0100_f_01.tif")

# DEM: raw Copernicus tile is WGS84; prepare_dem() reprojects to ITM at 30 m, clipped to Dublin.
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N53_00_W007_00_DEM/"
           "Copernicus_DSM_COG_10_N53_00_W007_00_DEM.tif")
DEM_CRS = "EPSG:2157"
DEM_BBOX = (712000, 728000, 730000, 745000)  # Dublin, ITM metres (E0, N0, E1, N1)
DEM_RES = 30.0


def _drop(label: str):
    return config.DATA_DIR / "downloads" / label


def _dropped_files(label: str):
    drop = _drop(label)
    if not drop.is_dir():
        return []
    return [p for p in drop.iterdir() if p.is_file() and not p.name.startswith(".")]


def download_open() -> None:
    for spec in SPECS:
        if spec.url and not spec.dest.exists():
            spec.dest.parent.mkdir(parents=True, exist_ok=True)
            print(f"  [download] {spec.label} <- {spec.url}")
            tmp = spec.dest.parent / "._dl"
            try:
                if spec.ext == ".gpkg":
                    _download_generated(spec.url, tmp)
                    tmp.rename(spec.dest)
                elif spec.url.endswith(".zip"):
                    _download(spec.url, tmp)
                    with zipfile.ZipFile(tmp) as z:
                        inner = [n for n in z.namelist() if n.endswith(spec.ext)][0]
                        with z.open(inner) as fsrc, open(spec.dest, "wb") as fdst:
                            shutil.copyfileobj(fsrc, fdst)
                    tmp.unlink()
                else:
                    _download(spec.url, tmp)
                    tmp.rename(spec.dest)
            except Exception as e:
                # One bad source should not abort prep; it can be downloaded by hand instead.
                if tmp.exists():
                    tmp.unlink()
                print(f"  [skip] {spec.label} auto-download failed ({e}); "
                      f"download it manually. See docs/01_data_sources.md.")


def standardise() -> list:
    """Move single-file drops to their standardised path; return ambiguous drops, never guessing."""
    problems = []
    for spec in SPECS:
        if spec.dest.exists():
            continue
        candidates = [p for p in _dropped_files(spec.label) if p.suffix.lower() == spec.ext]
        if len(candidates) > 1:
            problems.append(f"{spec.label}: {len(candidates)} {spec.ext} files in drop folder; keep exactly one")
            continue
        if candidates:
            spec.dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidates[0]), str(spec.dest))
            print(f"  [move] {candidates[0].name} -> {spec.dest.relative_to(config.DATA_DIR)}")
    return problems


def _convert_ber(src, dest, encoding: str) -> None:
    """Tab-delimited SEAI export -> comma CSV with lowercased, underscored headers; chunked, QUOTE_NONE."""
    import csv
    import pandas as pd
    first = True
    newcols = None
    for chunk in pd.read_csv(src, sep="\t", dtype=str, chunksize=200000,
                             encoding=encoding, quoting=csv.QUOTE_NONE):
        if first:
            newcols = [str(c).lower().replace(" ", "_") for c in chunk.columns]
        chunk.columns = newcols
        chunk.to_csv(dest, index=False, mode="w" if first else "a", header=first)
        first = False


def prepare_ber() -> None:
    """Produce building_energy_ratings.csv; a dropped .csv is used as-is, a .txt is converted."""
    if config.BER_CSV.exists():
        return
    files = _dropped_files("ber")
    if not files:
        return
    src = files[0]
    config.BER_CSV.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".csv":
        shutil.move(str(src), str(config.BER_CSV))
        print(f"  [move] {src.name} -> {config.BER_CSV.relative_to(config.DATA_DIR)}")
        return
    print(f"  [ber] converting {src.name} (tab-delimited) -> {config.BER_CSV.name}")
    try:
        _convert_ber(src, config.BER_CSV, "utf-8")
    except UnicodeDecodeError:
        _convert_ber(src, config.BER_CSV, "latin-1")


def prepare_middlesex() -> None:
    """Produce middlesex.csv by extracting the 'Middlesex Uni' sheet; a dropped .csv is used directly."""
    if config.MIDDLESEX_CSV.exists():
        return
    files = _dropped_files("middlesex")
    if not files:
        return
    src = files[0]
    config.MIDDLESEX_CSV.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".csv":
        shutil.move(str(src), str(config.MIDDLESEX_CSV))
        print(f"  [move] {src.name} -> {config.MIDDLESEX_CSV.relative_to(config.DATA_DIR)}")
        return
    import pandas as pd
    print(f"  [middlesex] extracting 'Middlesex Uni' sheet from {src.name} -> {config.MIDDLESEX_CSV.name}")
    sheet = pd.read_excel(src, sheet_name="Middlesex Uni", header=None)
    sheet.to_csv(config.MIDDLESEX_CSV, index=False, header=False)


def _match_member(z: zipfile.ZipFile, name: str) -> str:
    for n in z.namelist():
        if n.rsplit("/", 1)[-1] == name:
            return n
    raise KeyError(name)


def _flood_zip(label: str, url: str):
    """Return (zip_path, is_temp): a dropped .zip, or the url downloaded to a temp file to delete."""
    zips = [p for p in _dropped_files(label) if p.suffix.lower() == ".zip"]
    if zips:
        return zips[0], False
    tmp = config.DATA_DIR / "hazard" / f"._{label}.zip"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [download] {label} <- {url}")
    _download(url, tmp)
    return tmp, True


def prepare_coastal() -> None:
    """Produce coastal_depth_rp100.tif from a dropped .tif or the OPW coastal zip."""
    if config.COASTAL_TIF.exists():
        return
    tifs = [p for p in _dropped_files("coastal") if p.suffix.lower() == ".tif"]
    config.COASTAL_TIF.parent.mkdir(parents=True, exist_ok=True)
    if tifs:
        shutil.move(str(tifs[0]), str(config.COASTAL_TIF))
        print(f"  [move] {tifs[0].name} -> {config.COASTAL_TIF.relative_to(config.DATA_DIR)}")
        return
    try:
        zpath, is_tmp = _flood_zip("coastal", COASTAL_URL)
    except Exception as e:
        print(f"  [skip] coastal download failed ({e}). See docs/01_data_sources.md.")
        return
    try:
        with zipfile.ZipFile(zpath) as z:
            member = _match_member(z, COASTAL_MEMBER)
            with z.open(member) as fsrc, open(config.COASTAL_TIF, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
        print(f"  [coastal] extracted {COASTAL_MEMBER} -> {config.COASTAL_TIF.relative_to(config.DATA_DIR)}")
    except Exception as e:
        print(f"  [skip] coastal extract failed ({e}).")
    finally:
        if is_tmp and zpath.exists():
            zpath.unlink()


def prepare_fluvial() -> None:
    """Populate the fluvial dir with the three Dublin 100-year tiles from drops or the OPW fluvial zip."""
    if config.FLUVIAL_DIR.is_dir() and any(config.FLUVIAL_DIR.glob("*.tif")):
        return
    config.FLUVIAL_DIR.mkdir(parents=True, exist_ok=True)
    tifs = [p for p in _dropped_files("fluvial") if p.suffix.lower() == ".tif"]
    if tifs:
        for p in tifs:
            shutil.move(str(p), str(config.FLUVIAL_DIR / p.name))
            print(f"  [move] {p.name} -> {(config.FLUVIAL_DIR / p.name).relative_to(config.DATA_DIR)}")
        return
    try:
        zpath, is_tmp = _flood_zip("fluvial", FLUVIAL_URL)
    except Exception as e:
        print(f"  [skip] fluvial download failed ({e}). See docs/01_data_sources.md.")
        return
    try:
        with zipfile.ZipFile(zpath) as z:
            for name in FLUVIAL_MEMBERS:
                member = _match_member(z, name)
                with z.open(member) as fsrc, open(config.FLUVIAL_DIR / name, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                print(f"  [fluvial] extracted {name}")
    except Exception as e:
        print(f"  [skip] fluvial extract failed ({e}).")
    finally:
        if is_tmp and zpath.exists():
            zpath.unlink()


def _reproject_dem(src_path, dst_path) -> None:
    """Reproject the Copernicus tile to EPSG:2157 at 30 m, clipped to the Dublin bbox."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, Resampling

    e0, n0, e1, n1 = DEM_BBOX
    width = int(round((e1 - e0) / DEM_RES))
    height = int(round((n1 - n0) / DEM_RES))
    dst_transform = from_origin(e0, n1, DEM_RES, DEM_RES)  # top-left origin
    with rasterio.open(src_path) as src:
        profile = src.profile.copy()
        profile.update(crs=DEM_CRS, transform=dst_transform,
                       width=width, height=height, driver="GTiff")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=DEM_CRS,
                resampling=Resampling.bilinear,
            )


def prepare_dem() -> None:
    """Produce dem_dublin.tif from a dropped tile or the downloaded Dublin tile, reprojected and clipped."""
    if config.DEM_TIF.exists():
        return
    dropped = [p for p in _dropped_files("dem") if p.suffix.lower() == ".tif"]
    tmp = None
    if dropped:
        raw = dropped[0]
    else:
        config.DEM_TIF.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.DEM_TIF.parent / "._dem_raw.tif"
        print(f"  [download] dem <- {DEM_URL}")
        try:
            _download(DEM_URL, tmp)
            raw = tmp
        except Exception as e:
            if tmp.exists():
                tmp.unlink()
            print(f"  [skip] dem auto-download failed ({e}); download the tile by hand. "
                  f"See docs/01_data_sources.md.")
            return
    try:
        _reproject_dem(raw, config.DEM_TIF)
        print(f"  [dem] reprojected to ITM, clipped to Dublin -> "
              f"{config.DEM_TIF.relative_to(config.DATA_DIR)}")
    except Exception as e:
        print(f"  [skip] dem reprojection failed ({e}).")
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


CHECKS = [
    ("ber", config.BER_CSV),
    ("saps", config.SAPS_CSV),
    ("saps_boundaries", config.SAPS_GPKG),
    ("jrc", config.JRC_XLSX),
    ("middlesex", config.MIDDLESEX_CSV),
    ("coastal", config.COASTAL_TIF),
    ("rainfall", config.RAINFALL_TXT),
    ("dem", config.DEM_TIF),
]


def validate(verbose: bool = False) -> bool:
    ok = True
    for label, dest in CHECKS:
        present = dest.exists()
        ok = ok and present
        if verbose:
            print(f"  [{'OK ' if present else 'MISS'}] {label:<16} {dest.relative_to(config.DATA_DIR)}")
    fluvial_ok = config.FLUVIAL_DIR.is_dir() and any(config.FLUVIAL_DIR.glob("*.tif"))
    ok = ok and fluvial_ok
    if verbose:
        print(f"  [{'OK ' if fluvial_ok else 'MISS'}] {'fluvial':<16} {config.FLUVIAL_DIR.relative_to(config.DATA_DIR)}/*.tif")
    return ok


def main(argv) -> int:
    if "--check" not in argv:
        download_open()
        problems = standardise()
        prepare_ber()
        prepare_middlesex()
        prepare_coastal()
        prepare_fluvial()
        prepare_dem()
        for p in problems:
            print(f"  AMBIGUOUS: {p}")
    print("\nData layout check:")
    ok = validate(verbose=True)
    if not ok:
        print("\nSome datasets are missing. See docs/01_data_sources.md; save each into data/downloads/<label>/ and re-run.")
        return 1
    print("\nAll datasets present and standardised. Next: python run_all.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
