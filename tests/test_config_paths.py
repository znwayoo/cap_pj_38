import config


def test_standardised_names_no_dcodes():
    # data paths use plain names, never internal D-codes
    for p in [config.BER_CSV, config.SAPS_CSV, config.SAPS_GPKG, config.JRC_XLSX,
              config.MIDDLESEX_CSV, config.DEM_TIF, config.COASTAL_TIF,
              config.FLUVIAL_DIR, config.RAINFALL_TXT]:
        s = str(p)
        assert "/d0" not in s and "/d1" not in s and "/d2" not in s, f"D-code leaked in {s}"


def test_expected_standardised_paths():
    dd = config.DATA_DIR
    assert config.BER_CSV == dd / "ber" / "building_energy_ratings.csv"
    assert config.JRC_XLSX == dd / "curves" / "jrc_huizinga.xlsx"
    assert config.COASTAL_TIF == dd / "hazard" / "coastal_depth_rp100.tif"
    assert config.FLUVIAL_DIR == dd / "hazard" / "fluvial"


def test_data_dir_env_override(monkeypatch):
    import importlib
    monkeypatch.setenv("DATA_DIR", "/tmp/xyz")
    importlib.reload(config)
    assert str(config.DATA_DIR) == "/tmp/xyz"
    monkeypatch.delenv("DATA_DIR")
    importlib.reload(config)
