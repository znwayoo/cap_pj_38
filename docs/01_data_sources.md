# Data sources: what to download and where to put it

The raw data is not committed to this repository (licensing and size). `prepare_data.py` downloads the open sources, converts or extracts the manual drops, and places everything into the standardised layout the pipeline reads. No file needs to be renamed by hand.

## How to prepare the data

1. Seven sources are automatic: `saps`, `saps_boundaries`, `jrc`, `rainfall`, `dem`, `coastal`, and `fluvial`. `prepare_data.py` downloads and prepares them. You do not download these by hand.
2. Two sources are manual: `ber` and `middlesex`. Download each and drop the file as-is into `data/downloads/<label>/`, one source per folder. `prepare_data.py` converts or extracts it; the filename does not matter.
3. Run `python prepare_data.py`. It downloads the automatic sources, prepares the drops, and prints a present / missing / ambiguous checklist. If a source is temporarily unreachable it prints a `[skip]` line; download that one by hand and re-run.
4. When the checklist is all present, run `python run_all.py`.

`prepare_data.py --check` validates the layout without downloading or preparing anything.

## Datasets

| Label (drop folder) | Dataset | What it provides | Auto | Licence |
|---|---|---|---|---|
| `ber` | SEAI BER (dwelling energy ratings) | dwelling type, floor area, storeys, year, wall type for ~1.4M dwellings (exposure features) | no | SEAI research terms |
| `saps` | CSO Census 2022 Small Area Population Statistics | dwelling counts by coarse type per small area | yes | CC-BY 4.0 |
| `saps_boundaries` | Small Area boundaries 2022 (GeoPackage) | small-area geometry for the deployment map | yes | CC-BY 4.0 |
| `jrc` | JRC Huizinga (2017) global depth-damage functions | reference curves (Europe, North America, Oceania) as synthetic labels | yes | EC reuse |
| `middlesex` | Middlesex FHRC / Multi-Coloured Manual per-type curves | the only per-type reference curve; closest to current Irish appraisal practice | no | proprietary (MCM); do not redistribute |
| `dem` | Copernicus GLO-30 DEM | elevation and slope (hazard features), reprojected to Irish Transverse Mercator | yes | free/open |
| `coastal` | OPW national coastal flood depth (100-year) | coastal flood depth labels | yes | CC-BY-NC-ND 4.0 |
| `fluvial` | OPW NIFM river flood depth (100-year) tiles | fluvial flood depth labels (three Dublin tiles) | yes | CC-BY-NC-ND 4.0 |
| `rainfall` | Met Eireann 1981-2010 gridded annual rainfall | national rainfall feature | yes | CC-BY 4.0 |

The fluvial hazard stage also pulls OpenStreetMap watercourses live from the Overpass API at run time (no download; ODbL licence) to build the distance-to-river feature.

## Automatic sources

`prepare_data.py` downloads and prepares these. Nothing to do unless one prints a `[skip]` line, in which case download the link into `data/downloads/<label>/` and re-run.

- `saps`: https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_Small_Area_UR_171024.csv (small-area level; the pipeline reads `GEOGID`, `T6_1_HB_H`, `T6_1_FA_H`).
- `saps_boundaries`: https://data-osi.opendata.arcgis.com/api/download/v1/items/70a33cbb8bd7406da0d571be28624721/geoPackage?layers=0 . The OSi portal builds this GeoPackage on demand, so the first request returns a "Pending" response; `prepare_data.py` waits and retries until the file is ready (usually under a minute). To use a local copy instead, drop the `.gpkg` in `data/downloads/saps_boundaries/`.
- `jrc`: https://publications.jrc.ec.europa.eu/repository/bitstream/JRC105688/copy_of_global_flood_depth-damage_functions__30102017.xlsx (the Excel database, not the PDF on the same page).
- `rainfall`: https://www.met.ie/cms/assets/uploads/2024/07/IE_RR_8110_V2.zip (the `.txt` grid is unzipped).
- `dem`: the Copernicus GLO-30 tile covering Dublin, reprojected to EPSG:2157 at 30 m and clipped to the Dublin bounding box. To use a local tile instead, drop it as a `.tif` in `data/downloads/dem/`.
- `coastal`: https://s3.eu-west-1.amazonaws.com/catalogue.floodinfo.opw/ncfhm_itm_dep_c_c_2yr_5yr_20yr_50yr_100yr.zip (about 0.4 GB). The 100-year file `ncfhm_itm_dep_c_c_0100_f_00.tif` is extracted; the zip is deleted afterwards.
- `fluvial`: https://s3.eu-west-1.amazonaws.com/catalogue.floodinfo.opw/nifm/nifm_dep_f_c_0020_0100_1000.zip (about 1.7 GB). The three Dublin 100-year tiles `ing_07/08/09_dep_f_c_d_0100_f_01.tif` are extracted; the zip is deleted afterwards.

For `coastal` and `fluvial` you may instead drop the OPW zip, or the already-extracted `.tif` tiles, into the drop folder; the download is skipped when a zip or tiles are present.

## Manual sources

### `ber`

Register at https://ndber.seai.ie/BERResearchTool/Register/Register.aspx and log in. Click **Download All Data**, unzip the result, and drop the extracted file (`BERPublicsearch.txt`, about 1.4 GB) into `data/downloads/ber/`. `prepare_data.py` converts it to the comma CSV the pipeline reads. An already-converted `.csv` is used directly.

BER is a live dataset and SEAI serves only the latest export, which grows over time. A fresh download reproduces the report's BER-dependent figures closely but not exactly. For byte-identical figures, use the archived BER snapshot from the original run.

### `middlesex`

Drop the sponsor workbook `Combined_Flood_Data.xlsx` into `data/downloads/middlesex/`. `prepare_data.py` extracts the "Middlesex Uni" sheet. An already-extracted `.csv` is used directly. Do not redistribute.

## Standardised layout after preparation

```
data/
  ber/building_energy_ratings.csv
  census/saps.csv
  census/small_area_boundaries.gpkg
  curves/jrc_huizinga.xlsx
  curves/middlesex.csv
  hazard/dem_dublin.tif
  hazard/coastal_depth_rp100.tif
  hazard/fluvial/ing_07_dep_f_c_d_0100_f_01.tif (and ing_08, ing_09)
  rainfall/met_eireann_rr.txt
```

## Notes

- Minimum to run the vulnerability model: `ber`, `jrc`, and `middlesex`. The hazard and deployment stages additionally need the flood rasters, DEM, SAPS, and SAPS boundaries.
- `ber` and `middlesex` are the only manual sources, because they are gated and proprietary. Everything else is automatic.
- CFRAM licence (CC-BY-NC-ND): fine for academic testing with attribution; do not redistribute modified copies.
- Two datasets are deliberately out of scope (see `docs/03_methodology.md`): pluvial flood extents (not distributed in the open portal) and SCSI rebuild costs (not openly machine-readable). Euro is reported as a band instead.
