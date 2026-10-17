"""Validate an Alexa+ add-on manifest (`addon.json`) against the documented shape.

The shape and limits are the ones the MCP toolkit quickstart documents
(read 2026-10-05): `manifestVersion`, `storeListing.distributionCountries`,
per-locale `name` (<= 30), `shortDescription` (<= 123), `fullDescription`
(<= 4000), 3-4 `examplePhrases` (<= 200 each), privacy policy and terms URLs,
six light icon sizes, at least one 600x900 carousel image, and an `MCP`
integration with an HTTPS endpoint. The functional requirements add: at least 3
*distinct* phrases and no developer jargon in customer-facing text.

What the docs do not state is not enforced: the dark icon set, banner images
and the `spokenForm` contents are reported, never failed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from . import (
    ALEXA_ALT_TEXT_MAX, ALEXA_CAROUSEL_SIZE, ALEXA_COUNTRIES_AVAILABLE, ALEXA_EXAMPLE_PHRASE_MAX,
    ALEXA_EXAMPLE_PHRASES, ALEXA_FULL_DESCRIPTION_MAX, ALEXA_ICON_SIZES, ALEXA_MEDIA_EXTENSIONS,
    ALEXA_NAME_MAX, ALEXA_SHORT_DESCRIPTION_MAX,
)
from .report import GapReport

LOCALE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")
#: Words that read as developer jargon in a store listing. Tool names are added per project.
JARGON = re.compile(r"\b(JSON|API|endpoint|MCP|tool[_ ]?call|schema|payload|JSON-RPC|OAuth|token|"
                    r"[a-z]+_[a-z_]+)\b")


def _https(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def load(path: Path) -> tuple[dict | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, str(exc)
    except json.JSONDecodeError as exc:
        return None, f"line {exc.lineno} column {exc.colno}: {exc.msg}"


def endpoints(doc: dict) -> list[str]:
    out = []
    for integration in doc.get("integrations") or []:
        if not isinstance(integration, dict) or integration.get("type") != "MCP":
            continue
        for endpoint in ((integration.get("config") or {}).get("endpoints") or {}).values():
            if isinstance(endpoint, dict) and endpoint.get("uri"):
                out.append(endpoint["uri"])
    return out


def validate(doc: dict, report: GapReport, path: str, *, tool_names: tuple[str, ...] = ()) -> dict:
    """Check `doc`; add `ALX0xx` findings; return a summary for the report's Found block."""
    summary: dict = {"locales": [], "countries": [], "endpoints": endpoints(doc)}
    if str(doc.get("manifestVersion")) != "1.0":
        report.add("ALX003", f"manifestVersion is {doc.get('manifestVersion')!r}", path=path,
                   locator="manifestVersion")
    listing = doc.get("storeListing") or {}
    countries = listing.get("distributionCountries")
    if not isinstance(countries, list) or not countries:
        report.add("ALX010", "storeListing.distributionCountries is missing or empty", path=path,
                   locator="storeListing.distributionCountries")
    else:
        summary["countries"] = countries
        for country in countries:
            if country not in ALEXA_COUNTRIES_AVAILABLE:
                report.add("ALX011", f"{country!r} is listed; the MCP toolkit is documented as available in "
                           f"{', '.join(ALEXA_COUNTRIES_AVAILABLE)}", path=path,
                           locator="storeListing.distributionCountries")
    locales = listing.get("locales")
    if not isinstance(locales, dict) or not locales:
        report.add("ALX012", "storeListing.locales is missing or empty", path=path, locator="storeListing.locales")
        locales = {}
    jargon_words = set(tool_names)
    for tag, entry in locales.items():
        where = f"storeListing.locales.{tag}"
        summary["locales"].append(tag)
        if not LOCALE.match(tag):
            report.add("ALX012", f"locale key {tag!r} is not of the form ll-CC", path=path, locator=where)
        if not isinstance(entry, dict):
            report.add("ALX012", f"locale {tag} is not an object", path=path, locator=where)
            continue
        name = (entry.get("name") or {}).get("value") if isinstance(entry.get("name"), dict) else entry.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > ALEXA_NAME_MAX:
            report.add("ALX013", f"name is {name!r}" + (f" ({len(name)} chars)" if isinstance(name, str) else ""),
                       path=path, locator=f"{where}.name.value")
        for key, limit, fid in (("shortDescription", ALEXA_SHORT_DESCRIPTION_MAX, "ALX014"),
                                ("fullDescription", ALEXA_FULL_DESCRIPTION_MAX, "ALX015")):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                size = f" ({len(value)} chars, limit {limit})" if isinstance(value, str) and value else ""
                report.add(fid, f"{key} is {'missing' if not value else 'too long'}{size}", path=path,
                           locator=f"{where}.{key}")
        phrases = entry.get("examplePhrases")
        low, high = ALEXA_EXAMPLE_PHRASES
        if not isinstance(phrases, list):
            report.add("ALX016", "examplePhrases is missing", path=path, locator=f"{where}.examplePhrases")
            phrases = []
        else:
            distinct = {p.strip().lower() for p in phrases if isinstance(p, str) and p.strip()}
            if len(distinct) < low or len(phrases) > high:
                report.add("ALX016", f"{len(phrases)} phrase(s), {len(distinct)} distinct; need {low}-{high}",
                           path=path, locator=f"{where}.examplePhrases")
            for i, phrase in enumerate(phrases):
                if not isinstance(phrase, str) or len(phrase) > ALEXA_EXAMPLE_PHRASE_MAX:
                    report.add("ALX016", f"phrase {i + 1} is longer than {ALEXA_EXAMPLE_PHRASE_MAX} characters",
                               path=path, locator=f"{where}.examplePhrases[{i}]")
        privacy = entry.get("privacyAndCompliance") or {}
        for key in ("privacyPolicyUrl", "termsOfUseUrl"):
            if not _https(privacy.get(key)):
                report.add("ALX017", f"{key} is {privacy.get(key)!r}", path=path,
                           locator=f"{where}.privacyAndCompliance.{key}")
        media = entry.get("mediaAssets") or {}
        icons = (media.get("icons") or {}).get("light") or []
        sizes = {i.get("size") for i in icons if isinstance(i, dict)}
        missing = [s for s in ALEXA_ICON_SIZES if s not in sizes]
        if missing:
            report.add("ALX018", f"missing light icon size(s): {', '.join(missing)}", path=path,
                       locator=f"{where}.mediaAssets.icons.light")
        for i, icon in enumerate(icons):
            _media_uri(report, path, f"{where}.mediaAssets.icons.light[{i}]", icon)
        carousel = media.get("carouselImages") or []
        if not carousel:
            report.add("ALX019", "no carouselImages", path=path, locator=f"{where}.mediaAssets.carouselImages")
        for i, image in enumerate(carousel):
            loc = f"{where}.mediaAssets.carouselImages[{i}]"
            _media_uri(report, path, loc, image)
            if isinstance(image, dict):
                if image.get("size") != ALEXA_CAROUSEL_SIZE:
                    report.add("ALX019", f"carousel size {image.get('size')!r}, expected {ALEXA_CAROUSEL_SIZE}",
                               path=path, locator=loc)
                alt = image.get("altText")
                if not isinstance(alt, str) or not alt.strip() or len(alt) > ALEXA_ALT_TEXT_MAX:
                    report.add("ALX019", "altText missing or longer than 250 characters", path=path, locator=loc)
        customer_text = " ".join(str(x) for x in [name, entry.get("shortDescription"),
                                                   entry.get("fullDescription"), *phrases] if x)
        hits = sorted({m.group(0) for m in JARGON.finditer(customer_text)} |
                      {t for t in jargon_words if t and t in customer_text})
        if hits:
            report.add("ALX022", f"customer-facing text mentions {', '.join(hits[:6])}", path=path, locator=where)
    eps = summary["endpoints"]
    if not eps or not all(_https(e) for e in eps):
        report.add("ALX020", f"MCP endpoint(s): {eps or 'none'}", path=path, locator="integrations")
    return summary


def _media_uri(report: GapReport, path: str, loc: str, item: object) -> None:
    uri = item.get("uri") if isinstance(item, dict) else None
    if not _https(uri):
        report.add("ALX019", f"media uri {uri!r} is not HTTPS", path=path, locator=loc)
        return
    suffix = Path(urlparse(uri).path).suffix.lower()
    if suffix and suffix not in ALEXA_MEDIA_EXTENSIONS:
        report.add("ALX019", f"media format {suffix} is not PNG/JPG/JPEG/WEBP", path=path, locator=loc)
