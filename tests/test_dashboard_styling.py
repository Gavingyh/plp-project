"""
Tests for the dashboard's heatmap styling.

These exist because of a bug that shipped in the first dashboard commit and
survived every run since: the Aspect Heatmap and per-source tables call
pandas' `Styler.background_gradient`, which requires matplotlib, and
matplotlib was never in requirements.txt. Neither table had ever rendered.

Two things made it hard to notice.

`Styler.background_gradient` is LAZY. Building the Styler succeeds; the
matplotlib import happens at render time inside `st.dataframe`, via
`Styler._compute()`. A try/except around the call site would not have caught
it, and neither does importing the module.

And the service health check passes. `/_stcore/health` reports that the
Streamlit server is up, not that any page renders, so `scripts/start.sh`
reported a healthy dashboard while two of its tables raised ImportError.

The test therefore forces `_compute()`, which is the only thing that actually
exercises the failure.
"""

import importlib.util

import pandas as pd
import pytest


def _frame():
    """Shaped like the real pivots: sources or aspects by bank, scores in -1..1."""
    return pd.DataFrame(
        {"DBS": [0.168, -0.002], "OCBC": [0.206, -0.011], "UOB": [0.229, -0.011]},
        index=["earnings", "arctic_shift"],
    )


def test_matplotlib_is_available():
    """The dependency the dashboard's heatmaps need, declared in requirements.txt.

    A plain import check, because the failure this guards against is simply
    that nobody declared it.
    """
    assert importlib.util.find_spec("matplotlib") is not None, (
        "matplotlib is missing. The dashboard's heatmap tables need it for "
        "Styler.background_gradient. Install it: "
        ".venv-plp/bin/python3 -m pip install -r requirements.txt"
    )


def test_background_gradient_renders_not_just_builds():
    """The regression itself.

    Building the Styler always succeeds. Only `_compute()` triggers the
    matplotlib import, which is what st.dataframe does internally, and what
    raised ImportError on the live dashboard.
    """
    styler = _frame().style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1).format("{:.3f}")
    styler._compute()  # must not raise
    assert styler.to_html()


def test_styler_construction_alone_would_not_have_caught_it():
    """Documents why the obvious test is worthless here.

    If this ever starts failing, the laziness assumption above has changed and
    the comment in dashboard/app.py should be revisited.
    """
    frame = _frame()
    # No _compute(), so no matplotlib import: this succeeds even when the
    # dependency is absent.
    styler = frame.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1)
    assert styler is not None


def test_heatmap_helper_falls_back_without_matplotlib(monkeypatch):
    """With matplotlib absent the tables must lose their colour, not the page.

    The helper is re-implemented here rather than imported: dashboard/app.py is
    a Streamlit script that runs its whole UI at import time, so importing it
    in a test is not possible. That makes this a contract test for the shape of
    the fallback, and `test_matplotlib_is_available` is what guards the real
    dependency.
    """
    frame = _frame()

    def heatmap_table(f, has_matplotlib):
        if has_matplotlib:
            return f.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1).format("{:.3f}")
        return f.round(3)

    plain = heatmap_table(frame, has_matplotlib=False)
    assert isinstance(plain, pd.DataFrame), "fallback must still be renderable by st.dataframe"
    assert plain.loc["earnings", "UOB"] == pytest.approx(0.229)

    styled = heatmap_table(frame, has_matplotlib=True)
    styled._compute()
    assert hasattr(styled, "to_html")


def test_dashboard_routes_both_heatmaps_through_the_helper():
    """Guards against a future edit reintroducing a bare background_gradient
    call at a call site, which would bypass the fallback."""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "dashboard", "app.py")
    with open(path, encoding="utf-8") as f:
        source = f.read()

    # Exactly one background_gradient CALL, inside the helper. Counting the
    # bare name would also match the explanatory comment above it.
    assert source.count("background_gradient(") == 1, (
        "dashboard/app.py should call background_gradient only inside "
        "heatmap_table(); a second call site would skip the matplotlib guard."
    )
    assert source.count("heatmap_table(") >= 3, (
        "expected the helper definition plus both heatmap call sites"
    )
