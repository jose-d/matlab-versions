import pytest

import matlab_versions as mv


@pytest.mark.parametrize(
    "version, name",
    [
        ("9.0.1.123", "R2016a"),
        ("9.0.1.123.456", "R2016a"),
        ("9.0.1.123 (R2016a)", "R2016a"),
        ("9.0.1", "R2016a"),
        ("9.0", "R2015b"),
        ("9.0.2.123", "R2015b"),
        ("9.0.10.123", "R2015b"),
        ("9.10.0.1739362", "R2021a"),
    ],
)
def test_runtime_uses_longest_known_component_prefix(version, name):
    assert mv.from_runtime(version).name == name


def test_each_known_runtime_accepts_build_components():
    for release in mv.releases():
        if release.runtime is not None:
            assert mv.from_runtime(release.runtime + ".123.456") == release


def test_future_runtime_accepts_build_components():
    newest = mv.releases()[-1]
    future = mv.from_license(newest.license + 1)
    assert mv.from_runtime(future.runtime + ".123.456") == future


def test_unknown_runtime_prefix_is_rejected():
    with pytest.raises(ValueError, match="unknown MATLAB Runtime version"):
        mv.from_runtime("9.100.1.123")
