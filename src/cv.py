"""Cross-validation with a live spinner; mirrors cross_val_score / cross_val_predict."""
import numpy as np
from sklearn.base import clone
from sklearn.metrics import get_scorer

from src import progress


def _take(a, idx):
    """Index a numpy array or a pandas DataFrame/Series by row positions."""
    return a.iloc[idx] if hasattr(a, "iloc") else a[idx]


def cv_scores(model, X, y, splitter, scoring, desc):
    """Per-fold scores under a spinner; equivalent to cross_val_score."""
    scorer = get_scorer(scoring)
    splits = list(splitter.split(X, y))
    out = []
    with progress.spinner(f"{desc} ({len(splits)}-fold CV)"):
        for tr, te in splits:
            fitted = clone(model).fit(_take(X, tr), _take(y, tr))
            out.append(scorer(fitted, _take(X, te), _take(y, te)))
    return np.array(out)


def cv_oof_predict(model, X, y, splitter, desc):
    """Out-of-fold predictions under a spinner; equivalent to cross_val_predict."""
    splits = list(splitter.split(X, y))
    pred = np.empty(len(y), dtype=object)
    with progress.spinner(f"{desc} ({len(splits)}-fold CV)"):
        for tr, te in splits:
            fitted = clone(model).fit(_take(X, tr), _take(y, tr))
            pred[te] = fitted.predict(_take(X, te))
    return pred
