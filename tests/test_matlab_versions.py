import io
import json
import re

import pytest

import matlab_versions as mv
from matlab_versions.__main__ import main

LMSTAT = """\
lmutil - Copyright (c) 1989-2025 Flexera. All Rights Reserved.
Flexible License Manager status on Tue 11/10/2026 10:20

Users of MATLAB:  (Total of 25 licenses issued;  Total of 3 licenses in use)

  "MATLAB" v55, vendor: MLM, expiry: 01-jan-0000
  floating license

    alice host1 /dev/pts/1 (v45) (lic.example.org/27000 6741), start Tue 11/10 8:43, PID: 57590
    bob host2 /dev/tty (v51) (lic.example.org/27000 3423), start Tue 11/10 10:15, PID: 4157333
    carol ws3 ws3 (v54) (lic.example.org/27000 101), start Mon 11/9 9:00

Users of Signal_Toolbox:  (Total of 9 licenses issued;  Total of 1 license in use)

  "Signal_Toolbox" v55, vendor: MLM, expiry: 01-jan-0000
  floating license

    bob host2 /dev/tty (v51) (lic.example.org/27000 3424), start Tue 11/10 10:16, PID: 4157333
"""


# --- the table --------------------------------------------------------------

def test_table_is_contiguous_and_consistent():
    rels = mv.releases()
    assert rels[0].name == "R2006a"
    expected = [f"R{y}{h}" for y in range(2006, 2006 + len(rels) // 2 + 1) for h in "ab"][: len(rels)]
    assert [r.name for r in rels] == expected
    levels = set(mv.data()["evidence_levels"])
    sources = set(mv.data()["sources"])
    for r in rels:
        assert r.matlab is not None
        assert set(r.evidence.values()) <= levels
        assert {s for ss in r.sources.values() for s in ss} <= sources


def test_license_column_follows_rule():
    for r in mv.releases():
        if r.license is not None:
            assert r.license == 2 * (r.year - 2008) + 19 + (r.half == "b")
    assert [r.name for r in mv.releases() if r.license is None] == ["R2006a", "R2006b"]


def test_matlab_column_follows_rule_from_r2023b():
    for r in mv.releases():
        if (r.year, r.half) >= (2023, "b"):
            assert r.matlab == f"{r.year % 100}.{'1' if r.half == 'a' else '2'}"


def test_values_are_unique_per_column():
    for col in ("matlab", "runtime", "license"):
        values = [getattr(r, col) for r in mv.releases() if getattr(r, col) is not None]
        assert len(values) == len(set(values)), col
    folders = [r.runtime_folder for r in mv.releases() if r.runtime_folder]
    assert len(folders) == len(set(folders))


# --- known pairs --------------------------------------------------------------

@pytest.mark.parametrize(
    "name, matlab, runtime, folder, lic",
    [
        ("R2012a", "7.14", "7.17", "v717", 27),
        ("R2015b", "8.6", "9.0", "v90", 34),
        ("R2016a", "9.0", "9.0.1", "v901", 35),
        ("R2019b", "9.7", "9.7", "v97", 42),
        ("R2021a", "9.10", "9.10", "v910", 45),
        ("R2022a", "9.12", "9.12", "v912", 47),
        ("R2022b", "9.13", "9.13", "R2022b", 48),
        ("R2023a", "9.14", "9.14", "R2023a", 49),
        ("R2024a", "24.1", "24.1", "R2024a", 51),
        ("R2026a", "26.1", "26.1", "R2026a", 55),
    ],
)
def test_known_release(name, matlab, runtime, folder, lic):
    r = mv.release(name)
    assert (r.matlab, r.runtime, r.runtime_folder, r.license) == (matlab, runtime, folder, lic)
    assert mv.from_matlab(matlab) == r
    assert mv.from_runtime(runtime) == r
    assert mv.from_runtime(folder) == r
    assert mv.from_license(lic) == r


def test_runtime_unknown_before_r2012a():
    r = mv.release("R2011b")
    assert r.runtime is None and r.runtime_folder is None
    with pytest.raises(ValueError):
        mv.from_runtime("R2011b")


# --- spellings ----------------------------------------------------------------

@pytest.mark.parametrize("term", ["R2024a", "2024a", "r2024A", " R2024a "])
def test_release_spellings(term):
    assert mv.release(term).name == "R2024a"


@pytest.mark.parametrize("term", [51, "51", "v51", "V51", "v51.0", " v51 "])
def test_license_spellings(term):
    assert mv.from_license(term).name == "R2024a"


@pytest.mark.parametrize("term", ["9.10", "9.10.0.1739362", "9.10.0.1739362 (R2021a)"])
def test_matlab_spellings(term):
    assert mv.from_matlab(term).name == "R2021a"


def test_matlab_9_1_is_not_9_10():
    assert mv.from_matlab("9.1.0.441655").name == "R2016b"


# --- newer than the table -----------------------------------------------------

def test_extrapolation_beyond_table():
    newest = mv.releases()[-1]
    nxt = mv.from_license(newest.license + 1)
    assert nxt.evidence["license"] == "extrapolated"
    assert mv.release(nxt.name).license == nxt.license
    assert mv.from_matlab(nxt.matlab).name == nxt.name
    assert mv.from_runtime(nxt.matlab).name == nxt.name
    assert mv.release("R2030b").matlab == "30.2"
    assert mv.release("R2030b").license == 64


@pytest.mark.parametrize("fn, bad", [
    (mv.release, "R2005b"), (mv.release, "R14SP3"), (mv.release, "R2024c"), (mv.release, "51"),
    (mv.from_license, 16), (mv.from_license, "abc"), (mv.from_license, "R2024a"),
    (mv.from_matlab, "8.9"), (mv.from_matlab, "24"), (mv.from_matlab, "23.5"),
    (mv.from_runtime, "v999"), (mv.from_runtime, "7.14"),
])
def test_rejects(fn, bad):
    with pytest.raises(ValueError):
        fn(bad)


# --- lookup -------------------------------------------------------------------

def _readings(term):
    return [(kind, r.name) for kind, r in mv.lookup(term)]


def test_lookup_reports_ambiguity():
    assert _readings("9.0") == [("matlab", "R2016a"), ("runtime", "R2015b")]
    # 24.1 is never a licence version: MathWorks uses whole numbers
    assert _readings("24.1") == [("matlab", "R2024a"), ("runtime", "R2024a")]


def test_lookup_kinds():
    assert _readings("R2024a") == [("name", "R2024a")]
    assert _readings("v51") == [("license", "R2024a")]
    assert _readings("51") == [("license", "R2024a")]
    assert _readings("v914") == []  # R2023a installs under "R2023a"; licence 914 is centuries away
    assert _readings("v910") == [("runtime", "R2021a")]
    assert _readings("v91") == [("runtime", "R2016b")]  # licence 91 would be R2044a: too far ahead
    assert _readings("v57") == [("license", "R2027a")]  # next releases still resolve
    assert _readings("nonsense") == []


@pytest.mark.parametrize("term", ["51.0", "v51.0", " 51.0 "])
def test_lookup_dotted_license(term):
    assert _readings(term) == [("license", "R2024a")]


@pytest.mark.parametrize("term", ["v100", "V100", " v100 ", "v100.0"])
def test_lookup_far_future_license_is_rejected(term):
    assert _readings(term) == []


def test_dotted_license_must_be_whole():
    assert mv.from_license("v51.0").name == "R2024a"
    for bad in ("24.1", "v51.5"):
        with pytest.raises(ValueError):
            mv.from_license(bad)


def test_extrapolation_horizon():
    newest = mv.releases()[-1]
    last_ok = newest.license + mv.MAX_RELEASES_AHEAD
    assert mv.from_license(last_ok).evidence["license"] == "extrapolated"
    far = mv.from_license(last_ok)
    assert mv.release(far.name) == far
    with pytest.raises(ValueError, match="releases after the newest"):
        mv.from_license(last_ok + 1)
    with pytest.raises(ValueError):
        mv.release("R2453b")
    with pytest.raises(ValueError):
        mv.from_matlab("53.2")
    line = "    bob host2 /dev/tty (v910) (lic.example.org/27000 1), start Tue 11/10 10:15"
    assert mv.parse_checkout(line).release is None


def test_cli_survives_closed_pipe():
    import subprocess, sys
    r = subprocess.run(
        f"{sys.executable} -m matlab_versions --json | head -c 10 >/dev/null",
        shell=True, capture_output=True, text=True,
    )
    assert "Traceback" not in r.stderr and "BrokenPipe" not in r.stderr


# --- lmstat -------------------------------------------------------------------

def test_parse_checkout_line():
    c = mv.parse_checkout(LMSTAT.splitlines()[9])
    assert c == mv.Checkout(
        user="bob", host="host2", display="/dev/tty", version=51, server="lic.example.org",
        port=27000, handle=3423, start="Tue 11/10 10:15", pid=4157333,
    )
    assert c.release.name == "R2024a"


def test_parse_ignores_other_lines():
    for line in LMSTAT.splitlines()[:8]:
        assert mv.parse_checkout(line) is None


def test_parse_lmstat_tracks_feature():
    got = [(c.feature, c.user, c.release.name) for c in mv.parse_lmstat(LMSTAT)]
    assert got == [
        ("MATLAB", "alice", "R2021a"),
        ("MATLAB", "bob", "R2024a"),
        ("MATLAB", "carol", "R2025b"),
        ("Signal_Toolbox", "bob", "R2024a"),
    ]


# --- command line -------------------------------------------------------------

def test_cli_lookup(capsys):
    assert main(["v51", "9.0"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "v51 (licence version)\tR2024a\tmatlab 24.1\truntime 24.1 (R2024a)\tlicense v51"
    assert out[1].startswith("9.0 (MATLAB version)\tR2016a")
    assert out[2].startswith("9.0 (Runtime)\tR2015b")


def test_cli_marks_extrapolated(capsys):
    assert main(["R2026b"]) == 0
    assert capsys.readouterr().out.strip().endswith("license v56*")


def test_cli_no_match(capsys):
    assert main(["nonsense"]) == 2


def test_cli_stdin_summary(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(LMSTAT))
    assert main(["--summary"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "MATLAB\tR2021a\t1",
        "MATLAB\tR2024a\t1",
        "MATLAB\tR2025b\t1",
        "Signal_Toolbox\tR2024a\t1",
    ]


def test_cli_json_roundtrips(capsys):
    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out) == mv.data()


def test_release_names_are_well_formed():
    assert all(re.fullmatch(r"R20\d\d[ab]", r.name) for r in mv.releases())
