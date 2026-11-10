"""Translate between the identifiers of a MATLAB release.

Every MATLAB release has several numbers, and they are easy to mix up:

=========  ==============  ===============  ===============  ===============
Release    MATLAB version  Runtime version  Runtime folder   FlexLM (lmstat)
=========  ==============  ===============  ===============  ===============
R2016a     9.0             9.0.1            v901             v35
R2021a     9.10            9.10             v910             v45
R2024a     24.1            24.1             R2024a           v51
=========  ==============  ===============  ===============  ===============

* the **MATLAB version** is what ``version()`` and ``VersionInfo.xml`` report;
* the **MATLAB Runtime version** is what compiled applications need, installed
  under a folder named ``v910`` (up to R2022a) or ``R2024a`` (from R2022b);
* the **licence version** is what a client checks out from a FlexLM licence
  server, printed by ``lmutil lmstat -a`` on every checkout line as ``(v51)``.

The bundled table (``versions.json``) covers R2006a onwards and records, for
each value, how well it is supported and where it comes from. Releases newer
than the table are computed from the current rules and marked
``"extrapolated"``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Tuple, Union

__all__ = [
    "Checkout",
    "Release",
    "data",
    "from_license",
    "from_matlab",
    "from_runtime",
    "lookup",
    "parse_checkout",
    "parse_lmstat",
    "release",
    "releases",
]
__version__ = "0.1.1"

#: Oldest licence version the +1 rule holds for (R2007a).
FIRST_LICENSE = 17

#: How many releases past the newest one in the table are computed from the rules
#: (10 = five years). Anything further is rejected rather than guessed: the rules are
#: only known to hold today, and "v910" is a Runtime folder, not a release in 2453.
MAX_RELEASES_AHEAD = 10

_NAME_RE = re.compile(r"^\s*R?(?P<year>\d{4})(?P<half>[ab])\s*$", re.IGNORECASE)
_LICENSE_RE = re.compile(r"^\s*v?(?P<major>\d+)(?:\.(?P<minor>\d+))?\s*$", re.IGNORECASE)
_DOTTED_RE = re.compile(r"^\s*(?P<version>\d+(?:\.\d+)+)(?:\s.*)?$")
_FOLDER_RE = re.compile(r"^\s*v(?P<digits>\d{2,4})\s*$", re.IGNORECASE)
_FEATURE_RE = re.compile(r"^Users of\s+(?P<feature>\S+?):", re.IGNORECASE)
_CHECKOUT_RE = re.compile(
    r"^\s+(?P<user>\S+)\s+(?P<host>\S+)\s+(?:(?P<display>.*?)\s+)?"
    r"\(v(?P<version>\d+)(?:\.\d+)?\)\s+"
    r"\((?P<server>[^/\s]+)/(?P<port>\d+)\s+(?P<handle>\d+)\)"
    r"(?:,\s+start\s+(?P<start>.+?))?"
    r"(?:,\s+PID:\s*(?P<pid>\d+))?\s*$"
)


@dataclass(frozen=True)
class Release:
    """One MATLAB release and its identifiers. Missing values are ``None``."""

    name: str
    """Release name, e.g. ``"R2024a"``."""
    matlab: Optional[str]
    """MATLAB version as ``version()`` reports it, major.minor only, e.g. ``"24.1"``."""
    runtime: Optional[str]
    """MATLAB Runtime version, e.g. ``"24.1"`` (``"9.0.1"`` for R2016a)."""
    license: Optional[int]
    """FlexLM licence version, e.g. ``51`` (shown by lmstat as ``(v51)``)."""
    evidence: Mapping[str, str] = field(default_factory=dict, compare=False, hash=False)
    """Per field: ``"observed"``, ``"documented"`` or ``"extrapolated"`` (see ``data()``)."""
    sources: Mapping[str, Tuple[str, ...]] = field(default_factory=dict, compare=False, hash=False)
    """Per field: keys into ``data()["sources"]``."""

    @property
    def year(self) -> int:
        return int(self.name[1:5])

    @property
    def half(self) -> str:
        return self.name[5]

    @property
    def runtime_folder(self) -> Optional[str]:
        """Folder the MATLAB Runtime installs under: ``"v910"`` up to R2022a, ``"R2022b"`` after."""
        if self.runtime is None:
            return None
        if (self.year, self.half) >= (2022, "b"):
            return self.name
        return "v" + self.runtime.replace(".", "")

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Checkout:
    """One checkout line from ``lmutil lmstat -a``."""

    user: str
    host: str
    display: Optional[str]
    version: int
    """Licence version the client checked out, e.g. ``51``."""
    server: str
    port: int
    handle: int
    start: Optional[str]
    pid: Optional[int]
    feature: Optional[str] = None
    """The ``Users of <feature>:`` section the line was in (only from :func:`parse_lmstat`)."""

    @property
    def release(self) -> Optional[Release]:
        """The client's MATLAB release, or ``None`` for licence versions before R2007a."""
        try:
            return from_license(self.version)
        except ValueError:
            return None


_DATA: Optional[dict] = None
_BY_NAME: Dict[str, Release] = {}


def data() -> dict:
    """The bundled table: description, rules, caveats, evidence levels, sources and releases."""
    global _DATA
    if _DATA is None:
        text = files(__package__).joinpath("versions.json").read_text(encoding="utf-8")
        _DATA = json.loads(text)
        for row in _DATA["releases"]:
            rel = Release(
                name=row["release"],
                matlab=row.get("matlab"),
                runtime=row.get("runtime"),
                license=row.get("license"),
                evidence=dict(row.get("evidence", {})),
                sources={k: tuple(v) for k, v in row.get("sources", {}).items()},
            )
            _BY_NAME[rel.name] = rel
    return _DATA


def releases() -> Tuple[Release, ...]:
    """All releases in the bundled table, oldest first."""
    data()
    return tuple(sorted(_BY_NAME.values(), key=lambda r: (r.year, r.half)))


def _newest() -> Release:
    return releases()[-1]


def _is_newer(year: int, half: str) -> bool:
    newest = _newest()
    return (year, half) > (newest.year, newest.half)


def _extrapolate(year: int, half: str) -> Release:
    """A release newer than the table, from the rules that hold since R2023b.

    Raises :class:`ValueError` beyond :data:`MAX_RELEASES_AHEAD` releases.
    """
    newest = _newest()
    ahead = 2 * (year - newest.year) + (half == "b") - (newest.half == "b")
    if ahead > MAX_RELEASES_AHEAD:
        raise ValueError(
            f"R{year}{half} is {ahead} releases after the newest known release ({newest.name}); "
            f"only {MAX_RELEASES_AHEAD} are extrapolated"
        )
    ver = f"{year % 100}.{1 if half == 'a' else 2}"
    lic = 2 * (year - 2008) + 19 + (half == "b")
    return Release(
        name=f"R{year}{half}", matlab=ver, runtime=ver, license=lic,
        evidence={"matlab": "extrapolated", "runtime": "extrapolated", "license": "extrapolated"},
    )


def release(name: str) -> Release:
    """Release by name: ``"R2024a"``, ``"2024a"`` or ``"r2024A"``."""
    m = _NAME_RE.match(str(name))
    if not m:
        raise ValueError(f"not a release name like 'R2024a': {name!r}")
    year, half = int(m.group("year")), m.group("half").lower()
    data()
    found = _BY_NAME.get(f"R{year}{half}")
    if found:
        return found
    if _is_newer(year, half):
        return _extrapolate(year, half)
    raise ValueError(f"R{year}{half} is not covered (the table starts at {releases()[0].name})")


def from_license(ver: Union[int, str]) -> Release:
    """Release whose clients check out this licence version: ``51``, ``"v51"``, ``"v51.0"``.

    MathWorks licence versions are whole numbers, so ``"v51.0"`` is accepted but
    ``"24.1"`` is not a licence version.
    """
    if isinstance(ver, bool):
        raise TypeError("licence version must be an int or str")
    if isinstance(ver, str):
        m = _LICENSE_RE.match(ver)
        if not m or int(m.group("minor") or 0) != 0:
            raise ValueError(f"not a licence version: {ver!r}")
        ver = int(m.group("major"))
    if ver < FIRST_LICENSE:
        raise ValueError(f"licence version {ver} predates R2007a, where the numbering differs")
    for rel in releases():
        if rel.license == ver:
            return rel
    steps = ver - 19
    return _extrapolate(2008 + steps // 2, "ab"[steps % 2])


def _two_part(version: str) -> str:
    return ".".join(version.split(".")[:2])


def from_matlab(ver: str) -> Release:
    """Release for a MATLAB version: ``"24.1"``, ``"9.10"`` or a full ``version()`` string
    such as ``"9.10.0.1739362 (R2021a)"``."""
    m = _DOTTED_RE.match(str(ver))
    if not m:
        raise ValueError(f"not a MATLAB version like '24.1': {ver!r}")
    wanted = _two_part(m.group("version"))
    for rel in releases():
        if rel.matlab == wanted:
            return rel
    major, minor = (int(x) for x in wanted.split("."))
    if major >= 23 and minor in (1, 2) and _is_newer(2000 + major, "ab"[minor - 1]):
        return _extrapolate(2000 + major, "ab"[minor - 1])
    raise ValueError(f"unknown MATLAB version: {ver!r}")


def from_runtime(ver: str) -> Release:
    """Release for a MATLAB Runtime version or install folder:
    ``"9.14"``, ``"9.0.1"``, ``"v914"``, ``"v901"`` or ``"R2023b"``."""
    text = str(ver).strip()
    if _NAME_RE.match(text):
        rel = release(text)
        if rel.runtime is None:
            raise ValueError(f"no MATLAB Runtime version is known for {rel.name}")
        return rel
    if _FOLDER_RE.match(text):
        for rel in releases():
            if rel.runtime_folder and rel.runtime_folder.lower() == text.lower():
                return rel
        raise ValueError(f"unknown MATLAB Runtime folder: {ver!r}")
    m = _DOTTED_RE.match(text)
    if not m:
        raise ValueError(f"not a MATLAB Runtime version like '9.14' or 'v914': {ver!r}")
    full = m.group("version")
    parts = full.split(".")
    for length in range(len(parts), 1, -1):
        candidate = ".".join(parts[:length])
        for rel in releases():
            if rel.runtime == candidate:
                return rel
    major, minor = (int(x) for x in _two_part(full).split("."))
    if major >= 23 and minor in (1, 2) and _is_newer(2000 + major, "ab"[minor - 1]):
        return _extrapolate(2000 + major, "ab"[minor - 1])
    raise ValueError(f"unknown MATLAB Runtime version: {ver!r}")


def lookup(term: Union[int, str]) -> List[Tuple[str, Release]]:
    """Every reading of ``term``, as ``(kind, release)`` pairs.

    ``kind`` is ``"name"``, ``"matlab"``, ``"runtime"`` or ``"license"``. Some
    terms have more than one reading: ``"9.0"`` is MATLAB R2016a but MATLAB
    Runtime R2015b. Licence readings are included wherever valid, including
    dotted versions and Runtime folder spellings. An empty list means nothing
    matched.
    """
    text = str(term).strip()
    if _NAME_RE.match(text):
        try:
            return [("name", release(text))]
        except ValueError:
            return []
    if "." in text and not text.lower().startswith("v"):
        readings = (("matlab", from_matlab), ("runtime", from_runtime), ("license", from_license))
    elif _FOLDER_RE.match(text) and len(text.strip()) >= 4:
        # Keep Runtime folders first while also accepting their licence reading.
        readings = (("runtime", from_runtime), ("license", from_license))
    else:
        # "51", "v51", "v51.0" are licence versions; "v91" could also be a Runtime folder
        readings = (("license", from_license), ("runtime", from_runtime))
    found = []
    for kind, fn in readings:
        try:
            found.append((kind, fn(text)))
        except ValueError:
            pass
    return found


def parse_checkout(line: str, feature: Optional[str] = None) -> Optional[Checkout]:
    """Parse one lmstat checkout line; ``None`` if it is not one."""
    m = _CHECKOUT_RE.match(line.rstrip("\r\n"))
    if not m:
        return None
    pid = m.group("pid")
    return Checkout(
        user=m.group("user"),
        host=m.group("host"),
        display=m.group("display") or None,
        version=int(m.group("version")),
        server=m.group("server"),
        port=int(m.group("port")),
        handle=int(m.group("handle")),
        start=m.group("start"),
        pid=int(pid) if pid else None,
        feature=feature,
    )


def parse_lmstat(text: Union[str, Iterable[str]]) -> Iterator[Checkout]:
    """Yield every checkout in ``lmutil lmstat -a`` output, tagged with its feature."""
    lines = text.splitlines() if isinstance(text, str) else text
    feature = None
    for line in lines:
        m = _FEATURE_RE.match(line)
        if m:
            feature = m.group("feature")
            continue
        checkout = parse_checkout(line, feature)
        if checkout is not None:
            yield checkout
