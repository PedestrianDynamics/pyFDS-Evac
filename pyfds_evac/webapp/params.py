"""Generate the parameter sidebar form from the CLI's argparse flags.

All argparse introspection, grouping and form_to_opts logic is unchanged.
HTML rendering uses plain FastHTML + inline styles (no MonsterUI).
"""

from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
from typing import Any

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
    Span,
)

try:
    from fasthtml.common import to_xml
except ImportError:
    try:
        from fasthtml.xtend import to_xml
    except ImportError:
        from fasthtml.core import to_xml

from pyfds_evac.cli import _build_parser
from pyfds_evac.config import frontend
from pyfds_evac.config.frontend import RESULTS_ENV as RESULTS_ENV
from pyfds_evac.config.frontend import output_paths, run_stamp, utc_now
from pyfds_evac.config.frontend import run_name as run_name
from pyfds_evac.config.parameters import (
    GUI_HIDDEN,
    GUI_SECTIONS,
    GUI_UNIT_LABELS,
    PARAMETERS,
    RUN_OPTIONS,
    default,
    parameter,
)
from pyfds_evac.core.manifest import find_project_root

# Root of the GUI's scenario, upload and result folders: the source checkout
# the package runs from, else the directory the server started in. An
# installed wheel thus never writes into site-packages, and finds scenarios
# in ./assets.
_WORK_ROOT = find_project_root() or Path.cwd()
_ASSET_ROOT = _WORK_ROOT / "assets"
# Scenarios uploaded through the GUI. Gitignored, and kept out of assets/ so a
# user's drop can never shadow or overwrite a bundled scenario.
_UPLOAD_ROOT = _WORK_ROOT / "uploads"
# Picker values for uploads carry this prefix; bundled scenarios carry none.
UPLOAD_PREFIX = "uploads/"
# Derived output folders go under RESULTS_ENV when set, else results/ under
# the root above (see _WORK_ROOT).

_INPUT = (
    "background:var(--surface-input);border:1px solid var(--hairline);"
    "border-radius:9px;padding:10px 12px;color:var(--ink);"
    "font-family:'JetBrains Mono',monospace;font-size:13px;"
    "width:100%;box-sizing:border-box"
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

# Sections, hidden flags, units and help come from the configuration model;
# the form keeps no option metadata of its own.
FIELD_GROUPS: list[tuple] = [(title, list(dests)) for title, dests in GUI_SECTIONS]

_HIDDEN = set(GUI_HIDDEN)


def _load_parser() -> argparse.ArgumentParser:
    return _build_parser()


def _is_bool(action: argparse.Action) -> bool:
    # store_true flags, plus --x/--no-x BooleanOptionalAction toggles.
    if isinstance(action, getattr(argparse, "BooleanOptionalAction", ())):
        return True
    return action.nargs == 0 and action.const is True


def _options_under(root: Path, prefix: str = "") -> list[tuple]:
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
    options: list[tuple] = []
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


def _scenario_options() -> list[tuple]:
    return _options_under(_ASSET_ROOT)


def _upload_options() -> list[tuple]:
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
        "placeholder='Name (optional)' aria-label='Name of the uploaded scenario (optional)' "
        "autocomplete='off' spellcheck='false' "
        "class='upload-name'>"
        "<label id='upload-drop' class='upload-drop'>"
        "<input type='file' name='files' multiple accept='.json,.wkt,.zip' class='visually-hidden'>"
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
_HELP_TEXT: dict[str, str] = {
    **{p.dest: p.gui_help for p in PARAMETERS if p.gui_help},
    "output_base": "Folder the run writes into. Leave it blank to use the derived path "
    "shown greyed out: a new folder per run, named by scenario, mode, the seed "
    "used and the start time (UTC). Type a folder to use instead of that "
    "path; each run still writes into its own start-time folder inside it, so "
    "no run overwrites another. A relative folder is taken under the results "
    "root.",
    "results_only": "Finishes sooner by skipping the trajectory viewer and plots. "
    "Writes every output file to the output folder: the SQLite, the CSVs, and "
    "a config + geometry snapshot. Same as 'uv run run.py'.",
}


def _help_text(dest: str, action: argparse.Action | None = None) -> str:
    """Curated (or argparse) help string for *dest*, or '' when there's none."""
    text = (_HELP_TEXT.get(dest) or (action.help if action else "") or "").strip()
    if not text or text == "show this help message and exit":
        return ""
    return text


# Units stated by each field's own help text, shown in its label.
_UNITS: dict[str, str] = {
    dest: unit for dest in GUI_UNIT_LABELS if (unit := parameter(dest).unit)
}


def _with_unit(text: str, dest: str) -> str:
    unit = _UNITS.get(dest)
    return f"{text} ({unit})" if unit else text


def _tip_id(dest: str) -> str:
    return f"tip-{dest}"


def _described(dest: str, action: argparse.Action | None = None) -> dict:
    """``aria-describedby`` tying a control to its help text, if it has one."""
    return {"aria_describedby": _tip_id(dest)} if _help_text(dest, action) else {}


def _help_button(text: str, dest: str) -> str:
    """The ? that expands a field's help; a real button, so keyboards reach it.

    It sits beside the label, never inside it: a button inside a <label>
    would add "Help" to the control's accessible name.
    """
    import html as _html

    return (
        '<button type="button" class="help-badge" aria-expanded="false" '
        f'aria-controls="{_tip_id(dest)}" '
        f'aria-label="Help: {_html.escape(text, quote=True)}">?</button>'
    )


def _help_tip(dest: str, tip: str) -> NotStr:
    import html as _html

    return NotStr(
        f'<div class="badge-tip" id="{_tip_id(dest)}">{_html.escape(tip)}</div>'
    )


def _lbl(
    text: str,
    dest: str,
    action: argparse.Action | None = None,
    for_: str | None = None,
    control: bool = True,
) -> Any:
    """A field label, with a ? button that expands an in-flow help block.

    The label names the control with id *for_* (default: *dest*). With
    ``control=False`` it is plain text with id ``lbl-<dest>``, for a group
    to reference with aria-labelledby. The help block sits in normal
    document flow, so it is bounded by the field width and never clipped.
    """
    text = _with_unit(text, dest)
    if control:
        label = Label(text, style=_LABEL, fr=for_ or dest)
    else:
        label = Span(text, style=_LABEL, id=f"lbl-{dest}")
    tip = _help_text(dest, action)
    if not tip:
        return label
    return Div(
        Div(label, NotStr(_help_button(text, dest)), cls="lbl-line"),
        _help_tip(dest, tip),
        cls="lblwrap",
    )


def _switch(
    dest: str, label: str, checked: bool = False, action: argparse.Action | None = None
) -> Any:
    """An on/off field: a native checkbox, visually a switch.

    The checkbox stays focusable and is toggled by the browser (click or
    Space); the track and knob are styled from its :checked and
    :focus-visible state, so the look can never disagree with the value.
    """
    import html as _html

    _chk = "checked " if checked else ""
    _tip = _help_text(dest, action)
    described = f'aria-describedby="{_tip_id(dest)}" ' if _tip else ""
    _label_node = Label(
        label,
        fr=dest,
        style=f"{_GROTESK};font-size:12px;font-weight:500;color:var(--ink)",
    )
    # Presence sentinel: an unchecked box posts nothing, so without it an
    # unchecked switch and an absent field look the same. The checkbox comes
    # later in the form and wins when checked (last value wins).
    _row = Div(
        NotStr(f'<input type="hidden" name="{dest}" value="off">'),
        Div(
            _label_node,
            *([NotStr(_help_button(label, dest))] if _tip else []),
            cls="lbl-line",
        ),
        NotStr(
            '<span class="switch">'
            f'<input type="checkbox" class="sw-input" id="{dest}" name="{dest}" '
            f'value="on" {_chk}{described}>'
            '<span class="sw-track" aria-hidden="true"><span class="sw-knob"></span>'
            "</span></span>"
        ),
        style="display:flex;align-items:center;justify-content:space-between;gap:10px",
    )
    if not _tip:
        return _row
    return Div(
        _row,
        NotStr(
            f'<div class="badge-tip" id="{_tip_id(dest)}">{_html.escape(_tip)}</div>'
        ),
        cls="lblwrap",
    )


def _incap_toggle() -> Any:
    return Div(
        _lbl("Incapacitation mode", "incapacitation_mode", control=False),
        Div(
            NotStr(
                '<button type="button" class="mode-btn" id="btn-prob"'
                ' aria-pressed="false"'
                " onclick=\"setTenabilityMode('probabilistic')\">Probabilistic</button>"
                '<button type="button" class="mode-btn active" id="btn-det"'
                ' aria-pressed="true"'
                " onclick=\"setTenabilityMode('deterministic')\">Deterministic</button>"
            ),
            cls="mode-toggle",
            role="group",
            aria_labelledby="lbl-incapacitation_mode",
            **_described("incapacitation_mode"),
        ),
        Input(
            type="hidden",
            id="incapacitation_mode",
            name="incapacitation_mode",
            value=default("incapacitation_mode"),
        ),
        NotStr(
            '<div id="incap-dist" style="display:none;margin-top:10px;border-radius:9px;overflow:hidden;background:var(--surface-panel)">'
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
    "width:100%"
)


def _choice_select(action: argparse.Action) -> Any:
    """A dropdown of the flag's argparse choices, its default preselected.

    A flag whose default is None gets a leading blank "default" option, which
    form_to_opts maps back to None so the model applies its own default.
    """
    dest = action.dest
    default = "" if action.default is None else str(action.default)
    pairs = [("default", "")] if action.default is None else []
    pairs += [(str(c), str(c)) for c in action.choices]
    options = [Option(ol, value=ov, selected=(ov == default)) for ol, ov in pairs]
    return Div(
        _lbl(dest.replace("_", " ").capitalize(), dest, action, for_=dest),
        Select(*options, id=dest, name=dest, style=_SELECT, **_described(dest, action)),
        style=_FIELD,
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
        Select(
            *children,
            name="scenario",
            id="scenario",
            style=_SELECT,
            **_described("scenario"),
        ),
        *([note] if note is not None else []),
        id="scenario-block",
        style=_FIELD,
    )


# Decimal fields are text inputs: Chromium on macOS shows a number input's
# value in the OS region's format ("1,6" on a German region) whatever the
# page language, while the server parses with float(). A text input shows
# the value exactly as sent; the pattern flags a decimal comma before
# submit, which float() would reject anyway. No inputmode=decimal: a
# comma-region keypad may offer no point (#552).
_DECIMAL_TEXT = {
    "autocomplete": "off",
    "spellcheck": "false",
    "pattern": "[^,]*",
    "title": "Use a point as decimal separator, e.g. 1.6",
}


def _field(action: argparse.Action) -> Any:
    dest = action.dest

    if dest == "scenario":
        return scenario_block()

    if dest == "seed":
        return Div(
            _lbl("Seed", "seed", action),
            # Blank maps to None, as on the CLI: the scenario's baseSeed.
            Input(
                id=dest,
                name=dest,
                type="number",
                step="1",
                min="0",
                placeholder="blank = scenario baseSeed",
                style=_INPUT,
                **_described(dest, action),
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
                    **_described(dest, action),
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
                    placeholder="blank = no cache",
                    style=_INPUT + ";flex:1;min-width:0",
                    **_described(dest, action),
                ),
                _browse_button("vis_cache", "file"),
                style="display:flex;gap:7px",
            ),
            style=_FIELD,
        )

    if dest == "incapacitation_mode":
        return _incap_toggle()

    if dest == "susceptibility_sigma":
        val = str(action.default)
        return Div(
            Div(
                _lbl("Susceptibility σ", "susceptibility_sigma", action),
                Input(
                    id=dest,
                    name=dest,
                    value=val,
                    style=_INPUT,
                    **_DECIMAL_TEXT,
                    **_described(dest, action),
                ),
                style=_FIELD,
            ),
            id="sigma-row",
            style="display:none",
        )

    if action.choices is not None:
        return _choice_select(action)

    if _is_bool(action):
        # Initial toggle state follows the flag's own default, so an
        # on-by-default CLI flag (e.g. rerouting) renders checked.
        return _switch(
            dest,
            dest.replace("_", " ").capitalize(),
            checked=bool(action.default),
            action=action,
        )

    value = "" if action.default is None else str(action.default)
    label = dest.replace("_", " ").capitalize()
    if action.type is float:
        return Div(
            _lbl(label, dest, action),
            Input(
                id=dest,
                name=dest,
                value=value,
                style=_INPUT,
                **_DECIMAL_TEXT,
                **_described(dest, action),
            ),
            style=_FIELD,
        )
    if action.type is int:
        return Div(
            _lbl(label, dest, action),
            Input(
                id=dest,
                name=dest,
                type="number",
                step="1",
                value=value,
                style=_INPUT,
                **_described(dest, action),
            ),
            style=_FIELD,
        )
    return Div(
        _lbl(label, dest, action),
        Input(
            id=dest, name=dest, value=value, style=_INPUT, **_described(dest, action)
        ),
        style=_FIELD,
    )


def _details_block(
    title: str, accent: str, fields: list[Any], open_: bool = False
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
                aria_describedby=_tip_id("results_only"),
                style=(
                    "display:flex;align-items:center;justify-content:center;gap:6px;"
                    "flex:1;padding:11px;border-radius:12px;cursor:pointer;"
                    f"{_GROTESK};font-size:13.5px;font-weight:600;"
                    "background:transparent;color:var(--gold-ink);"
                    "border:1px solid rgba(244,196,48,.45)"
                ),
            ),
            NotStr(_help_button("Results only", "results_only")),
            style="display:flex;align-items:center;gap:8px",
        ),
        _help_tip("results_only", _HELP_TEXT["results_only"]),
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
    "_exit_history.csv",
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
                    data_results_root=results_root().as_posix(),
                    autocomplete="off",
                    spellcheck="false",
                    style=_INPUT,
                    **_described("output_base"),
                ),
                # Filled by the autofill script while a folder is typed: each
                # run still gets its own start-time folder inside it (#319).
                Div(id="output-run-note", style=_PREVIEW_ROW + ";display:none"),
                style=_FIELD,
            ),
            Div(
                Div(
                    "6 artifacts",
                    id="artifact-heading",
                    style=f"{_GROTESK};font-size:9px;font-weight:600;letter-spacing:.07em;"
                    f"text-transform:uppercase;color:var(--ink-faint);margin-bottom:6px",
                ),
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
    sections: list[Any] = []

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
            cls="form-scroll",
            style="display:flex;flex-direction:column;gap:9px;margin:-4px;padding:4px",
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
        id="run-form",
        hx_post=post_url,
        hx_target="#run-panel",
        hx_swap="innerHTML show:top",
        # The upload inputs sit inside this form for layout only. Exclude them
        # so a staged file is not serialised into the urlencoded run request.
        hx_params="not files,upload_name",
        style="display:flex;flex-direction:column;gap:14px",
    )


def results_root() -> Path:
    """Root of the derived output folders (see ``RESULTS_ENV``)."""
    return frontend.results_root(_WORK_ROOT)


def default_output_base(scenario: Any, mode: Any, seed: Any, stamp: str) -> str:
    """Derived output folder of one run (``frontend.default_output_base``)."""
    return frontend.default_output_base(scenario, mode, seed, stamp, results_root())


def typed_output_base(typed: str, stamp: str) -> str:
    """Run folder under a typed "Output folder" (``frontend.typed_output_base``)."""
    return frontend.typed_output_base(typed, stamp, results_root())


def _convert(action: argparse.Action, raw: Any) -> Any:
    """Apply the parser's own type check, naming the field when it fails."""
    if not action.type:
        return str(raw)
    try:
        return action.type(raw)
    except (argparse.ArgumentTypeError, ValueError, TypeError) as exc:
        raise ValueError(f"{action.dest}: {exc}") from exc


def form_to_opts(
    form: dict[str, Any], *, baseseed: Any = None, stamp: str | None = None
) -> Namespace:
    """Resolve a submitted form into the options ``build_run_kwargs`` takes.

    ``baseseed`` is the scenario's own seed, which a blank Seed field falls
    back to; it names the derived output folder. ``stamp`` is the run's start
    time (see ``runner.run_stamp``); it defaults to now.
    """
    parser = _load_parser()
    opts: dict[str, Any] = {}
    for action in parser._actions:
        dest = action.dest
        if dest not in RUN_OPTIONS:
            continue
        if _is_bool(action):
            # Absent means the flag's own default (rerouting is on by default);
            # the switch's hidden sentinel posts "off" when it is unchecked.
            raw = form.get(dest)
            opts[dest] = (
                action.default
                if raw is None
                else str(raw).lower() in ("on", "true", "1", "yes")
            )
            continue
        raw = form.get(dest)
        if raw is None or str(raw).strip() == "":
            opts[dest] = action.default
            continue
        opts[dest] = _convert(action, raw)
        if action.choices is not None and opts[dest] not in action.choices:
            raise ValueError(
                f"{dest}: {raw!r} is not one of {', '.join(map(str, action.choices))}"
            )
    opts["collect_route_cost_history"] = True

    # The output paths are always derived here from the scenario and the
    # "Output folder" (typed, or the derived default). Posted output_* values
    # are ignored: they used to come from hidden fields that a polling script
    # filled in, so a run submitted before its next poll wrote to the previous
    # scenario's folder (#330).
    sc = run_name(opts.get("scenario"))
    mode = str(opts.get("incapacitation_mode") or default("incapacitation_mode"))
    stamp = stamp or run_stamp(utc_now())
    typed = str(form.get("output_base") or "").strip().replace("\\", "/").rstrip("/")
    base = (
        typed_output_base(typed, stamp)
        if typed
        else default_output_base(
            opts.get("scenario"),
            mode,
            opts["seed"] if opts.get("seed") is not None else baseseed,
            stamp,
        )
    )
    opts.update(output_paths(base, sc))

    return Namespace(**opts)
