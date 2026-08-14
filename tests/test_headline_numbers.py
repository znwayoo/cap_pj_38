"""Guard the headline Dublin results against regression (read from the deployment artifact)."""
import pandas as pd

import config


def test_dublin_headline():
    df = pd.read_csv(config.ARTIFACTS / "deployment" / "dublin_damage_by_sa.csv")
    flooded = df[df["m2_mid"] > 0]
    # 379 small areas flood; 536,810 m2 damaged floor-area equivalent.
    assert len(flooded) == 379
    assert round(flooded["m2_mid"].sum()) == 536810


def test_dublin_band():
    df = pd.read_csv(config.ARTIFACTS / "deployment" / "dublin_damage_by_sa.csv")
    # Source-disagreement band: 136,027 to 782,435 m2.
    assert round(df["m2_lo"].sum()) == 136027
    assert round(df["m2_hi"].sum()) == 782435
