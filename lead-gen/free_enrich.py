#!/usr/bin/env python3
"""
Free, no-paid-API contact enrichment for the MIBK lead list.

Replaces the paid Apify step with three free sources, cheapest-signal first:

  1. Receita Federal CNPJ open data, via BrasilAPI or OpenCNPJ (free public
     APIs, no key). Every registered Brazilian company files a phone and an
     email with the Receita. This is official data, not scraping, and it is
     the single best free source for this market.
  2. gosom/google-maps-scraper output (free, self-hosted Go binary) - ingest
     its CSV/JSON with --gmaps.
  3. The company's own website, via enrich.py's Crawl4AI pass.

Usage
-----
    python free_enrich.py --cnpj              # query the CNPJ APIs
    python free_enrich.py --gmaps results.csv # ingest google-maps-scraper
    python enrich.py --no-crawl               # rebuild the xlsx

Needs real outbound internet. Field names differ slightly between the two
CNPJ APIs and across versions, so lookups read several key spellings and skip
anything they cannot find rather than guessing.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "mibk_leads_brazil.json"

BRASILAPI = "https://brasilapi.com.br/api/v1/cnpj/v1/{cnpj}"
OPENCNPJ = "https://api.opencnpj.org/{cnpj}"

UA = "mibk-lead-gen/1.0 (+contact enrichment for HSN 29141300)"

# The APIs disagree on field names; try each spelling in order.
PHONE_KEYS = ("ddd_telefone_1", "ddd_telefone_2", "telefone", "telefones", "phone")
EMAIL_KEYS = ("email", "correio_eletronico", "e_mail")
CITY_KEYS = ("municipio", "cidade", "city")
STATE_KEYS = ("uf", "estado", "state")


def digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def first_value(payload: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        val = payload.get(key)
        if isinstance(val, list):
            val = val[0] if val else ""
        if isinstance(val, dict):
            val = val.get("numero") or val.get("number") or ""
        if val and str(val).strip():
            return str(val).strip()
    return ""


def fetch_json(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        print(f"    ! HTTP {exc.code} for {url}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - one bad lookup must not kill the run
        print(f"    ! {type(exc).__name__} for {url}", file=sys.stderr)
    return None


def lookup_cnpj(cnpj: str) -> dict | None:
    """Try BrasilAPI, then OpenCNPJ. Both are free and need no key."""
    num = digits(cnpj)
    if len(num) != 14:
        return None
    for template in (BRASILAPI, OPENCNPJ):
        data = fetch_json(template.format(cnpj=num))
        if data:
            data["_source"] = "BrasilAPI" if template is BRASILAPI else "OpenCNPJ"
            return data
        time.sleep(0.4)  # be polite to a free public service
    return None


def enrich_from_cnpj(leads: list[dict]) -> int:
    hits = 0
    targets = [l for l in leads if l.get("cnpj")]
    if not targets:
        print("No leads carry a 'cnpj' field yet - add them to data/mibk_leads_brazil.json.")
        print("Look one up by company name at https://opencnpj.org or consultacnpj.com.")
        return 0

    for lead in targets:
        print(f"  -> {lead['company']}")
        rec = lookup_cnpj(lead["cnpj"])
        if not rec:
            continue
        phone = first_value(rec, PHONE_KEYS)
        email = first_value(rec, EMAIL_KEYS)
        city = first_value(rec, CITY_KEYS)
        state = first_value(rec, STATE_KEYS)
        src = rec.get("_source", "CNPJ API")

        if phone and not lead.get("phone"):
            lead["phone"] = phone
            lead["phone_source"] = f"Receita Federal via {src}"
        if email:
            found = lead.setdefault("emails_found", [])
            if email not in found:
                found.append(email)
            lead["email_source"] = f"Receita Federal via {src}"
        if city:
            lead["city"] = f"{city.title()}, {state.upper()}" if state else city.title()
            lead["city_source"] = f"Receita Federal via {src}"
        hits += 1
        time.sleep(0.4)
    return hits


def enrich_from_gmaps(leads: list[dict], path: Path) -> int:
    """Ingest gosom/google-maps-scraper or omkarcloud output (CSV or JSON)."""
    from merge_apify import match  # reuse the name matcher

    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("items", rows.get("results", []))
    else:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))

    hits = 0
    for row in rows:
        title = row.get("title") or row.get("name") or row.get("Name") or ""
        lead = match(title, leads)
        if not lead:
            continue
        phone = row.get("phone") or row.get("Phone") or ""
        email = row.get("email") or row.get("Email") or ""
        website = row.get("website") or row.get("Website") or ""
        if phone and not lead.get("phone"):
            lead["phone"] = phone
            lead["phone_source"] = "Google Maps via gosom/google-maps-scraper"
        if email:
            found = lead.setdefault("emails_found", [])
            for e in re.split(r"[;,\s]+", email):
                if "@" in e and e not in found:
                    found.append(e)
            lead["email_source"] = "Google Maps via gosom/google-maps-scraper"
        if website and not lead.get("website"):
            lead["website"] = re.sub(r"^https?://(www\.)?", "", website).rstrip("/")
        hits += 1
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnpj", action="store_true", help="query the free CNPJ APIs")
    ap.add_argument("--gmaps", type=Path, help="ingest google-maps-scraper CSV/JSON output")
    args = ap.parse_args()

    if not args.cnpj and not args.gmaps:
        ap.print_help()
        return 2

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    leads = payload["leads"]

    total = 0
    if args.cnpj:
        total += enrich_from_cnpj(leads)
    if args.gmaps:
        total += enrich_from_gmaps(leads, args.gmaps)

    DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"enriched {total} leads -> {DATA}")
    print("now run: python enrich.py --no-crawl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
