import numpy as np
import pandas as pd

from src.vulnerability import (
    fit_rf, ALL_FEATURES, TARGET, CANONICAL_TYPES, _training_frame_cache_key,
)


def _frame(n=300):
    """Small frame with the same columns and dtypes as the real training frame."""
    rng = np.random.default_rng(1)
    return pd.DataFrame({
        "dwelling_id": np.arange(n),
        "type": rng.choice(CANONICAL_TYPES, n),
        "area": rng.uniform(50, 200, n),
        "storeys": rng.integers(1, 3, n).astype(float),
        "age": rng.uniform(1900, 2020, n),
        "masonry": rng.integers(0, 2, n).astype(float),
        "flood_depth": rng.uniform(0, 3, n),
        TARGET: rng.uniform(0, 1, n),
        "weight": rng.uniform(0.5, 2, n),
        "countyname": rng.choice(["A", "B"], n),
    })


def test_parquet_roundtrip_preserves_frame_and_training(tmp_path):
    df = _frame()
    path = tmp_path / "frame.parquet"
    df.to_parquet(path, index=False)
    reloaded = pd.read_parquet(path)
    pd.testing.assert_frame_equal(df, reloaded)
    # a model trained on the cached (reloaded) frame predicts identically
    m1, pre1 = fit_rf(df)
    m2, pre2 = fit_rf(reloaded)
    x = _frame()
    np.testing.assert_array_equal(
        m1.predict(pre1.transform(x[ALL_FEATURES])),
        m2.predict(pre2.transform(x[ALL_FEATURES])),
    )


def test_cache_key_is_deterministic_and_seed_sensitive():
    assert _training_frame_cache_key(7) == _training_frame_cache_key(7)
    assert _training_frame_cache_key(7) != _training_frame_cache_key(8)
