import numpy as np
import pandas as pd

from src.vulnerability import fit_rf, ALL_FEATURES, TARGET, CANONICAL_TYPES


def _tiny_train(n=200):
    """Small valid training frame matching the real feature schema."""
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "type": rng.choice(CANONICAL_TYPES, n),
        "area": rng.uniform(50, 150, n),
        "storeys": rng.integers(1, 3, n).astype(float),
        "age": rng.uniform(0, 120, n),
        "masonry": rng.integers(0, 2, n).astype(float),
        "flood_depth": rng.uniform(0, 3, n),
        TARGET: rng.uniform(0, 1, n),
        "weight": rng.uniform(0.5, 2, n),
    })


def test_fit_rf_is_deterministic():
    df = _tiny_train()
    m1, p1 = fit_rf(df)
    m2, p2 = fit_rf(df)
    x = _tiny_train()  # same seed, so identical inputs
    pred1 = m1.predict(p1.transform(x[ALL_FEATURES]))
    pred2 = m2.predict(p2.transform(x[ALL_FEATURES]))
    np.testing.assert_array_equal(pred1, pred2)
