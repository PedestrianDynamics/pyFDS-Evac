"""Generate the parameter sidebar form from run.py's argparse flags.

All argparse introspection, grouping and form_to_opts logic is unchanged.
HTML rendering uses plain FastHTML + inline styles (no MonsterUI).
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List

from fasthtml.common import (
    Button,
    Div,
    Form,
    Input,
    Label,
    NotStr,
    Optgroup,
    Option,
    Select,
)

try:
    from fasthtml.common import to_xml
except ImportError:
    try:
        from fasthtml.xtend import to_xml
    except ImportError:
        from fasthtml.core import to_xml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSET_ROOT = _REPO_ROOT / "assets"
# Scenarios uploaded through the GUI. Gitignored, and kept out of assets/ so a
# user's drop can never shadow or overwrite a bundled scenario.
_UPLOAD_ROOT = _REPO_ROOT / "uploads"
# Picker values for uploads carry this prefix; bundled scenarios carry none.
UPLOAD_PREFIX = "uploads/"

_INPUT = (
    "background:var(--surface-input);border:1px solid var(--hairline);"
    "border-radius:9px;padding:10px 12px;color:var(--ink);"
    "font-family:'JetBrains Mono',monospace;font-size:13px;"
    "outline:none;width:100%;box-sizing:border-box"
)
_LABEL = (
    "display:block;font-family:'Space Grotesk',sans-serif;"
    "font-size:10.5px;font-weight:500;letter-spacing:.07em;"
    "text-transform:uppercase;color:var(--ink-faint);margin-bottom:6px"
)
_FIELD = "display:flex;flex-direction:column;gap:6px"
_GROTESK = "font-family:'Space Grotesk',sans-serif"
_MONO = "font-family:'JetBrains Mono',monospace"

_GROUP_ACCENT = ["#F4C430", "#FF8A3D", "#E01E37", "#C81D4E", "#F4C430", "#FFB020"]

FIELD_GROUPS: List[tuple] = [
    ("Core", ["scenario", "seed"]),
    (
        "Smoke",
        [
            "fds_dir",
            "constant_extinction",
            "smoke_update_interval",
            "smoke_slice_height",
        ],
    ),
    (
        "FED & Tenability",
        [
            "disable_tenability",
            "incapacitation_mode",
            "susceptibility_sigma",
            "fic_alpha",
            "fic_min_factor",
            "fed_threshold",
            "heat_incapacitation_mode",
            "heat_susceptibility_sigma",
            "heat_fed_threshold",
        ],
    ),
    ("Rerouting", ["enable_rerouting", "reroute_interval"]),
    ("Visibility", ["vis_cache"]),
    (
        "Output files",
        [
            "output_sqlite",
            "output_smoke_history",
            "output_fed_history",
            "output_route_history",
            "output_route_cost_history",
            "export_app_bundle",
        ],
    ),
]

_HIDDEN = {"help", "print_summary", "export_only", "inspect_fds", "cleanup"}


def _load_parser() -> argparse.ArgumentParser:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    import run

    return run._build_parser()


def _is_bool(action: argparse.Action) -> bool:
    # store_true flags, plus --x/--no-x BooleanOptionalAction toggles.
    if isinstance(action, getattr(argparse, "BooleanOptionalAction", ())):
        return True
    return action.nargs == 0 and action.const is True


def _options_under(root: Path, prefix: str = "") -> List[tuple]:
    """(label, value) pairs for every scenario directory under *root*.

    The rule here is deliberately the same one ``load_scenario`` applies to a
    directory: it needs one JSON and one WKT, preferring ``config.json`` and
    ``geometry.wkt`` but falling back to the alphabetically first of each.
    The picker used to demand a literal ``config.json``, which made a
    directory the CLI loads happily invisible in the GUI -- ``assets/Haspel``
    (``BUW_Geometrie_EG.wkt`` + ``inifile_template.json``) was exactly that.

    Each *other* *.json beside the primary one becomes an extra option, since
    ``load_scenario`` also accepts a bare .json path and reads the geometry
    from a sibling .wkt.
    """
    if not root.is_dir():
        return []
    options: List[tuple] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        jsons = sorted(p.glob("*.json"))
        if not jsons or not any(p.glob("*.wkt")):
            continue
        # Mirror load_scenario's preference so the bare-directory option and
        # the loader agree on which JSON is the primary one.
        preferred = p / "config.json"
        primary = preferred if preferred.exists() else jsons[0]
        options.append((p.name, f"{prefix}{p.name}"))
        for json_file in jsons:
            if json_file == primary:
                continue
            options.append(
                (
                    f"{p.name} / {json_file.name}",
                    f"{prefix}{p.name}/{json_file.name}",
                )
            )
    return options


def _scenario_options() -> List[tuple]:
    return _options_under(_ASSET_ROOT)


def _upload_options() -> List[tuple]:
    return _options_under(_UPLOAD_ROOT, UPLOAD_PREFIX)


def scenario_path(name: str) -> Path:
    """Resolve a scenario picker value to a real path on disk.

    Values are ``<dir>`` or ``<dir>/<file>.json``, optionally carrying the
    ``uploads/`` prefix. The resolved path is required to stay inside its root
    so a crafted value ("../../etc", an absolute path, a symlink out) cannot
    reach arbitrary files -- the value reaches us straight from a form field,
    not only from the <select> we rendered.
    """
    raw = (name or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("No scenario selected.")
    if raw.startswith(UPLOAD_PREFIX):
        root, rel = _UPLOAD_ROOT, raw[len(UPLOAD_PREFIX) :]
    else:
        root, rel = _ASSET_ROOT, raw
    if not rel or rel.startswith("/"):
        raise ValueError(f"Invalid scenario: {name!r}")

    resolved = (root / rel).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Scenario is outside {root.name}/: {name!r}")
    if not resolved.exists():
        raise ValueError(f"Scenario not found: {name!r}")
    return resolved


def upload_block() -> NotStr:
    """Drop zone for a user's own scenario, shown under the scenario picker.

    It lives *inside* the run form so there is one place to choose what runs:
    the picker lists bundled and uploaded scenarios together, and this adds to
    that list. HTML forbids nested forms, so rather than a <form> of its own the
    upload is posted by htmx straight off the button, pulling in the two inputs
    by hx-include. The run form drops them again via hx-params.
    """
    return NotStr(
        "<div class='upload-block'>"
        "<div class='upload-title'>Or upload your own</div>"
        "<input type='text' id='upload-name' name='upload_name' "
        "placeholder='Name (optional)' autocomplete='off' spellcheck='false' "
        "class='upload-name'>"
        "<label id='upload-drop' class='upload-drop'>"
        "<input type='file' name='files' multiple accept='.json,.wkt,.zip' hidden>"
        "<span class='upload-drop-title'>Drop files or click to browse</span>"
        "<span class='upload-drop-sub'>config JSON + geometry WKT, or a .zip bundle</span>"
        "<span id='upload-picked' class='upload-picked'></span>"
        "</label>"
        "<button type='button' class='upload-btn' "
        "hx-post='/upload-scenario' hx-encoding='multipart/form-data' "
        "hx-include=\"#upload-drop input, #upload-name, [name='scenario']\" "
        # hx-params is inherited from the enclosing run form, whose filter drops
        # exactly the two fields this request needs. Opt back in to all of them.
        "hx-params='*' "
        "hx-target='#scenario-block' hx-swap='outerHTML' "
        "hx-indicator='#upload-busy'>"
        "<span id='upload-busy' class='upload-busy'>…</span>Add to list</button>"
        "<span class='upload-hint'>Geometry and configuration only. Fire data is "
        "supplied separately through the FDS dir field under Smoke.</span>"
        "</div>"
    )


def _browse_button(target_id: str, mode: str) -> Any:
    return Button(
        "Browse…",
        type="button",
        hx_get=f"/browse-dir?mode={mode}&field={target_id}",
        hx_target="#dir-modal",
        hx_swap="innerHTML",
        style=(
            "flex:none;background:var(--surface-raised);border:1px solid var(--hairline-strong);"
            "border-radius:9px;padding:0 12px;height:42px;"
            f"{_GROTESK};font-size:12px;color:var(--ink-dim);cursor:pointer"
        ),
    )


# Curated, friendly explanations shown in the ? badge next to each field.
# Preferred over argparse's terse help text; keyed by the field's dest.
_HELP_TEXT: Dict[str, str] = {
    "scenario": "Which building + agent setup to run. Each option under assets/ pairs "
    "a floor plan (geometry) with an exits/agents config.",
    "seed": "Random seed. The same seed reproduces the exact same run; change it to "
    "get a different random spawn layout and variation.",
    "fds_dir": "Folder of precomputed FDS fire results. Supplies the smoke and "
    "toxic-gas fields agents react to. Leave blank to run with no fire.",
    "constant_extinction": "Skip FDS and apply one uniform smoke density K (1/m) everywhere — a "
    "quick way to test smoke slowdown without a full fire run.",
    "smoke_update_interval": "How often (sim seconds) the smoke each agent feels is refreshed. "
    "Smaller is smoother but costs more compute.",
    "smoke_slice_height": "Height (m) of the horizontal FDS slice sampled for smoke — roughly "
    "head height of a standing person.",
    "disable_tenability": "Turn off smoke's effect on people: no slowing from irritants and no "
    "collapse from toxic dose. Agents just walk at normal speed.",
    "incapacitation_mode": "Probabilistic: each agent draws its own tolerance from a population "
    "curve (some collapse early, some late). Deterministic: every agent "
    "shares the same threshold.",
    "susceptibility_sigma": "Spread of how differently people tolerate toxic smoke. Higher = more "
    "variation between agents in when they're overcome.",
    "fic_alpha": "How strongly irritant gases slow an agent. Higher = agents slow down "
    "more in irritating smoke.",
    "fic_min_factor": "Floor on irritant slowdown — an agent never drops below this fraction "
    "of its speed from irritants alone.",
    "fed_threshold": "Toxic dose (FED) at which a typical person is incapacitated. 1.0 is the "
    "standard 'untenable' dose (ISO 13571). Lower = agents succumb sooner.",
    "heat_incapacitation_mode": "Same idea as toxic-dose mode, but for heat: probabilistic draws a "
    "per-agent tolerance, deterministic gives everyone the same one. "
    "Independent of the toxic-gas track.",
    "heat_susceptibility_sigma": "Spread of how differently people tolerate heat exposure. Reuses the "
    "toxic-gas default as a starting assumption — there's no published "
    "population data for heat specifically.",
    "heat_fed_threshold": "Heat dose (SFPE Handbook Eq. 63.44) at which a typical person is thermally "
    "incapacitated — tracked separately from toxic gas dose; 1.0 is the "
    "standard tenability limit.",
    "enable_rerouting": "Let agents rethink their route mid-evacuation as smoke and crowding "
    "change, instead of blindly following their first assigned route.",
    "reroute_interval": "How often (sim seconds) each agent rethinks its route. 1 = very "
    "responsive; larger values make agents commit longer before "
    "reconsidering.",
    "vis_cache": "Precomputed sign-visibility map (.npz). Lets agents lose sight of exit "
    "signs through smoke and walls. Needs an FDS dir + rerouting enabled.",
    "output_base": "Folder the run writes into. Leave it blank to use the derived path "
    "shown greyed out, which keeps each scenario / mode / seed in its own "
    "folder. Type a path to override it and everything below goes there.",
    "results_only": "Finishes sooner by skipping the trajectory viewer and plots. "
    "Writes every output file to results/: the SQLite, the CSVs, and a "
    "config + geometry snapshot. Same as 'uv run run.py'.",
}


def _help_text(dest: str, action: argparse.Action | None = None) -> str:
    """Curated (or argparse) help string for *dest*, or '' when there's none."""
    text = (_HELP_TEXT.get(dest) or (action.help if action else "") or "").strip()
    if not text or text == "show this help message and exit":
        return ""
    return text


def _label_line(text: str, has_badge: bool) -> str:
    """Inline label-text + optional ? badge. The badge toggles 'open' on the
    enclosing .lblwrap, which reveals the in-flow help block below."""
    import html as _html

    badge = (
        (
            '<span class="help-badge" '
            "onclick=\"this.closest('.lblwrap').classList.toggle('open')\">?</span>"
        )
        if has_badge
        else ""
    )
    return f'<span class="lbl-line">{_html.escape(text)}{badge}</span>'


def _lbl(text: str, dest: str, action: argparse.Action | None = None) -> Any:
    """A field label with a pressable ? that expands an in-flow help block.

    The help block sits in normal document flow (not absolutely positioned),
    so it's bounded by the field width and can never overflow / be clipped by
    the sidebar's scroll box.
    """
    import html as _html

    tip = _help_text(dest, action)
    if not tip:
        return Label(text, style=_LABEL)
    return Div(
        Label(NotStr(_label_line(text, True)), style=_LABEL),
        NotStr(f'<div class="badge-tip">{_html.escape(tip)}</div>'),
        cls="lblwrap",
    )


def _switch(
    dest: str, label: str, checked: bool = False, action: argparse.Action | None = None
) -> Any:
    _chk = "checked " if checked else ""
    _track_bg = "#F4C430" if checked else "var(--surface-input)"
    _knob_pos = "19px" if checked else "2px"
    import html as _html

    _tip = _help_text(dest, action)
    _label_node = Label(
        NotStr(_label_line(label, bool(_tip))),
        style=f"{_GROTESK};font-size:12px;font-weight:500;color:var(--ink)",
    )
    _row = Div(
        _label_node,
        NotStr(
            f'<label style="position:relative;display:inline-block;width:40px;height:23px;cursor:pointer">'
            f'<input type="checkbox" id="{dest}" name="{dest}" value="on" {_chk}'
            f'style="opacity:0;width:0;height:0;position:absolute">'
            f'<span onclick="event.preventDefault();var cb=this.previousElementSibling;cb.checked=!cb.checked;'
            f"this.style.background=cb.checked?'#F4C430':'var(--surface-input)';"
            f"this.querySelector('span').style.left=cb.checked?'19px':'2px';\" "
            f'style="position:absolute;inset:0;border-radius:99px;'
            f'background:{_track_bg};border:1px solid var(--hairline-strong);transition:background .18s">'
            f'<span style="position:absolute;top:2px;left:{_knob_pos};width:17px;height:17px;'
            f'border-radius:99px;background:var(--ink-dim);transition:left .18s;display:block"></span>'
            f"</span></label>"
        ),
        style="display:flex;align-items:center;justify-content:space-between;gap:10px",
    )
    if not _tip:
        return _row
    return Div(
        _row,
        NotStr(f'<div class="badge-tip">{_html.escape(_tip)}</div>'),
        cls="lblwrap",
    )


def _incap_toggle() -> Any:
    return Div(
        _lbl("Incapacitation Mode", "incapacitation_mode"),
        Div(
            NotStr(
                '<button type="button" class="mode-btn active" id="btn-prob"'
                " onclick=\"setTenabilityMode('probabilistic')\">Probabilistic</button>"
                '<button type="button" class="mode-btn" id="btn-det"'
                " onclick=\"setTenabilityMode('deterministic')\">Deterministic</button>"
            ),
            cls="mode-toggle",
        ),
        Input(
            type="hidden",
            id="incapacitation_mode",
            name="incapacitation_mode",
            value="probabilistic",
        ),
        NotStr(
            '<div id="incap-dist" style="margin-top:10px;border-radius:9px;overflow:hidden;background:var(--surface-panel)">'
            '<canvas id="incap-canvas" style="width:100%;height:108px;display:block"></canvas>'
            "</div>"
        ),
        style=_FIELD,
    )


_SELECT = (
    "appearance:none;"
    'background:var(--surface-input) url("data:image/svg+xml;utf8,'
    "<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'>"
    "<path d='M2 4l4 4 4-4' stroke='%23837A74' stroke-width='1.5' fill='none'/>"
    '</svg>") no-repeat right 12px center;'
    "border:1px solid var(--hairline);border-radius:9px;"
    f"padding:10px 32px 10px 12px;color:var(--ink);{_GROTESK};font-size:13px;"
    "outline:none;width:100%"
)


def scenario_block(selected: str | None = None, note: Any = None) -> Any:
    """The scenario picker, as a self-contained swap target.

    Split out of ``_field`` so /upload-scenario can re-render it with the fresh
    upload preselected. Bundled and uploaded scenarios go in separate optgroups
    so it stays obvious which are yours.
    """
    bundled = _scenario_options()
    uploaded = _upload_options()
    vals = [v for _, v in bundled + uploaded]
    default = selected if selected in vals else (vals[0] if vals else "")

    def _opts(pairs):
        return [Option(ol, value=ov, selected=(ov == default)) for ol, ov in pairs]

    if uploaded:
        children = [
            Optgroup(*_opts(bundled), label="Bundled"),
            Optgroup(*_opts(uploaded), label="Uploaded"),
        ]
    else:
        children = _opts(bundled)

    return Div(
        _lbl("Scenario", "scenario"),
        Select(*children, name="scenario", id="scenario", style=_SELECT),
        *([note] if note is not None else []),
        id="scenario-block",
        style=_FIELD,
    )


def _field(action: argparse.Action) -> Any:
    dest = action.dest

    if dest == "scenario":
        return scenario_block()

    if dest == "seed":
        return Div(
            _lbl("Seed", "seed", action),
            Input(
                id=dest, name=dest, type="number", step="1", value="42", style=_INPUT
            ),
            style=_FIELD,
        )

    if dest == "fds_dir":
        return Div(
            _lbl("FDS dir", "fds_dir", action),
            Div(
                Input(
                    id=dest,
                    name=dest,
                    placeholder="results/demo/fds",
                    autocomplete="off",
                    spellcheck="false",
                    style=_INPUT + ";flex:1;min-width:0",
                ),
                _browse_button("fds_dir", "dir"),
                style="display:flex;gap:7px",
            ),
            style=_FIELD,
        )

    if dest == "vis_cache":
        return Div(
            _lbl("Vis cache", "vis_cache", action),
            Div(
                Input(
                    id=dest,
                    name=dest,
                    placeholder="results/demo/vis.npz",
                    style=_INPUT + ";flex:1;min-width:0",
                ),
                _browse_button("vis_cache", "file"),
                style="display:flex;gap:7px",
            ),
            style=_FIELD,
        )

    if dest == "incapacitation_mode":
        return _incap_toggle()

    if dest == "susceptibility_sigma":
        val = str(action.default if action.default is not None else 0.94)
        return Div(
            Div(
                _lbl("Susceptibility σ", "susceptibility_sigma", action),
                Input(
                    id=dest,
                    name=dest,
                    type="number",
                    step="any",
                    value=val,
                    style=_INPUT,
                ),
                style=_FIELD,
            ),
            id="sigma-row",
        )

    if _is_bool(action):
        # Initial toggle state follows the flag's own default, so an
        # on-by-default CLI flag (e.g. rerouting) renders checked.
        return _switch(
            dest,
            dest.replace("_", " ").capitalize(),
            checked=bool(action.default),
            action=action,
        )

    step = "1" if action.type is int else "any"
    value = "" if action.default is None else str(action.default)
    label = dest.replace("_", " ").capitalize()
    if action.type in (int, float):
        return Div(
            _lbl(label, dest, action),
            Input(
                id=dest, name=dest, type="number", step=step, value=value, style=_INPUT
            ),
            style=_FIELD,
        )
    return Div(
        _lbl(label, dest, action),
        Input(id=dest, name=dest, value=value, style=_INPUT),
        style=_FIELD,
    )


def _details_block(
    title: str, accent: str, fields: List[Any], open_: bool = False
) -> NotStr:
    body = to_xml(
        Div(
            *fields,
            style="display:flex;flex-direction:column;gap:13px;padding:14px 4px 4px",
        )
    )
    return NotStr(
        f"<details {'open' if open_ else ''}>"
        f'<summary style="display:flex;align-items:center;justify-content:space-between;'
        f"padding:11px 13px;background:var(--surface-accent);border:1px solid var(--hairline);"
        f'border-left:2px solid {accent};border-radius:11px;list-style:none;cursor:pointer">'
        f'<span style="{_GROTESK};font-weight:600;font-size:12.5px;letter-spacing:.01em;color:var(--ink)">{title}</span>'
        f'<svg class="chevron" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="var(--ink-faint)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        f"</summary>" + body + "</details>"
    )


def _results_only_button() -> Any:
    """Secondary submit: same run, no viewer built afterwards.

    The ? badge has to sit *outside* the <button> -- inside it, clicking to
    read the help would submit the form and start a run. It reuses the same
    .lblwrap/.badge-tip mechanism as the field labels.
    """
    import html as _html

    return Div(
        Div(
            Button(
                NotStr(
                    '<span class="run-btn-icon">↓</span>'
                    '<span class="run-btn-label">Results only</span>'
                ),
                id="results-btn",
                type="submit",
                name="results_only",
                value="1",
                cls="run-btn results-btn",
                style=(
                    "display:flex;align-items:center;justify-content:center;gap:6px;"
                    "flex:1;padding:11px;border-radius:12px;cursor:pointer;"
                    f"{_GROTESK};font-size:13.5px;font-weight:600;"
                    "background:transparent;color:#F4C430;"
                    "border:1px solid rgba(244,196,48,.45)"
                ),
            ),
            NotStr(
                '<span class="help-badge" style="flex:none;align-self:center" '
                "onclick=\"this.closest('.lblwrap').classList.toggle('open')\">?</span>"
            ),
            style="display:flex;align-items:stretch;gap:8px",
        ),
        NotStr(
            f'<div class="badge-tip">{_html.escape(_HELP_TEXT["results_only"])}</div>'
        ),
        cls="lblwrap",
    )


# Filename suffixes appended to the run name, in sidebar display order. The
# preview lines are re-rendered client-side from the selected scenario, so the
# names here must stay in step with _OUTPUT_DEFAULTS in form_to_opts.
ARTIFACT_SUFFIXES = (
    ".sqlite",
    "_smoke_history.csv",
    "_fed_history.csv",
    "_route_history.csv",
    "_route_cost_history.csv",
)

_DOT = (
    '<span style="width:4px;height:4px;border-radius:99px;'
    'background:#FF6A1A;flex:none;display:inline-block;margin-right:8px"></span>'
)
_PREVIEW_ROW = (
    f"display:flex;align-items:center;{_MONO};font-size:10.5px;color:var(--ink-dim)"
)


def _output_files_section() -> NotStr:
    body = to_xml(
        Div(
            Div(
                _lbl("Output folder", "output_base"),
                Input(
                    id="output_base",
                    name="output_base",
                    autocomplete="off",
                    spellcheck="false",
                    style=_INPUT,
                ),
                style=_FIELD,
            ),
            Div(
                Div(
                    "6 artifacts",
                    id="artifact-heading",
                    style=f"{_GROTESK};font-size:9px;font-weight:600;letter-spacing:.07em;"
                    f"text-transform:uppercase;color:var(--ink-faint);margin-bottom:6px",
                ),
                *[
                    Input(id=k, name=k, type="hidden")
                    for k in (
                        "output_sqlite",
                        "output_smoke_history",
                        "output_fed_history",
                        "output_route_history",
                        "output_route_cost_history",
                        "export_app_bundle",
                    )
                ],
                # data-suffix lets the autofill script rewrite these to the real
                # run name; the <run> text is what shows if the script is dead.
                *[
                    Div(
                        NotStr(_DOT),
                        NotStr(
                            f'<span class="artifact-preview" data-suffix="{suffix}">'
                            f"&lt;run&gt;{suffix}</span>"
                        ),
                        style=_PREVIEW_ROW,
                    )
                    for suffix in ARTIFACT_SUFFIXES
                ],
                Div(
                    NotStr(_DOT),
                    "bundle/{config.json,geometry.wkt}",
                    style=_PREVIEW_ROW,
                ),
                style=(
                    "background:var(--surface-accent);border:1px solid var(--hairline);"
                    "border-radius:10px;padding:11px 12px;display:flex;flex-direction:column;gap:5px"
                ),
            ),
            style="display:flex;flex-direction:column;gap:11px;padding:14px 4px 4px",
        )
    )
    return NotStr(
        "<details>"
        f'<summary style="display:flex;align-items:center;justify-content:space-between;'
        f"padding:11px 13px;background:var(--surface-accent);border:1px solid var(--hairline);"
        f'border-left:2px solid #FFB020;border-radius:11px;list-style:none;cursor:pointer">'
        f'<span style="{_GROTESK};font-weight:600;font-size:12.5px;letter-spacing:.01em;color:var(--ink)">Output files</span>'
        f'<svg class="chevron" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 4l4 4 4-4" stroke="var(--ink-faint)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        "</summary>" + body + "</details>"
    )


def build_form(post_url: str) -> Any:
    parser = _load_parser()
    by_dest = {
        a.dest: a for a in parser._actions if a.dest not in _HIDDEN and a.option_strings
    }
    grouped: set = set()
    sections: List[Any] = []

    for (title, dests), accent in zip(FIELD_GROUPS, _GROUP_ACCENT):
        if title == "Output files":
            sections.append(_output_files_section())
            grouped.update(dests)
            continue
        fields = [_field(by_dest[d]) for d in dests if d in by_dest]
        if not fields:
            continue
        # Uploading is a way of adding to the scenario picker, so it belongs
        # beside it rather than in a section of its own.
        if title == "Core":
            fields.append(upload_block())
        grouped.update(dests)
        open_ = title in ("Core", "Smoke", "FED & Tenability")
        sections.append(_details_block(title, accent, fields, open_))

    other = [_field(a) for d, a in by_dest.items() if d not in grouped]
    if other:
        sections.append(_details_block("Other", "var(--ink-faint)", other, False))

    return Form(
        Div(
            *sections,
            style="display:flex;flex-direction:column;gap:9px;"
            "max-height:calc(100vh - 230px);overflow:auto;margin:-4px;padding:4px",
        ),
        Button(
            NotStr(
                '<span class="run-btn-icon">▶</span>'
                '<span class="run-btn-label">Run scenario</span>'
            ),
            id="run-btn",
            type="submit",
            cls="run-btn",
            style=(
                "display:flex;align-items:center;justify-content:center;gap:6px;"
                "width:100%;padding:13px;border-radius:12px;border:none;cursor:pointer;"
                f"{_GROTESK};font-size:14.5px;font-weight:600;"
                "background:linear-gradient(180deg,#FFC24D,#E8590C);color:var(--on-heat);"
                "box-shadow:0 6px 20px rgba(232,89,12,.28)"
            ),
        ),
        _results_only_button(),
        hx_post=post_url,
        hx_target="#run-panel",
        hx_swap="innerHTML show:top",
        # The upload inputs sit inside this form for layout only. Exclude them
        # so a staged file is not serialised into the urlencoded run request.
        hx_params="not files,upload_name",
        style="display:flex;flex-direction:column;gap:14px",
    )


def run_name(scenario: Any) -> str:
    """Filename stem for a scenario's artifacts.

    ``clean()`` in the sidebar's autofill script mirrors this; the two must
    agree or the hidden fields and this server-side fallback would disagree on
    where a run writes.
    """
    name = str(scenario or "")
    return name.replace(".json", "").replace("/", "_") if name else "run"


def default_output_base(scenario: Any, mode: Any, seed: Any) -> str:
    """Derived output folder: one per scenario / incapacitation mode / seed."""
    return (
        f"results/{run_name(scenario)}/{mode or 'probabilistic'}/"
        f"seed{seed if seed is not None else 'default'}"
    )


def form_to_opts(form: Dict[str, Any]) -> Namespace:
    parser = _load_parser()
    opts: Dict[str, Any] = {}
    for action in parser._actions:
        dest = action.dest
        if dest == "help":
            continue
        if _is_bool(action):
            raw = form.get(dest)
            opts[dest] = (
                str(raw).lower() in ("on", "true", "1", "yes") if raw else False
            )
            continue
        raw = form.get(dest)
        if raw is None or str(raw).strip() == "":
            opts[dest] = action.default
            continue
        opts[dest] = action.type(raw) if action.type else str(raw)
    opts["collect_route_cost_history"] = True

    # Ensure output paths are always populated: the JS autofill may not have run
    # before submission, so derive them server-side too. The typed "Output
    # folder" wins when present -- it used to be read by nobody, so a path typed
    # there was silently discarded and the run went to the derived path anyway.
    sc = run_name(opts.get("scenario"))
    mode = str(opts.get("incapacitation_mode") or "probabilistic")
    base = (
        str(form.get("output_base") or "").strip().replace("\\", "/").rstrip("/")
    ) or (default_output_base(opts.get("scenario"), mode, opts.get("seed")))
    _OUTPUT_DEFAULTS = {
        "output_sqlite": f"{base}/{sc}.sqlite",
        "output_smoke_history": f"{base}/{sc}_smoke_history.csv",
        "output_fed_history": f"{base}/{sc}_fed_history.csv",
        "output_route_history": f"{base}/{sc}_route_history.csv",
        "output_route_cost_history": f"{base}/{sc}_route_cost_history.csv",
        "export_app_bundle": f"{base}/bundle",
    }
    # --export-app-bundle takes a *directory*, but the sidebar used to render it
    # as a checkbox; the posted "on" was passed straight through as a path, so
    # every GUI run dumped its bundle into a literal ./on/ folder. Treat the
    # checkbox-era truthy strings as "just use the default".
    if str(opts.get("export_app_bundle") or "").strip().lower() in (
        "on",
        "true",
        "1",
        "yes",
    ):
        opts["export_app_bundle"] = ""
    for k, v in _OUTPUT_DEFAULTS.items():
        if not opts.get(k):
            opts[k] = v

    return Namespace(**opts)
