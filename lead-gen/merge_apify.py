#!/usr/bin/env python3
"""
Merge Apify Google Maps results into the MIBK lead list.

The Google Maps Scraper (compass/crawler-google-places) returns verified
switchboard phones, addresses and websites for each company. This script folds
that into data/mibk_leads_brazil.json, matching on company name.

Only fields that came back from Apify are written, and each one is stamped with
its source so a reviewer can tell verified data from an estimate.

    python merge_apify.py apify_results.json
    python enrich.py --no-crawl        # regenerate the xlsx
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "mibk_leads_brazil.json"

# Google Maps names a place its own way; map the awkward ones to our list.
ALIASES = {
    "empresas artecola": "Artecola Química",
    "brenntag química brasil ltda.": "Brenntag Brasil",
    "química anastacio": "Química Anastácio",
    "renner sayerlack": "Renner Sayerlack (Sherwin-Williams)",
    "cbmm": "CBMM - Companhia Brasileira de Metalurgia e Mineração",
    "suvinil": "BASF Coatings / Suvinil",
    "clariant": "Clariant Mining Solutions Brasil",
    "akzo nobel unidade maua": "AkzoNobel Brasil (Coral)",
    "ourofino agrociencia": "Ouro Fino Química",
    "basf s a": "BASF Coatings / Suvinil",
    "indorama ventures indovinya": "Oxiteno (Indorama Ventures)",
    "tintas killing tintas e adesivos s a": "Killing S/A Tintas e Adesivos",
    "fabrica michelin cgr": "Michelin Brasil",
}

STOPWORDS = {
    "do", "da", "de", "brasil", "brazil", "ltda", "sa", "s", "a", "industria",
    "comercio", "e", "the", "inc", "group", "empresas",
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    # Collapse the runs of spaces left behind by stripped punctuation, so an
    # alias key like "akzo nobel unidade maua" actually matches.
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if t and t not in STOPWORDS}


def match(place_title: str, leads: list[dict]) -> dict | None:
    key = norm(place_title)
    if key in ALIASES:
        target = ALIASES[key]
        for lead in leads:
            if lead["company"] == target:
                return lead

    pt = tokens(place_title)
    if not pt:
        return None
    best, best_score = None, 0.0
    for lead in leads:
        lt = tokens(lead["company"])
        if not lt:
            continue
        overlap = len(pt & lt)
        if not overlap:
            continue
        score = overlap / min(len(pt), len(lt))
        if score > best_score:
            best, best_score = lead, score
    # Require a decisive overlap; a single shared generic token is not a match.
    return best if best_score >= 0.5 else None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    leads = payload["leads"]
    places = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if isinstance(places, dict):
        places = places.get("items", [])

    matched, unmatched = 0, []
    for place in places:
        title = place.get("title") or ""
        lead = match(title, leads)
        if not lead:
            unmatched.append(title)
            continue
        matched += 1

        phone = place.get("phone") or ""
        if phone:
            lead["phone"] = phone
            lead["phone_source"] = "Google Maps (verified)"
        city = place.get("city") or ""
        state = place.get("state") or ""
        if city:
            new_city = f"{city}, {state}" if state else city
            if norm(new_city) != norm(lead.get("city", "")):
                lead["city_previous_estimate"] = lead.get("city", "")
            lead["city"] = new_city
            lead["city_source"] = "Google Maps (verified)"
        if place.get("website"):
            lead["website"] = re.sub(r"^https?://(www\.)?", "", place["website"]).rstrip("/")
        emails = [e for e in (place.get("emails") or []) if e]
        if emails:
            lead["emails_found"] = emails
            lead["email_source"] = "Company website via Google Maps enrichment"
        if place.get("address"):
            lead["address"] = place["address"]

        # Personal-level records, when the leads database has any.
        enrich = place.get("leadsEnrichment")
        if isinstance(enrich, dict):
            enrich = [enrich]
        for rec in enrich or []:
            if not isinstance(rec, dict) or not rec.get("fullName"):
                continue
            lead.setdefault("people", []).append({
                "name": rec.get("fullName", ""),
                "title": rec.get("jobTitle", ""),
                "email": rec.get("email", ""),
                "mobile": rec.get("mobileNumber", ""),
                "linkedin": rec.get("linkedinProfile", ""),
            })

    DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"matched {matched}/{len(places)} places into {len(leads)} leads")
    if unmatched:
        print("unmatched place titles:")
        for t in unmatched:
            print(f"  - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
