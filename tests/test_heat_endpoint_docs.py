"""Docs checks for the heat dose's endpoint and flux type (#218).

Three things the heat pages must state:

- which kind of flux each formula takes: the radiant tolerance data
  (Eq. 63.43) are incident flux, the total-flux form (Eq. 63.49) is a net
  exchange with the skin, and the convective laws take air temperature, no
  flux at all (SFPE Handbook 5th ed., Ch. 63, pp. 2382-2384);
- that heat FED = 1 and gas FED = 1 are different endpoints although both set
  the same ``incapacitated`` flag and ``incapacitation_cause`` column;
- code citations by file and name, not line number: every cited name must
  be defined in the cited file (checked with ``ast``), across the site and
  docs pages except the historical docs/archive and
  docs/gate-model-review-notes.md.
"""

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODELS_FED = ROOT / "site" / "content" / "models" / "fed.md"
MODELS_HEAT = ROOT / "site" / "content" / "models" / "heat.md"
FUND_HEAT = ROOT / "site" / "content" / "fundamentals" / "heat.md"
LIMITATIONS = ROOT / "docs" / "limitations.md"


def _section(path: Path, heading: str) -> str:
    """Return the text under ``## heading`` up to the next ``## `` heading."""
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"{path.name}: no section '## {heading}'"
    return match.group(1)


def _paragraph_with(path: Path, needle: str) -> str:
    """Return the blank-line-delimited paragraph of ``path`` containing ``needle``."""
    for para in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        if needle in para:
            return para
    raise AssertionError(f"{path.name}: no paragraph containing {needle!r}")


# --- Code citations ----------------------------------------------------------
#
# Pages cite code by file and name, (`fed.py`, `TenabilityConfig`), not by
# line number, which goes stale with every edit above the cited line. Left
# out: docs/archive and docs/gate-model-review-notes.md, which record the
# code at an older commit.

_EXCLUDED = ("docs/archive/", "docs/gate-model-review-notes.md")
# Cited files outside the repository, by the package that ships them.
_EXTERNAL = {"FDSVisMap.py": "fdsvismap"}
_FILE_NAME = re.compile(r"\.(?:py|md|csv|fds|json|sqlite|png|txt|toml|yaml)$")
_NOT_SOURCE = {".git", ".venv", "venv", "site", "temp", "node_modules", "build"}

_FILE = r"`(?P<file>[\w./-]+\.py)`"
_SYMBOL = r"`[A-Za-z_][\w.]*(?:\(\))?`"
# (`file.py`, `symbol`, `symbol`): the names after the file.
_CITATION = re.compile(_FILE + r"(?P<symbols>(?:, " + _SYMBOL + r")+)")
# `symbol` (`file.py`): the name right before the file.
_NAMED_BEFORE = re.compile(r"`(?P<symbol>[A-Za-z_][\w.]*)(?:\(\))?` \(" + _FILE + r"\)")


def _pages() -> list[Path]:
    pages = [*(ROOT / "site" / "content").rglob("*.md"), *(ROOT / "docs").rglob("*.md")]
    return [
        p for p in pages if not p.relative_to(ROOT).as_posix().startswith(_EXCLUDED)
    ]


def _git_listed(root: Path) -> list[str] | None:
    """Python files git sees under *root*: tracked or untracked, not ignored.

    ``None`` when git is missing or *root* is not the top of a work tree
    (a tarball, an sdist, or a directory inside some other repository).
    """
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root.resolve():
        return None
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert listed.returncode == 0, f"git ls-files in {root}: {listed.stderr}"
    return [r for r in listed.stdout.split("\0") if r.endswith(".py")]


def _walked(root: Path) -> list[str]:
    """Python files under *root*, outside any nested repository or worktree."""
    nested = {g.parent for g in root.rglob(".git") if g.parent != root}
    return [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if not nested & set(p.parents)
    ]


@lru_cache(maxsize=1)
def _repo_sources() -> tuple[Path, ...]:
    """Python files of the checkout, without nested worktrees and clones.

    A git worktree inside the checkout (e.g. ``.worktrees/``) holds a second
    copy of every file, which would match a citation too. Git leaves those
    out; without git the tree walk skips every directory with a ``.git``.
    """
    rel = _git_listed(ROOT)
    if rel is None:
        rel = _walked(ROOT)
    return tuple(
        ROOT / r
        for r in sorted(set(rel))
        if not _NOT_SOURCE & set(Path(r).parts[:-1]) and (ROOT / r).is_file()
    )


def _resolve(cited: str) -> Path | None:
    """The file a citation names; ``None`` for an external one not installed."""
    if cited in _EXTERNAL:
        spec = importlib.util.find_spec(_EXTERNAL[cited])
        return None if spec is None else Path(spec.origin).parent / cited
    rel = [p.relative_to(ROOT).as_posix() for p in _repo_sources()]
    hits = [r for r in rel if r == cited or r.endswith("/" + cited)]
    if len(hits) > 1:
        hits = [r for r in hits if r.startswith("pyfds_evac/")] or hits
    assert len(hits) == 1, f"`{cited}` matches {len(hits)} files: {hits}"
    return ROOT / hits[0]


@lru_cache(maxsize=None)
def _defined_names(path: Path) -> frozenset[str]:
    """Qualified names defined in *path*: defs, classes, methods, and
    module-, class- and ``self.``-level assignment targets."""
    names: set[str] = set()

    def visit(node, prefix: str, cls: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                names.add(name)
                inner_cls = name if isinstance(child, ast.ClassDef) else cls
                visit(child, name + ".", inner_cls)
                continue
            targets = []
            if isinstance(child, ast.Assign):
                targets = child.targets
            elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
                targets = [child.target]
            for target in targets:
                if isinstance(target, ast.Name) and not prefix.endswith(")."):
                    names.add(prefix + target.id)
                is_self = (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                )
                if is_self and cls is not None:
                    names.add(f"{cls}.{target.attr}")
            visit(child, prefix, cls)

    visit(ast.parse(path.read_text(encoding="utf-8")), "", None)
    return frozenset(names)


def _is_defined(symbol: str, path: Path) -> bool:
    names = _defined_names(path)
    return symbol in names or any(n.endswith("." + symbol) for n in names)


def _citations() -> list:
    found = []
    for page in _pages():
        text = page.read_text(encoding="utf-8")
        rel = page.relative_to(ROOT).as_posix()
        for match in _CITATION.finditer(text):
            for symbol in re.findall(r"`([A-Za-z_][\w.]*)", match.group("symbols")):
                if _FILE_NAME.search(symbol):
                    continue  # a list of files, not a citation
                found.append(
                    pytest.param(match.group("file"), symbol, id=f"{rel}:{symbol}")
                )
        for match in _NAMED_BEFORE.finditer(text):
            symbol = match.group("symbol")
            found.append(
                pytest.param(match.group("file"), symbol, id=f"{rel}:{symbol}")
            )
    return found


@pytest.mark.parametrize(("cited_file", "symbol"), _citations())
def test_cited_symbol_exists_in_cited_file(cited_file, symbol):
    """Each (`file.py`, `name`) citation names code that is in that file."""
    path = _resolve(cited_file)
    if path is None:
        pytest.skip(f"{cited_file}: package not installed")
    assert _is_defined(symbol, path), f"`{symbol}` is not defined in {cited_file}"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_resolve_ignores_nested_git_worktree(tmp_path, monkeypatch):
    """A worktree inside the checkout does not add a second match (#304)."""
    _git("init", "-q", cwd=tmp_path)
    (tmp_path / "run.py").write_text("def _build_parser():\n    pass\n")
    _git("add", "run.py", cwd=tmp_path)
    _git("commit", "-q", "-m", "init", cwd=tmp_path)
    _git("worktree", "add", "-q", ".worktrees/feat", cwd=tmp_path)
    assert (tmp_path / ".worktrees" / "feat" / "run.py").is_file()
    (tmp_path / "untracked.py").write_text("x = 1\n")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    _repo_sources.cache_clear()
    try:
        assert _resolve("run.py") == tmp_path / "run.py"
        assert _resolve("untracked.py") == tmp_path / "untracked.py"
    finally:
        _repo_sources.cache_clear()


def test_resolve_without_git_skips_nested_repositories(tmp_path, monkeypatch):
    """Outside a git work tree (tarball, sdist) or without git, the tree walk
    resolves citations and still leaves out a nested checkout (#304)."""
    (tmp_path / "run.py").write_text("def _build_parser():\n    pass\n")
    nested = tmp_path / ".worktrees" / "feat"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: elsewhere\n")
    (nested / "run.py").write_text("def _build_parser():\n    pass\n")

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", no_git)
    _repo_sources.cache_clear()
    try:
        assert _resolve("run.py") == tmp_path / "run.py"
    finally:
        _repo_sources.cache_clear()
    monkeypatch.undo()
    # With git installed, a directory that is not the top of a work tree
    # (an unpacked tarball or sdist) also falls back to the walk.
    assert _git_listed(tmp_path) is None


def test_citation_check_finds_citations():
    """The citation pattern matches the pages, so the check above is not empty."""
    assert len(_citations()) > 50


def test_no_line_number_citation_remains():
    """No page cites code as ``file.py:N``, nor as a bare ``:N`` after a .py file."""
    after_py = re.compile(r"\.py`?[^)\n]*?`:\d+")
    for page in _pages():
        text = page.read_text(encoding="utf-8")
        rel = page.relative_to(ROOT).as_posix()
        assert not re.search(r"\.py:\d+", text), f"{rel}: .py:N citation"
        assert not after_py.search(text), f"{rel}: bare :N after a .py citation"


# --- Incident vs net flux --------------------------------------------------
#
# Each check asserts the relation, not a keyword: a sentence that names the
# right flux for the right equation. The negative cases are wrong wordings
# that must fail, so a sentence with the opposite meaning cannot pass.


def _sentences(text: str) -> list[str]:
    """Split on sentence ends; line breaks inside a sentence become spaces."""
    flat = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+(?=[A-Z`\\])", flat)


def _negated(sentence: str, word: str) -> bool:
    """True if ``word`` follows a negation in ``sentence``."""
    return bool(
        re.search(rf"\b(?:not|no|nor|neither)\b[^.;:]*\b{word}\b", sentence, re.I)
    )


def _radiant_limit_is_incident(text: str) -> bool:
    """A sentence ties the radiant limit or Eq. 63.43 to incident flux."""
    return any(
        re.search(r"\bradiant\b", s, re.I)
        and re.search(r"\bincident\b", s)
        and not re.search(r"\bnet\b", s)
        and not _negated(s, "incident")
        for s in _sentences(text)
    )


def _eq_63_49_is_net(text: str) -> bool:
    """A sentence names Eq. 63.49 and says it is written as a net exchange."""
    return any(
        "63.49" in s and re.search(r"\bnet exchange\b", s) and not _negated(s, "net")
        for s in _sentences(text)
    )


def _takes_temperature_not_flux(text: str) -> bool:
    """A sentence says no heat flux enters and only the temperature does."""
    return any(
        re.search(r"\bNo heat flux enters\b", s)
        and re.search(r"\b(?:air|gas) temperature only\b", s)
        for s in _sentences(text)
    )


def _fds_radiative_flux_is_net_with_emissivity(text: str) -> bool:
    """FDS RADIATIVE HEAT FLUX is net, εs(q_inc − σTs⁴), with the emissivity."""
    return any(
        "`RADIATIVE HEAT FLUX`" in s
        and re.search(r"\bnet\b", s)
        and re.search(r"\\varepsilon_s\s*\\left\(|\\varepsilon_s\s*\(", s)
        and re.search(r"\\sigma\s*T_s\^4", s)
        for s in _sentences(text)
    )


_FLUX_CHECKS = [
    (
        "radiant-incident",
        _radiant_limit_is_incident,
        lambda: _section(FUND_HEAT, "Radiant heat"),
        [
            "The tenability limit for net radiant flux on skin is 2.5 kW/m².",
            "The radiant limit is not incident flux.",
        ],
    ),
    (
        "eq-63-49-net",
        _eq_63_49_is_net,
        lambda: _section(FUND_HEAT, "Combining the two"),
        [
            "The total heat flux to the skin (Eq. 63.49) is the incident flux.",
            "Eq. 63.49 is not a net exchange with the skin surface.",
        ],
    ),
    (
        "convective-fundamentals",
        _takes_temperature_not_flux,
        lambda: _section(FUND_HEAT, "Convective heat"),
        [
            "These convective equations take incident heat flux.",
            "They take the heat flux only, not the air temperature.",
        ],
    ),
    (
        "convective-models",
        _takes_temperature_not_flux,
        lambda: _section(MODELS_HEAT, "What is computed"),
        [
            "The law takes the net heat flux at the agent.",
            "No gas temperature enters the law: it takes the heat flux only.",
        ],
    ),
    (
        "fds-radiative-net",
        _fds_radiative_flux_is_net_with_emissivity,
        lambda: FUND_HEAT.read_text(encoding="utf-8"),
        [
            "FDS's `RADIATIVE HEAT FLUX` output is net (absorbed incident flux "
            r"minus \(\sigma T_s^4\)).",
            "FDS's `RADIATIVE HEAT FLUX` output is the incident flux.",
        ],
    ),
]


@pytest.mark.parametrize(
    ("check", "text"),
    [pytest.param(c, t, id=i) for i, c, t, _ in _FLUX_CHECKS],
)
def test_docs_state_the_flux_each_formula_takes(check, text):
    """Eq. 63.43 incident, Eq. 63.49 net, Eqs. 63.44-63.47 temperature only."""
    assert check(text()), f"{check.__name__} not stated"


@pytest.mark.parametrize(
    ("check", "wrong"),
    [
        pytest.param(c, w, id=f"{i}-{n}")
        for i, c, _, wrongs in _FLUX_CHECKS
        for n, w in enumerate(wrongs)
    ],
)
def test_flux_checks_reject_wrong_wording(check, wrong):
    """Each flux check fails on a sentence with the wrong or opposite meaning."""
    assert not check(wrong), f"{check.__name__} accepted {wrong!r}"


# --- Endpoints of the two doses --------------------------------------------


def _heat_incapacitation_and_output() -> str:
    return _section(MODELS_HEAT, "Incapacitation") + _section(MODELS_HEAT, "Output")


def _says_endpoints_differ(text: str) -> bool:
    """Heat and gas FED = 1 are stated as different endpoints, never the same."""
    flat = re.sub(r"\s+", " ", text)
    differ = re.search(r"\bdo not share an endpoint\b|\bdifferent endpoints\b", flat)
    same = re.search(
        r"(?<!not )\bshare an endpoint\b|\bsame endpoint\b|\bone endpoint\b", flat
    )
    return bool(differ) and not same


def _says_cause_separates_the_endpoints(text: str) -> bool:
    """``incapacitated`` mixes the endpoints; ``incapacitation_cause`` tells them apart."""
    flat = re.sub(r"\s+", " ", text)
    return bool(
        re.search(r"`incapacitated` column is true whichever dose", flat)
        and re.search(r"filter on `incapacitation_cause`", flat)
    )


def _says_later_crossing_not_recorded(text: str) -> bool:
    """``gas+heat`` is the same update; a later crossing leaves the cause alone."""
    flat = re.sub(r"\s+", " ", text)
    return bool(
        re.search(r"`gas\+heat` means both doses crossed[^.]*same update", flat)
        and re.search(r"after the agent has stopped is not recorded", flat)
    )


_ENDPOINT_CHECKS = [
    (
        "models-heat-differ",
        _says_endpoints_differ,
        _heat_incapacitation_and_output,
        [
            "Heat and gas have the same endpoint.",
            "The two doses share an endpoint, FED = 1.",
            "Gas FED = 1 and heat FED = 1 are one endpoint.",
        ],
    ),
    (
        "limitations-differ",
        _says_endpoints_differ,
        lambda: _paragraph_with(LIMITATIONS, "either dose reaches its threshold"),
        ["An agent is incapacitated when either dose reaches the same endpoint."],
    ),
    (
        "models-heat-cause",
        _says_cause_separates_the_endpoints,
        lambda: _section(MODELS_HEAT, "Output"),
        [
            "The `incapacitated` column is true only for the gas dose.",
            "Filter on `incapacitated` to count them apart.",
        ],
    ),
    (
        "models-heat-later-crossing",
        _says_later_crossing_not_recorded,
        lambda: _section(MODELS_HEAT, "Output"),
        [
            "`gas+heat` means both doses crossed at some time during the run.",
            "`gas+heat` means both doses crossed their thresholds on the same "
            "update; a later crossing by the other dose is recorded as well.",
        ],
    ),
]


@pytest.mark.parametrize(
    ("check", "text"),
    [pytest.param(c, t, id=i) for i, c, t, _ in _ENDPOINT_CHECKS],
)
def test_docs_separate_heat_and_gas_endpoints(check, text):
    """Heat FED = 1 is not the gas dose's incapacitation endpoint."""
    assert check(text()), f"{check.__name__} not stated"


@pytest.mark.parametrize(
    ("check", "wrong"),
    [
        pytest.param(c, w, id=f"{i}-{n}")
        for i, c, _, wrongs in _ENDPOINT_CHECKS
        for n, w in enumerate(wrongs)
    ],
)
def test_endpoint_checks_reject_wrong_wording(check, wrong):
    """Each endpoint check fails on a sentence with the opposite meaning."""
    assert not check(wrong), f"{check.__name__} accepted {wrong!r}"


def test_models_heat_names_the_shared_output_columns():
    """Both doses report through ``incapacitation_cause``; pins the column name."""
    assert "`incapacitation_cause`" in _section(MODELS_HEAT, "Output")


def test_models_heat_does_not_call_the_implemented_law_fatal():
    """FED = 1 = fatal belongs to the unimplemented total-flux form (#223).

    The implemented law is Eq. 63.44, whose times lie near the tolerance
    curve, so the Incapacitation and Output sections must not call it fatal
    unless they also say that it is not.
    """
    text = _heat_incapacitation_and_output()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\bfatal\b", sentence, flags=re.IGNORECASE):
            assert re.search(
                r"\bnot\b|#223|total-flux|planned", sentence, flags=re.IGNORECASE
            ), f"implemented heat law called fatal: {sentence!r}"
