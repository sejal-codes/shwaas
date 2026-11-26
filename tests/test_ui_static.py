"""Static checks on the web UI: translations, accessibility basics, security rules, colour contrast."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.activity import MaskLevel
from app.aqi import Severity
from app.explain import FIX_TEXT
from app.models import ActivityKind, CookingFuel, Heating, TravelMode, WindowHabit

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
STRINGS = json.loads((STATIC / "i18n.json").read_text(encoding="utf-8"))
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")


# ------------------------------------------------------------------- translations
def test_english_and_hindi_have_identical_keys():
    assert set(STRINGS["en"]) == set(STRINGS["hi"])


def test_no_translation_is_blank_except_the_english_language_note():
    for lang, table in STRINGS.items():
        blanks = {k for k, v in table.items() if not v.strip()}
        assert blanks <= {"tips.lang_note"} if lang == "en" else not blanks


def test_placeholders_match_between_languages():
    token = re.compile(r"\{(\w+)\}")
    for key, en in STRINGS["en"].items():
        assert set(token.findall(en)) == set(token.findall(STRINGS["hi"][key])), key


def _codes():
    yield from (f"severity.{s.value}" for s in Severity)
    yield from (f"fix.{c}" for c in FIX_TEXT)
    yield from (f"mode.{m.value}" for m in TravelMode)
    yield from (f"kind.{k.value}" for k in ActivityKind)
    yield from (f"mask.{m.value}" for m in MaskLevel)
    yield from (f"windows.{w.value}" for w in WindowHabit)
    yield from (f"cooking.{c.value}" for c in CookingFuel)
    yield from (f"heating.{h.value}" for h in Heating)
    yield from (f"factor.windows_{w.value}" for w in WindowHabit)
    yield from (f"factor.cooking_{c.value}" for c in CookingFuel)
    yield from (f"factor.heating_{h.value}" for h in Heating)
    yield from ("factor.incense", "factor.indoor_smoking", "factor.purifier")
    yield from ("explain.gemini", "explain.template", "purifier.yes", "purifier.no")


@pytest.mark.parametrize("key", sorted(set(_codes())))
def test_every_backend_code_has_a_label_in_both_languages(key):
    assert key in STRINGS["en"] and key in STRINGS["hi"]


def test_every_key_used_in_html_and_js_exists():
    used = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', HTML))
    for js in STATIC.glob("*.js"):
        used |= set(re.findall(r'\bt\("([a-z0-9_.]+)"', js.read_text(encoding="utf-8")))
        used |= set(re.findall(
            r'"((?:q|error|travel|tips|mask|chat|map|location|globe|short|quick|purifier|env)\.[a-z_.]+)"', js.read_text(encoding="utf-8")
        ))
    assert used - set(STRINGS["en"]) == set()


def test_hindi_strings_are_actually_hindi():
    devanagari = re.compile(r"[\u0900-\u097F]")
    latin_ok = {"lang.other", "outdoor.aqi", "gauge.label", "travel.co2", "time.better", "explain.gemini"}
    for key, value in STRINGS["hi"].items():
        if key not in latin_ok and key != "tips.lang_note" and not key.startswith("mode."):
            assert devanagari.search(value), key


# ------------------------------------------------------------------ html structure
class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.ids, self.labels_for, self.fieldsets = [], [], set(), []
        self.controls, self.buttons, self.inline_handlers, self.inline_styles = [], [], [], []
        self.inline_scripts, self._label_depth, self._in_fieldset = 0, 0, 0
        self.html_attrs, self.meta = {}, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.html_attrs = a
        if tag == "meta":
            self.meta.append(a)
        if tag == "label":
            self._label_depth += 1
            if "for" in a:
                self.labels_for.add(a["for"])
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden":
            self.controls.append((tag, a, self._label_depth > 0))
        if tag == "button":
            self.buttons.append(a)
        if tag == "script" and "src" not in a:
            self.inline_scripts += 1
        if "style" in a:
            self.inline_styles.append(tag)
        self.inline_handlers += [k for k in a if k.startswith("on")]

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth -= 1


PAGE = _Page()
PAGE.feed(HTML)


def test_page_basics():
    assert PAGE.html_attrs.get("lang") == "en"
    assert any(m.get("name") == "viewport" for m in PAGE.meta)
    assert PAGE.tags.count("h1") == 1 and "title" in PAGE.tags


def test_skip_link_target_exists():
    assert re.search(r'href="#main"', HTML) and "main" in PAGE.ids


def test_ids_are_unique():
    assert len(PAGE.ids) == len(set(PAGE.ids))


def test_every_form_control_has_a_label():
    for tag, attrs, wrapped in PAGE.controls:
        assert wrapped or attrs.get("id") in PAGE.labels_for or "aria-label" in attrs, attrs


def test_every_button_declares_its_type():
    assert all("type" in b for b in PAGE.buttons)


def test_radio_groups_are_in_fieldsets_with_legends():
    assert HTML.count("<fieldset") == HTML.count("</fieldset>") == HTML.count("<legend")


def test_no_inline_scripts_styles_or_handlers():
    assert PAGE.inline_scripts == 0 and PAGE.inline_styles == [] and PAGE.inline_handlers == []


def test_no_third_party_resources():
    assert not re.search(r'(?:src|href)="https?://', HTML)
    assert "http" not in CSS.replace("http-equiv", "")


def test_js_never_writes_html():
    for js in STATIC.glob("*.js"):
        source = js.read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", source), js.name
        assert not re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie", source), js.name


def test_reduced_motion_is_respected():
    assert "prefers-reduced-motion: reduce" in CSS


# ---------------------------------------------------------------- colour contrast
def _luminance(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ratio(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


DARK = _tokens(re.search(r":root\s*{(.*?)}", CSS, re.S).group(1))
LIGHT = _tokens(re.search(r"prefers-color-scheme: light\)\s*{\s*:root\s*{(.*?)}", CSS, re.S).group(1))
TEXT_PAIRS = [
    ("text", "bg"), ("text", "surface"), ("text", "surface-2"), ("muted", "bg"), ("muted", "surface"),
    ("muted", "surface-2"), ("accent", "surface"), ("accent", "surface-2"), ("on-accent", "accent"),
    ("on-accent", "accent-2"), ("focus", "bg"), ("focus", "surface"),
]
UI_PAIRS = [("control-border", "surface"), ("control-border", "surface-2"), ("control-border", "bg")]


@pytest.mark.parametrize("name, tokens", [("dark", DARK), ("light", LIGHT)])
def test_text_contrast_meets_wcag_aa(name, tokens):
    for fg, bg in TEXT_PAIRS:
        assert _ratio(tokens[fg], tokens[bg]) >= 4.5, f"{name}: {fg} on {bg}"


@pytest.mark.parametrize("name, tokens", [("dark", DARK), ("light", LIGHT)])
def test_control_borders_and_severity_colours_are_visible(name, tokens):
    for fg, bg in UI_PAIRS:
        assert _ratio(tokens[fg], tokens[bg]) >= 3.0, f"{name}: {fg} on {bg}"
    for sev in ("good", "satisfactory", "moderate", "poor", "very-poor", "severe"):
        assert _ratio(tokens[f"sev-{sev}"], tokens["surface-2"]) >= 3.0, f"{name}: sev-{sev}"


# ---------------------------------------------------------------- size guard
def test_the_whole_app_stays_well_under_the_10mb_repository_limit():
    root = STATIC.parent.parent
    total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and "node_modules" not in f.parts)
    assert total < 6 * 1024 * 1024, f"project is {total / 1024 / 1024:.1f} MB"


def test_every_country_has_a_map_file():
    world = json.loads((STATIC / "geo" / "world.json").read_text(encoding="utf-8"))
    geometries = next(iter(world["objects"].values()))["geometries"]
    codes = {g["properties"]["a"] for g in geometries}
    files = {p.stem for p in (STATIC / "geo" / "states").glob("*.json")}
    assert len(codes) == 242 and codes == files
