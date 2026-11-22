#!/usr/bin/env python3
"""Validate the generated 42vibes VS Code themes.

Checks:
  * both theme files are valid JSON with the expected name/type,
  * all required workbench colors exist and are valid hex colors,
  * terminal.ansi* carries exactly the 16 palette.ansi values,
  * tokenColors is non-empty and every entry has scope + settings.foreground,
  * bold/italic are only used in the scopes allowed for this theme,
  * key foreground/background pairs meet the WCAG contrast thresholds,
  * preview/palette-*.svg are valid XML and contain every semantic/ANSI hex,
  * preview/palette-*.png exist and are valid PNG files,
  * README.md and README.de.md carry markers, switcher, screenshot and
    preview image paths (PNG only, no SVG), all sections, the packaging
    command and the license notice,
  * package.json uses valid uiTheme values (``vs-dark`` and ``vs``) and the
    themes carry no non-functional placeholder color keys,
  * build.py --check exits 0 and two runs produce the same digest.

Run: python3 validate.py   (exit 0 = ok, exit 1 = errors)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PALETTE_FILE = ROOT / "vendor" / "palette.json"
PACKAGE_FILE = ROOT / "package.json"

THEMES = {
    "dark": ROOT / "themes" / "42vibes-color-theme.json",
    "light": ROOT / "themes" / "42vibes-light-color-theme.json",
}

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# WCAG thresholds. Text needs 4.5; the status bar is treated as UI text (3.0).
MIN_TEXT_CONTRAST = 4.5
MIN_STATUS_CONTRAST = 3.0

CONTRAST_PAIRS = [
    ("editor.foreground", "editor.background", MIN_TEXT_CONTRAST),
    (
        "list.activeSelectionForeground",
        "list.activeSelectionBackground",
        MIN_TEXT_CONTRAST,
    ),
    ("statusBar.foreground", "statusBar.background", MIN_STATUS_CONTRAST),
    ("terminal.foreground", "terminal.background", MIN_TEXT_CONTRAST),
]

# Workbench colors required by the theme specification. The legacy indent guide
# keys are emitted as well because VS Code 1.80 still honours them (deprecated),
# while ``...1`` is the authoritative key since 1.80.
REQUIRED_COLORS = [
    "editor.background",
    "editor.foreground",
    "editorLineNumber.foreground",
    "editorLineNumber.activeForeground",
    "editorCursor.foreground",
    "editor.selectionBackground",
    "editor.selectionHighlightBackground",
    "editor.findMatchBackground",
    "editor.findMatchHighlightBackground",
    "editor.wordHighlightBackground",
    "editorIndentGuide.background1",
    "editorIndentGuide.activeBackground1",
    "editorIndentGuide.background",
    "editorIndentGuide.activeBackground",
    "editorWhitespace.foreground",
    "editorOverviewRuler.border",
    "focusBorder",
    "contrastBorder",
    "foreground",
    "descriptionForeground",
    "errorForeground",
    "sideBar.background",
    "sideBar.foreground",
    "sideBar.border",
    "sideBarTitle.foreground",
    "sideBarSectionHeader.background",
    "sideBarSectionHeader.foreground",
    "activityBar.background",
    "activityBar.foreground",
    "activityBar.border",
    "activityBarBadge.background",
    "activityBarBadge.foreground",
    "statusBar.background",
    "statusBar.foreground",
    "statusBar.border",
    "statusBarItem.activeBackground",
    "statusBarItem.hoverBackground",
    "statusBarItem.prominentBackground",
    "statusBarItem.prominentForeground",
    "statusBarItem.errorBackground",
    "statusBarItem.errorForeground",
    "statusBarItem.warningBackground",
    "statusBarItem.warningForeground",
    "titleBar.activeBackground",
    "titleBar.activeForeground",
    "titleBar.inactiveBackground",
    "titleBar.inactiveForeground",
    "titleBar.border",
    "tab.activeBackground",
    "tab.inactiveBackground",
    "tab.activeBorderTop",
    "tab.activeBorder",
    "tab.border",
    "tab.activeForeground",
    "tab.inactiveForeground",
    "editorGroupHeader.tabsBackground",
    "editorGroupHeader.border",
    "editorGroupHeader.tabsBorder",
    "panel.background",
    "panel.border",
    "panelTitle.activeForeground",
    "panelTitle.activeBorder",
    "list.activeSelectionBackground",
    "list.activeSelectionForeground",
    "list.inactiveSelectionBackground",
    "list.hoverBackground",
    "list.hoverForeground",
    "list.errorForeground",
    "list.warningForeground",
    "input.background",
    "input.foreground",
    "input.border",
    "input.placeholderForeground",
    "dropdown.background",
    "dropdown.border",
    "dropdown.foreground",
    "button.background",
    "button.foreground",
    "button.hoverBackground",
    "badge.background",
    "badge.foreground",
    "notificationCenter.border",
    "notifications.background",
    "notifications.foreground",
    "notifications.border",
    "widget.shadow",
    "widget.border",
    "peekViewResult.background",
    "peekView.border",
    "peekViewEditor.background",
    "quickInput.background",
    "quickInput.foreground",
    "menu.background",
    "menu.foreground",
    "menu.selectionBackground",
    "menu.selectionForeground",
    "menu.border",
    "scrollbarSlider.background",
    "scrollbarSlider.hoverBackground",
    "scrollbarSlider.activeBackground",
    "minimap.background",
    "breadcrumb.foreground",
    "breadcrumb.focusForeground",
    "breadcrumb.background",
    "gitDecoration.addedResourceForeground",
    "gitDecoration.modifiedResourceForeground",
    "gitDecoration.deletedResourceForeground",
    "gitDecoration.untrackedResourceForeground",
    "gitDecoration.conflictingResourceForeground",
    "gitDecoration.ignoredResourceForeground",
    "diffEditor.insertedTextBackground",
    "diffEditor.removedTextBackground",
    "diffEditor.insertedLineBackground",
    "diffEditor.removedLineBackground",
    "editorError.foreground",
    "editorWarning.foreground",
    "editorInfo.foreground",
    "editorHint.foreground",
    "terminal.background",
    "terminal.foreground",
    "terminalCursor.foreground",
    "terminal.selectionBackground",
]

# Non-functional keys must not be emitted again: VS Code ignores the first two
# (their real spellings are tab.activeBorderTop / terminalCursor.foreground),
# and the last two are not registered workbench colors at all.
FORBIDDEN_COLORS = {
    "tab.borderTop",
    "terminal.cursorForeground",
    "panel.titleForeground",
    "peekView.background",
}

ANSI_SLOTS = [
    ("black", "ansiBlack"),
    ("red", "ansiRed"),
    ("green", "ansiGreen"),
    ("yellow", "ansiYellow"),
    ("blue", "ansiBlue"),
    ("magenta", "ansiMagenta"),
    ("cyan", "ansiCyan"),
    ("white", "ansiWhite"),
    ("bright_black", "ansiBrightBlack"),
    ("bright_red", "ansiBrightRed"),
    ("bright_green", "ansiBrightGreen"),
    ("bright_yellow", "ansiBrightYellow"),
    ("bright_blue", "ansiBrightBlue"),
    ("bright_magenta", "ansiBrightMagenta"),
    ("bright_cyan", "ansiBrightCyan"),
    ("bright_white", "ansiBrightWhite"),
]

SEMANTIC_KEYS = [
    "bg", "bg_deep", "surface", "surface_high", "surface_max", "text",
    "text_muted", "text_faint", "accent", "interactive", "warm", "border",
    "success", "warning", "error", "info",
]

PREVIEWS = {
    mode: ROOT / "preview" / f"palette-{mode}.svg" for mode in THEMES
}
PREVIEW_PNGS = {
    mode: ROOT / "preview" / f"palette-{mode}.png" for mode in THEMES
}
EXPECTED_UI_THEMES = {
    "42vibes-color-theme.json": "vs-dark",
    "42vibes-light-color-theme.json": "vs",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
README_FILES = {
    "en": ROOT / "README.md",
    "de": ROOT / "README.de.md",
}
README_SPECS = {
    "en": {
        "switcher": "**English** · [Deutsch](README.de.md)",
        "preview_note": "Generated palette preview",
        "sections": [
            "## Screenshots", "## Installation", "## Choosing dark/light",
            "## Terminal ANSI coupling", "## Structure",
            "## Build and validation", "## Contrast values",
            "## Packaging note", "## Known limitations", "## License",
        ],
    },
    "de": {
        "switcher": "[English](README.md) · **Deutsch**",
        "preview_note": "Generierte Palettenvorschau",
        "sections": [
            "## Screenshots", "## Installation", "## Dark/Light auswählen",
            "## Terminal-ANSI-Kopplung", "## Struktur",
            "## Build und Validierung", "## Kontrastwerte",
            "## Packaging-Hinweis", "## Bekannte Einschränkungen", "## Lizenz",
        ],
    },
}
SCREENSHOTS = [
    "docs/screenshot-dark-code.png",
    "docs/screenshot-dark-markdown.png",
    "docs/screenshot-light-code.png",
    "docs/screenshot-light-markdown.png",
    "docs/screenshot-bold-inspect.png",
]
PACKAGING_MARKERS = (
    "npx --yes @vscode/vsce package",
    "repository",
    "https://github.com/42vibes/42vibes-vscode",
)
SVG_LINK_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\.svg(?:[?#][^)]*)?\)", re.IGNORECASE)
SVG_HTML_RE = re.compile(r"<img[^>]+src=[\"'][^\"']*\.svg", re.IGNORECASE)
PALETTE_START = "<!-- palette:start -->"
PALETTE_END = "<!-- palette:end -->"
SVG_NS = "http://www.w3.org/2000/svg"


def parse_color(value: str) -> tuple[float, float, float, float]:
    raw = value.lstrip("#")
    if len(raw) in (3, 4):
        raw = "".join(char * 2 for char in raw)
    r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    alpha = int(raw[6:8], 16) / 255 if len(raw) == 8 else 1.0
    return r, g, b, alpha


def relative_luminance(rgb: tuple[float, float, float, float]) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b, _ = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def composite(
    fg: tuple[float, float, float, float],
    bg: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    alpha = fg[3]
    return (
        fg[0] * alpha + bg[0] * (1 - alpha),
        fg[1] * alpha + bg[1] * (1 - alpha),
        fg[2] * alpha + bg[2] * (1 - alpha),
        1.0,
    )


def contrast_ratio(
    fg: tuple[float, float, float, float],
    bg: tuple[float, float, float, float],
) -> float:
    fg = composite(fg, bg) if fg[3] < 1 else fg
    light, dark = sorted(
        (relative_luminance(fg), relative_luminance(bg)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


def allowed_font_style(scope: str, style: str) -> bool:
    is_heading = scope.startswith("markup.heading") or (
        scope.startswith("heading.") and scope.endswith(".markdown")
    )
    is_comment = scope.startswith("comment") or scope.split(".")[-1] == "comment"
    if style == "bold":
        return is_heading or scope in {"markup.bold", "invalid", "invalid.illegal"}
    if style == "italic":
        return is_comment or scope == "markup.italic"
    return True


def check_theme(mode: str, palette: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    path = THEMES[mode]

    try:
        theme = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{path.name}: file not found (run `python3 build.py`)"], notes
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"], notes

    if theme.get("type") != mode:
        errors.append(f"{path.name}: type is {theme.get('type')!r}, expected {mode!r}")
    if not isinstance(theme.get("name"), str) or not theme["name"]:
        errors.append(f"{path.name}: missing or empty name")

    colors = theme.get("colors")
    if not isinstance(colors, dict):
        return errors + [f"{path.name}: colors is missing or not an object"], notes

    for key in REQUIRED_COLORS:
        if key not in colors:
            errors.append(f"{path.name}: missing required color {key}")
    for key in FORBIDDEN_COLORS:
        if key in colors:
            errors.append(f"{path.name}: non-functional color key must be removed: {key}")
    for key, value in colors.items():
        if not isinstance(value, str) or not HEX_RE.match(value):
            errors.append(f"{path.name}: invalid color {key}={value!r}")

    ansi = palette[mode]["ansi"]
    for name, key in ANSI_SLOTS:
        slot = f"terminal.{key}"
        if slot not in colors:
            errors.append(f"{path.name}: missing ANSI slot {slot}")
            continue
        expected = ansi[name].lower()
        if colors[slot].lower() != expected:
            errors.append(
                f"{path.name}: {slot}={colors[slot]} does not match palette "
                f"ansi.{name}={expected}"
            )

    token_colors = theme.get("tokenColors")
    if not isinstance(token_colors, list) or not token_colors:
        errors.append(f"{path.name}: tokenColors is missing or empty")
        token_colors = []
    for index, entry in enumerate(token_colors):
        label = f"{path.name}: tokenColors[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: not an object")
            continue
        scope = entry.get("scope")
        if not scope:
            errors.append(f"{label}: missing scope")
            continue
        scopes = [scope] if isinstance(scope, str) else list(scope)
        settings = entry.get("settings")
        if not isinstance(settings, dict):
            errors.append(f"{label}: missing settings")
            continue
        foreground = settings.get("foreground")
        if not foreground:
            errors.append(f"{label}: missing settings.foreground")
        elif not isinstance(foreground, str) or not HEX_RE.match(foreground):
            errors.append(f"{label}: invalid settings.foreground {foreground!r}")
        font_style = settings.get("fontStyle")
        if font_style:
            for style in str(font_style).split():
                for item in scopes:
                    if not allowed_font_style(item, style):
                        errors.append(
                            f"{label}: fontStyle {style!r} not allowed for "
                            f"scope {item!r}"
                        )

    for fg_key, bg_key, minimum in CONTRAST_PAIRS:
        fg, bg = colors.get(fg_key), colors.get(bg_key)
        if not fg or not bg or not HEX_RE.match(fg) or not HEX_RE.match(bg):
            continue
        ratio = contrast_ratio(parse_color(fg), parse_color(bg))
        status = "ok" if ratio >= minimum else "FAIL"
        notes.append(
            f"{fg_key} on {bg_key}: {ratio:.2f}:1 "
            f"(min {minimum:.1f}, {status})"
        )
        if ratio < minimum:
            errors.append(
                f"{path.name}: contrast {ratio:.2f} < {minimum:.1f} for "
                f"{fg_key} on {bg_key}"
            )

    return errors, notes


def check_package() -> list[str]:
    errors: list[str] = []
    try:
        package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"package.json: cannot read: {exc}"]

    themes = package.get("contributes", {}).get("themes", [])
    if len(themes) != 2:
        errors.append(f"package.json: expected 2 contributed themes, got {len(themes)}")
    for entry in themes:
        target = entry.get("path", "").lstrip("./")
        if not (ROOT / target).exists():
            errors.append(f"package.json: theme path does not exist: {target}")
            continue
        expected = EXPECTED_UI_THEMES.get(Path(target).name)
        actual = entry.get("uiTheme")
        if expected and actual != expected:
            errors.append(
                f"package.json: {Path(target).name} has uiTheme {actual!r}, "
                f"expected {expected!r}"
            )
    return errors


def check_readmes() -> list[str]:
    errors: list[str] = []
    for lang, path in README_FILES.items():
        spec = README_SPECS[lang]
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            errors.append(f"{path.name}: cannot read: {exc}")
            continue
        if spec["switcher"] not in "\n".join(text.splitlines()[:5]):
            errors.append(f"{path.name}: language switcher missing or not at the top")
        if PALETTE_START not in text or PALETTE_END not in text:
            errors.append(f"{path.name}: palette markers are missing")
        if spec["preview_note"] not in text:
            errors.append(f"{path.name}: preview is not marked as generated")
        for mode in THEMES:
            png = f"preview/palette-{mode}.png"
            if png not in text:
                errors.append(f"{path.name}: missing image path {png}")
            if f"preview/palette-{mode}.svg" in text:
                errors.append(f"{path.name}: README must reference {png}, not SVG")
            if not (ROOT / png).is_file():
                errors.append(f"{png}: file not found")
        if SVG_LINK_RE.search(text) or SVG_HTML_RE.search(text):
            errors.append(
                f"{path.name}: SVG image references are forbidden (use PNG)"
            )
        for marker in PACKAGING_MARKERS:
            if marker not in text:
                errors.append(f"{path.name}: missing packaging marker {marker!r}")
        for screenshot in SCREENSHOTS:
            if screenshot not in text:
                errors.append(f"{path.name}: missing screenshot path {screenshot}")
            if not (ROOT / screenshot).is_file():
                errors.append(f"{screenshot}: file not found")
        for section in spec["sections"]:
            if section not in text:
                errors.append(f"{path.name}: missing section {section!r}")
        for phrase in ("[`LICENSE`](LICENSE)", "MIT", "Copyright 2026 42vibes"):
            if phrase not in text:
                errors.append(f"{path.name}: missing license reference {phrase!r}")
    if not (ROOT / "LICENSE").is_file():
        errors.append("LICENSE: file not found")
    makefile = ROOT / "Makefile"
    try:
        make_text = makefile.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        errors.append(f"Makefile: cannot read: {exc}")
    else:
        for marker in PACKAGING_MARKERS[:3]:
            if marker not in make_text:
                errors.append(f"Makefile: missing packaging marker {marker!r}")
    return errors


def check_preview(palette: dict) -> list[str]:
    errors: list[str] = []

    for mode, path in PREVIEWS.items():
        relative = path.relative_to(ROOT)
        if not path.exists():
            errors.append(f"{relative}: file not found (run `python3 build.py`)")
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append(f"{relative}: invalid XML: {exc}")
            continue
        if root.tag != f"{{{SVG_NS}}}svg":
            errors.append(f"{relative}: root must be <svg xmlns={SVG_NS!r}>")
        if "ui-monospace" not in (root.get("font-family") or ""):
            errors.append(f"{relative}: missing font-family 'ui-monospace, monospace'")
        if "ui-monospace, monospace" not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative}: font-family attribute missing in SVG text")

        source = path.read_text(encoding="utf-8").lower()
        for name in SEMANTIC_KEYS:
            value = palette[mode]["semantic"][name]
            if value.lower() not in source:
                errors.append(f"{relative}: missing semantic hex {name}={value}")
            if name not in source:
                errors.append(f"{relative}: missing semantic label {name}")
        for name, _key in ANSI_SLOTS:
            value = palette[mode]["ansi"][name]
            if value.lower() not in source:
                errors.append(f"{relative}: missing ANSI hex {name}={value}")
            if name not in source:
                errors.append(f"{relative}: missing ANSI label {name}")

    for mode, path in PREVIEW_PNGS.items():
        relative = path.relative_to(ROOT)
        if not path.is_file():
            errors.append(f"{relative}: file not found (run `python3 build.py`)")
            continue
        data = path.read_bytes()
        if not data.startswith(PNG_SIGNATURE):
            errors.append(f"{relative}: not a PNG file")
        elif len(data) < 1024:
            errors.append(f"{relative}: PNG is suspiciously small ({len(data)} bytes)")

    return errors


BUILD_DIGEST_SCRIPT = r'''
import hashlib, importlib.util, json
spec = importlib.util.spec_from_file_location("build_themes", "build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
palette = json.loads(module.PALETTE_FILE.read_text(encoding="utf-8"))
artifacts, _skipped = module.build_artifacts(palette)
digest = hashlib.sha256()
for path, content in artifacts:
    digest.update(str(path.relative_to(module.ROOT)).encode())
    digest.update(hashlib.sha256(content).digest())
print(digest.hexdigest())
'''


def build_digest() -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-c", BUILD_DIGEST_SCRIPT],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check_build() -> list[str]:
    result = subprocess.run(
        [sys.executable, "build.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return [
            "build.py --check failed:\n"
            + (result.stdout + result.stderr).strip()
        ]
    return []


def check_determinism() -> tuple[list[str], str]:
    first = build_digest()
    second = build_digest()
    if first[0] != 0 or second[0] != 0:
        return ["build.py: recomputation failed: " + (first[2] or second[2])], ""
    if first[1] != second[1]:
        return [
            f"build.py is not deterministic ({first[1]} != {second[1]})"
        ], ""
    return [], first[1]


def main() -> int:
    palette = json.loads(PALETTE_FILE.read_text(encoding="utf-8"))
    errors = check_package()
    readme_errors = check_readmes()
    errors.extend(readme_errors)
    for mode in THEMES:
        theme_errors, notes = check_theme(mode, palette)
        errors.extend(theme_errors)
        print(f"[{mode}]")
        for note in notes:
            print(f"  {note}")

    preview_errors = check_preview(palette)
    errors.extend(preview_errors)
    build_errors = check_build()
    errors.extend(build_errors)
    determinism_errors, digest = check_determinism()
    errors.extend(determinism_errors)

    if not preview_errors:
        print(
            "[preview] SVGs valid; PNGs valid; all semantic and ANSI hex "
            "values present"
        )
    if not readme_errors:
        print(
            "[readme] README.md and README.de.md: markings, switcher, PNG "
            "paths, packaging note, sections and license present"
        )
    if not build_errors and not determinism_errors:
        print(f"[build] deterministic (sha256 {digest[:12]}…)")

    if errors:
        print("\nFAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("\nOK: both themes and palette previews are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
