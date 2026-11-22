#!/usr/bin/env python3
"""Generate the 42vibes VS Code themes from vendor/palette.json.

Input:  vendor/palette.json (copy of ../42vibes-palette/palette.json)
Output: themes/42vibes-color-theme.json (dark)
        themes/42vibes-light-color-theme.json (light)
        preview/palette-dark.svg / .png
        preview/palette-light.svg / .png
        the palette block in README.md (English) and README.de.md (German)
        (markers are kept)

The generated files are checked in. Run ``python3 build.py`` after palette
changes and ``python3 build.py --check`` to verify that the checked-in files
are current. Output is deterministic: no timestamps, stable key order.

The PNG previews are rendered from the generated SVGs with ImageMagick
(``convert``/``magick``). They exist because the VS Code Marketplace rejects
SVG images in README files. If ImageMagick is unavailable, ``build.py`` leaves
the checked-in PNGs untouched and prints a warning.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PALETTE_FILE = ROOT / "vendor" / "palette.json"
THEMES = {
    "dark": {
        "path": ROOT / "themes" / "42vibes-color-theme.json",
        "name": "42vibes",
        "type": "dark",
    },
    "light": {
        "path": ROOT / "themes" / "42vibes-light-color-theme.json",
        "name": "42vibes Light",
        "type": "light",
    },
}

SCHEMA = "vscode://schemas/color-theme"

PREVIEW_FILES = {
    mode: ROOT / "preview" / f"palette-{mode}.svg" for mode in THEMES
}
PREVIEW_PNG_FILES = {
    mode: ROOT / "preview" / f"palette-{mode}.png" for mode in THEMES
}
README_FILES = {
    "en": ROOT / "README.md",
    "de": ROOT / "README.de.md",
}
PALETTE_START = "<!-- palette:start -->"
PALETTE_END = "<!-- palette:end -->"

SEMANTIC_KEYS = [
    "bg", "bg_deep", "surface", "surface_high", "surface_max", "text",
    "text_muted", "text_faint", "accent", "interactive", "warm", "border",
    "success", "warning", "error", "info",
]

# ---------------------------------------------------------------------------
# HSL ramps -- identical to the other 42vibes targets (OpenCode, bash, vim).
# ---------------------------------------------------------------------------

STEPS = ["100", "200", "300", "400", "500", "600", "700", "800", "900"]
DARK_OFFSETS = dict(
    zip(STEPS, [0.28, 0.16, 0.09, 0.04, 0.00, -0.10, -0.20, -0.30, -0.38])
)
LIGHT_OFFSETS = dict(
    zip(STEPS, [-0.30, -0.20, -0.12, -0.05, 0.00, 0.08, 0.15, 0.22, 0.28])
)
SATURATION_SCALE = 0.55  # only the extreme steps 100 and 900


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def rgb_to_hsl(value: str) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(value))
    high, low = max(r, g, b), min(r, g, b)
    light = (high + low) / 2
    if high == low:
        return 0.0, 0.0, light
    delta = high - low
    saturation = delta / (1 - abs(2 * light - 1))
    if high == r:
        hue = ((g - b) / delta) % 6
    elif high == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation, light


def hsl_to_hex(hue: float, saturation: float, light: float) -> str:
    light = max(0.0, min(1.0, light))
    saturation = max(0.0, min(1.0, saturation))
    chroma = (1 - abs(2 * light - 1)) * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    m = light - chroma / 2
    if hue < 60:
        r, g, b = chroma, x, 0
    elif hue < 120:
        r, g, b = x, chroma, 0
    elif hue < 180:
        r, g, b = 0, chroma, x
    elif hue < 240:
        r, g, b = 0, x, chroma
    elif hue < 300:
        r, g, b = x, 0, chroma
    else:
        r, g, b = chroma, 0, x
    return rgb_to_hex(((r + m) * 255, (g + m) * 255, (b + m) * 255))


def shift(anchor: str, offsets: dict[str, float]) -> dict[str, str]:
    """Move only HSL lightness; soften the ends of the ramp slightly."""
    hue, saturation, light = rgb_to_hsl(anchor)
    return {
        step: hsl_to_hex(
            hue,
            saturation * (SATURATION_SCALE if step in ("100", "900") else 1.0),
            light + offset,
        )
        for step, offset in offsets.items()
    }


def ramps(mode: str, variant: dict) -> dict[str, dict[str, str]]:
    offsets = DARK_OFFSETS if mode == "dark" else LIGHT_OFFSETS
    return {name: shift(color, offsets) for name, color in variant["hues"].items()}


# ---------------------------------------------------------------------------
# Color slots (workbench)
# ---------------------------------------------------------------------------

ANSI_KEYS = {
    "black": "ansiBlack",
    "red": "ansiRed",
    "green": "ansiGreen",
    "yellow": "ansiYellow",
    "blue": "ansiBlue",
    "magenta": "ansiMagenta",
    "cyan": "ansiCyan",
    "white": "ansiWhite",
    "bright_black": "ansiBrightBlack",
    "bright_red": "ansiBrightRed",
    "bright_green": "ansiBrightGreen",
    "bright_yellow": "ansiBrightYellow",
    "bright_blue": "ansiBrightBlue",
    "bright_magenta": "ansiBrightMagenta",
    "bright_cyan": "ansiBrightCyan",
    "bright_white": "ansiBrightWhite",
}

SHADOW = {"dark": "#00000080", "light": "#0b1a2640"}


def build_colors(mode: str, variant: dict) -> dict[str, str]:
    s = variant["semantic"]
    r = ramps(mode, variant)
    g = r["gray"]
    green = r["green"]
    red = r["red"]

    colors: list[tuple[str, str]] = [
        # Editor
        ("editor.background", s["bg"]),
        ("editor.foreground", s["text"]),
        ("editorLineNumber.foreground", s["text_faint"]),
        ("editorLineNumber.activeForeground", s["text_muted"]),
        ("editorCursor.foreground", s["accent"]),
        ("editor.selectionBackground", s["surface_high"]),
        ("editor.selectionHighlightBackground", s["surface_max"] + "55"),
        ("editor.findMatchBackground", s["warm"] + "66"),
        ("editor.findMatchHighlightBackground", s["warm"] + "33"),
        ("editor.wordHighlightBackground", s["interactive"] + "33"),
        # New indent guide keys (VS Code 1.80+) plus the legacy spellings.
        # 1.80 deprecated ``editorIndentGuide.background``/``activeBackground``
        # but still honours them, so both pairs are emitted for compatibility.
        ("editorIndentGuide.background1", s["surface"]),
        ("editorIndentGuide.activeBackground1", s["border"]),
        ("editorIndentGuide.background", s["surface"]),
        ("editorIndentGuide.activeBackground", s["border"]),
        ("editorWhitespace.foreground", s["surface_max"]),
        ("editorOverviewRuler.border", s["border"] + "66"),
        # Focus / base UI
        ("focusBorder", s["accent"]),
        ("contrastBorder", s["border"]),
        ("foreground", s["text"]),
        ("descriptionForeground", s["text_muted"]),
        ("errorForeground", s["error"]),
        # Side bar
        ("sideBar.background", s["bg_deep"]),
        ("sideBar.foreground", s["text_muted"]),
        ("sideBar.border", s["border"]),
        ("sideBarTitle.foreground", s["text"]),
        ("sideBarSectionHeader.background", s["surface"]),
        ("sideBarSectionHeader.foreground", s["text_muted"]),
        # Activity bar
        ("activityBar.background", s["bg_deep"]),
        ("activityBar.foreground", s["text_muted"]),
        ("activityBar.border", s["border"]),
        ("activityBarBadge.background", s["accent"]),
        ("activityBarBadge.foreground", s["bg"]),
        # Status bar
        ("statusBar.background", s["surface_high"]),
        ("statusBar.foreground", s["text"]),
        ("statusBar.border", s["border"]),
        ("statusBarItem.activeBackground", s["surface_max"]),
        ("statusBarItem.hoverBackground", s["surface_max"]),
        ("statusBarItem.prominentBackground", s["accent"]),
        ("statusBarItem.prominentForeground", s["bg"]),
        ("statusBarItem.errorBackground", s["error"]),
        ("statusBarItem.errorForeground", s["bg"]),
        ("statusBarItem.warningBackground", s["warning"]),
        ("statusBarItem.warningForeground", s["bg"]),
        # Title bar
        ("titleBar.activeBackground", s["bg_deep"]),
        ("titleBar.activeForeground", s["text"]),
        ("titleBar.inactiveBackground", s["bg_deep"]),
        ("titleBar.inactiveForeground", s["text_faint"]),
        ("titleBar.border", s["border"]),
        # Tabs
        ("tab.activeBackground", s["bg"]),
        ("tab.inactiveBackground", s["bg_deep"]),
        ("tab.activeBorderTop", s["accent"]),
        ("tab.activeBorder", s["accent"]),
        ("tab.border", s["border"]),
        ("tab.activeForeground", s["text"]),
        ("tab.inactiveForeground", s["text_faint"]),
        ("editorGroupHeader.tabsBackground", s["bg_deep"]),
        ("editorGroupHeader.border", s["border"]),
        ("editorGroupHeader.tabsBorder", s["border"]),
        # Panel
        ("panel.background", s["bg_deep"]),
        ("panel.border", s["border"]),
        ("panelTitle.activeForeground", s["text_muted"]),
        ("panelTitle.activeBorder", s["accent"]),
        # Lists
        ("list.activeSelectionBackground", s["surface_high"]),
        ("list.activeSelectionForeground", s["text"]),
        ("list.inactiveSelectionBackground", s["surface"]),
        ("list.hoverBackground", s["surface"]),
        ("list.hoverForeground", s["text"]),
        ("list.errorForeground", s["error"]),
        ("list.warningForeground", s["warning"]),
        # Inputs and buttons
        ("input.background", s["surface"]),
        ("input.foreground", s["text"]),
        ("input.border", s["border"]),
        ("input.placeholderForeground", s["text_faint"]),
        ("dropdown.background", s["surface"]),
        ("dropdown.border", s["border"]),
        ("dropdown.foreground", s["text"]),
        ("button.background", s["accent"]),
        ("button.foreground", s["bg"]),
        ("button.hoverBackground", green["400"]),
        ("badge.background", s["accent"]),
        ("badge.foreground", s["bg"]),
        # Notifications / widgets
        ("notificationCenter.border", s["border"]),
        ("notifications.background", s["surface"]),
        ("notifications.foreground", s["text"]),
        ("notifications.border", s["border"]),
        ("widget.shadow", SHADOW[mode]),
        ("widget.border", s["border"]),
        ("peekViewResult.background", s["surface"]),
        ("peekView.border", s["border"]),
        ("peekViewEditor.background", s["bg"]),
        ("quickInput.background", s["surface"]),
        ("quickInput.foreground", s["text"]),
        ("menu.background", s["surface"]),
        ("menu.foreground", s["text"]),
        ("menu.selectionBackground", s["surface_high"]),
        ("menu.selectionForeground", s["text"]),
        ("menu.border", s["border"]),
        # Scrollbars and minimap
        ("scrollbarSlider.background", s["surface_max"] + "80"),
        ("scrollbarSlider.hoverBackground", s["border"] + "99"),
        ("scrollbarSlider.activeBackground", s["border"] + "cc"),
        ("minimap.background", s["bg_deep"]),
        ("breadcrumb.foreground", s["text_faint"]),
        ("breadcrumb.focusForeground", s["text"]),
        ("breadcrumb.background", s["bg"]),
        # Git decorations
        ("gitDecoration.addedResourceForeground", s["success"]),
        ("gitDecoration.modifiedResourceForeground", s["warning"]),
        ("gitDecoration.deletedResourceForeground", s["error"]),
        ("gitDecoration.untrackedResourceForeground", s["info"]),
        ("gitDecoration.conflictingResourceForeground", red["200"]),
        ("gitDecoration.ignoredResourceForeground", s["text_faint"]),
        # Diffs
        ("diffEditor.insertedTextBackground", s["success"] + "33"),
        ("diffEditor.removedTextBackground", s["error"] + "33"),
        ("diffEditor.insertedLineBackground", s["success"] + "1a"),
        ("diffEditor.removedLineBackground", s["error"] + "1a"),
        # Problems
        ("editorError.foreground", s["error"]),
        ("editorWarning.foreground", s["warning"]),
        ("editorInfo.foreground", s["info"]),
        ("editorHint.foreground", s["text_faint"]),
        # Integrated terminal
        ("terminal.background", s["bg"]),
        ("terminal.foreground", s["text"]),
        ("terminalCursor.foreground", s["accent"]),
        ("terminal.selectionBackground", s["surface_high"]),
    ]

    for name, key in ANSI_KEYS.items():
        colors.append((f"terminal.{key}", variant["ansi"][name]))

    return dict(colors)


# ---------------------------------------------------------------------------
# Token colors
# ---------------------------------------------------------------------------


def token(
    name: str, scopes: list[str] | str, foreground: str, font_style: str | None = None
) -> dict:
    settings: dict = {"foreground": foreground}
    if font_style:
        settings["fontStyle"] = font_style
    return {"name": name, "scope": scopes, "settings": settings}


def build_token_colors(mode: str, variant: dict) -> list[dict]:
    s = variant["semantic"]
    r = ramps(mode, variant)
    g, red, orange, yellow = r["gray"], r["red"], r["orange"], r["yellow"]
    green, cyan, blue, purple = r["green"], r["cyan"], r["blue"], r["purple"]

    if mode == "dark":
        palette = {
            "comment": g["400"],
            "keyword": purple["300"],
            "storage": purple["200"],
            "string": green["300"],
            "regexp": cyan["300"],
            "number": orange["300"],
            "constant": orange["200"],
            "function": blue["300"],
            "type": cyan["300"],
            "type_strong": cyan["200"],
            "variable": s["text"],
            "parameter": g["200"],
            "property": blue["200"],
            "tag": red["300"],
            "attribute": yellow["300"],
            "punctuation": g["300"],
            "operator": g["200"],
            "heading1": green["300"],
            "heading2": green["200"],
            "heading3": green["400"],
            "link": blue["300"],
            "quote": g["400"],
        }
    else:
        palette = {
            "comment": g["500"],
            "keyword": purple["400"],
            "storage": purple["500"],
            "string": green["500"],
            "regexp": cyan["400"],
            "number": orange["400"],
            "constant": orange["300"],
            "function": blue["500"],
            "type": cyan["400"],
            "type_strong": cyan["300"],
            "variable": s["text"],
            "parameter": g["500"],
            "property": blue["500"],
            "tag": red["500"],
            "attribute": orange["300"],
            "punctuation": g["500"],
            "operator": g["500"],
            "heading1": green["300"],
            "heading2": green["400"],
            "heading3": green["500"],
            "link": blue["500"],
            "quote": g["500"],
        }

    p = palette
    return [
        token(
            "Comment",
            ["comment", "punctuation.definition.comment", "string.comment"],
            p["comment"],
            "italic",
        ),
        token(
            "Keyword",
            ["keyword", "keyword.control", "keyword.other"],
            p["keyword"],
        ),
        token(
            "Storage",
            ["storage", "storage.type", "storage.modifier"],
            p["storage"],
        ),
        token(
            "String",
            [
                "string",
                "string.quoted",
                "string.template",
                "punctuation.definition.string",
            ],
            p["string"],
        ),
        token("Regular expression", ["string.regexp", "constant.regexp"], p["regexp"]),
        token("Number", ["constant.numeric"], p["number"]),
        token(
            "Constant",
            ["constant", "constant.language", "support.constant"],
            p["constant"],
        ),
        token(
            "Function",
            ["entity.name.function", "support.function"],
            p["function"],
        ),
        token(
            "Method",
            ["entity.name.function.member", "support.function.member"],
            p["function"],
        ),
        token(
            "Class",
            ["entity.name.class", "entity.name.type.class"],
            p["type_strong"],
        ),
        token(
            "Type",
            ["entity.name.type", "support.type", "support.class"],
            p["type"],
        ),
        token(
            "Interface",
            ["entity.name.type.interface", "entity.name.interface"],
            p["type_strong"],
        ),
        token(
            "Enum",
            ["entity.name.type.enum", "entity.name.enum"],
            p["type_strong"],
        ),
        token(
            "Variable",
            ["variable", "variable.other", "variable.other.readwrite"],
            p["variable"],
        ),
        token("Parameter", ["variable.parameter"], p["parameter"]),
        token(
            "Property",
            [
                "variable.other.property",
                "support.variable.property",
                "meta.object-literal.key",
            ],
            p["property"],
        ),
        token("Tag", ["entity.name.tag"], p["tag"]),
        token("Attribute", ["entity.other.attribute-name"], p["attribute"]),
        token(
            "Punctuation",
            ["punctuation", "punctuation.separator", "punctuation.terminator"],
            p["punctuation"],
        ),
        token("Operator", ["keyword.operator"], p["operator"]),
        token(
            "Invalid",
            ["invalid", "invalid.illegal"],
            s["error"],
            "bold",
        ),
        token(
            "Markup Heading 1",
            ["markup.heading.1", "markup.heading.1.markdown", "heading.1.markdown"],
            p["heading1"],
            "bold",
        ),
        token(
            "Markup Heading 2",
            ["markup.heading.2", "markup.heading.2.markdown", "heading.2.markdown"],
            p["heading2"],
            "bold",
        ),
        token(
            "Markup Heading 3",
            ["markup.heading.3", "markup.heading.3.markdown", "heading.3.markdown"],
            p["heading3"],
            "bold",
        ),
        token("Markup Heading", ["markup.heading"], s["accent"], "bold"),
        token("Markup Bold", ["markup.bold"], s["text"], "bold"),
        token("Markup Italic", ["markup.italic"], p["comment"], "italic"),
        token(
            "Markup Inline Code",
            ["markup.inlineCode", "markup.inline.code"],
            p["string"],
        ),
        token(
            "Markup Link",
            ["markup.link", "string.other.link"],
            p["link"],
        ),
        token("Markup Quote", ["markup.quote"], p["quote"]),
        token(
            "Markup List",
            ["markup.list", "punctuation.definition.list"],
            s["accent"],
        ),
    ]


def build_theme(mode: str, variant: dict) -> dict:
    meta = THEMES[mode]
    return {
        "$schema": SCHEMA,
        "name": meta["name"],
        "type": meta["type"],
        "semanticHighlighting": True,
        "colors": build_colors(mode, variant),
        "tokenColors": build_token_colors(mode, variant),
    }


def render(theme: dict) -> str:
    return json.dumps(theme, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# preview/palette-*.svg
# ---------------------------------------------------------------------------

PREVIEW_WIDTH = 760
PREVIEW_PAD = 28
PREVIEW_ROW_H = 40
PREVIEW_SWATCH_W = 48
PREVIEW_SWATCH_H = 24
PREVIEW_COL_GAP = 24


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_palette_svg(mode: str, variant: dict) -> str:
    """Render semantic tokens and ANSI 0-15 as a pure SVG swatch sheet."""
    sem = variant["semantic"]
    ansi = variant["ansi"]
    page_bg = sem["bg"]
    text = sem["text"]
    muted = sem["text_muted"]
    border = sem["border"]
    accent = sem["accent"]

    col_w = (PREVIEW_WIDTH - 2 * PREVIEW_PAD - PREVIEW_COL_GAP) // 2
    title_y = PREVIEW_PAD + 20
    subtitle_y = PREVIEW_PAD + 42
    semantic_label_y = PREVIEW_PAD + 76
    semantic_top = PREVIEW_PAD + 88
    ansi_label_y = semantic_top + 8 * PREVIEW_ROW_H + 26
    ansi_top = ansi_label_y + 12
    height = ansi_top + 8 * PREVIEW_ROW_H + PREVIEW_PAD
    label = "Dark" if mode == "dark" else "Light"

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PREVIEW_WIDTH}" '
        f'height="{height}" viewBox="0 0 {PREVIEW_WIDTH} {height}" '
        f'role="img" font-family="ui-monospace, monospace">',
        f"  <title>42vibes palette preview ({label})</title>",
        f'  <rect width="{PREVIEW_WIDTH}" height="{height}" fill="{page_bg}"/>',
        f'  <text x="{PREVIEW_PAD}" y="{title_y}" fill="{accent}" font-size="22" '
        f'font-weight="bold" font-family="ui-monospace, monospace">'
        f"42vibes · {label}</text>",
        f'  <text x="{PREVIEW_PAD}" y="{subtitle_y}" fill="{muted}" font-size="13" '
        f'font-family="ui-monospace, monospace">Semantische Tokens und ANSI 0–15, '
        f"generiert aus vendor/palette.json</text>",
        f'  <line x1="{PREVIEW_PAD}" y1="{subtitle_y + 12}" '
        f'x2="{PREVIEW_WIDTH - PREVIEW_PAD}" y2="{subtitle_y + 12}" '
        f'stroke="{border}" stroke-width="1"/>',
        f'  <text x="{PREVIEW_PAD}" y="{semantic_label_y}" fill="{muted}" '
        f'font-size="12" letter-spacing="1.5" '
        f'font-family="ui-monospace, monospace">SEMANTIC</text>',
    ]

    def add_rows(items: list[tuple[str, str]], top: int) -> None:
        for index, (name, value) in enumerate(items):
            column, row = divmod(index, 8)
            x = PREVIEW_PAD + column * (col_w + PREVIEW_COL_GAP)
            y = top + row * PREVIEW_ROW_H
            swatch_y = y + (PREVIEW_ROW_H - PREVIEW_SWATCH_H) // 2
            baseline = y + PREVIEW_ROW_H // 2 + 4
            text_x = x + PREVIEW_SWATCH_W + 12
            hex_x = x + col_w - 4
            out.extend(
                [
                    f'  <rect x="{x}" y="{swatch_y}" width="{PREVIEW_SWATCH_W}" '
                    f'height="{PREVIEW_SWATCH_H}" rx="4" fill="{value}" '
                    f'stroke="{border}" stroke-width="1"/>',
                    f'  <text x="{text_x}" y="{baseline}" fill="{text}" '
                    f'font-size="13" font-family="ui-monospace, monospace">'
                    f"{xml_escape(name)}</text>",
                    f'  <text x="{hex_x}" y="{baseline}" fill="{muted}" '
                    f'font-size="12" text-anchor="end" '
                    f'font-family="ui-monospace, monospace">{value}</text>',
                ]
            )

    add_rows([(key, sem[key]) for key in SEMANTIC_KEYS], semantic_top)
    out.append(
        f'  <text x="{PREVIEW_PAD}" y="{ansi_label_y}" fill="{muted}" '
        f'font-size="12" letter-spacing="1.5" '
        f'font-family="ui-monospace, monospace">ANSI 0–15</text>'
    )
    add_rows(
        [
            (f"{index} {name}", ansi[name])
            for index, name in enumerate(ANSI_KEYS)
        ],
        ansi_top,
    )
    out.append("</svg>")
    return "\n".join(out)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def render_palette_png(svg: str) -> bytes | None:
    """Rasterise the palette SVG to PNG with ImageMagick, or None if absent."""
    tool = shutil.which("convert") or shutil.which("magick")
    if tool is None:
        return None
    result = subprocess.run(
        [tool, "svg:-", "-strip", "png:-"],
        input=svg.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(f"ImageMagick failed to render palette PNG: {message}")
    if not result.stdout.startswith(PNG_SIGNATURE):
        raise SystemExit("ImageMagick did not return a PNG image")
    return result.stdout


# ---------------------------------------------------------------------------
# README palette block
# ---------------------------------------------------------------------------


def build_palette_block(palette: dict, lang: str) -> str:
    dark = palette["dark"]
    light = palette["light"]
    if lang == "en":
        intro = [
            "## Palette preview",
            "",
            "The following images and tables are generated by `build.py` from",
            "`vendor/palette.json`: generated preview, not a screenshot.",
            "Please do not edit them by hand.",
            "",
            "**Dark**",
            "",
            "![Generated palette preview Dark: semantic tokens and ANSI 0–15]"
            "(preview/palette-dark.png)",
            "",
            "**Light**",
            "",
            "![Generated palette preview Light: semantic tokens and ANSI 0–15]"
            "(preview/palette-light.png)",
            "",
            "### Semantic tokens (dark/light)",
            "",
            "| Token | Dark | Light |",
            "| --- | --- | --- |",
        ]
        ansi_heading = "### ANSI 0–15 (dark/light)"
    else:
        intro = [
            "## Palettenvorschau",
            "",
            "Die folgenden Bilder und Tabellen werden von `build.py` aus",
            "`vendor/palette.json` erzeugt: generierte Vorschau, kein Screenshot.",
            "Bitte nicht von Hand bearbeiten.",
            "",
            "**Dark**",
            "",
            "![Generierte Palettenvorschau Dark: semantische Tokens und ANSI 0–15]"
            "(preview/palette-dark.png)",
            "",
            "**Light**",
            "",
            "![Generierte Palettenvorschau Light: semantische Tokens und ANSI 0–15]"
            "(preview/palette-light.png)",
            "",
            "### Semantische Tokens (Dark/Light)",
            "",
            "| Token | Dark | Light |",
            "| --- | --- | --- |",
        ]
        ansi_heading = "### ANSI 0–15 (Dark/Light)"
    lines = [PALETTE_START, *intro]
    for key in SEMANTIC_KEYS:
        lines.append(
            f"| `{key}` | `{dark['semantic'][key]}` | `{light['semantic'][key]}` |"
        )
    lines += [
        "",
        ansi_heading,
        "",
        "| Slot | Dark | Light |",
        "| --- | --- | --- |",
    ]
    for index, name in enumerate(ANSI_KEYS):
        lines.append(
            f"| {index} {name} | `{dark['ansi'][name]}` | `{light['ansi'][name]}` |"
        )
    lines.append(PALETTE_END)
    return "\n".join(lines)


def render_readme(palette: dict, lang: str) -> str:
    path = README_FILES[lang]
    text = path.read_text(encoding="utf-8")
    start = text.find(PALETTE_START)
    end = text.find(PALETTE_END)
    if start == -1 or end == -1 or end < start:
        raise SystemExit(
            f"{path.name}: Marker <!-- palette:start -->/<!-- palette:end --> fehlen"
        )
    end += len(PALETTE_END)
    return text[:start] + build_palette_block(palette, lang) + text[end:]


def build_artifacts(palette: dict) -> tuple[list[tuple[Path, bytes]], list[str]]:
    artifacts: list[tuple[Path, bytes]] = []
    png_skipped: list[str] = []
    for mode, meta in THEMES.items():
        if mode not in palette:
            raise SystemExit(f"palette has no '{mode}' variant")
        artifacts.append(
            (meta["path"], render(build_theme(mode, palette[mode])).encode("utf-8"))
        )
        svg = render_palette_svg(mode, palette[mode])
        artifacts.append((PREVIEW_FILES[mode], svg.encode("utf-8")))
        png = render_palette_png(svg)
        if png is None:
            png_skipped.append(mode)
        else:
            artifacts.append((PREVIEW_PNG_FILES[mode], png))
    for lang in README_FILES:
        artifacts.append(
            (README_FILES[lang], render_readme(palette, lang).encode("utf-8"))
        )
    return artifacts, png_skipped


def main() -> int:
    check = "--check" in sys.argv[1:]
    palette = json.loads(PALETTE_FILE.read_text(encoding="utf-8"))
    artifacts, png_skipped = build_artifacts(palette)

    if png_skipped:
        print(
            "warning: ImageMagick (convert/magick) not found; checked-in PNG "
            "previews are used unchanged",
            file=sys.stderr,
        )

    if check:
        stale = [
            path.relative_to(ROOT)
            for path, content in artifacts
            if not path.exists() or path.read_bytes() != content
        ]
        stale.extend(
            PREVIEW_PNG_FILES[mode].relative_to(ROOT)
            for mode in png_skipped
            if not PREVIEW_PNG_FILES[mode].exists()
        )
        if stale:
            for path in stale:
                print(f"stale: {path}", file=sys.stderr)
            print(
                "Generated files are out of date; run `python3 build.py`.",
                file=sys.stderr,
            )
            return 1
        print("themes, previews (SVG/PNG) and README block are up to date")
        return 0

    for path, content in artifacts:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
