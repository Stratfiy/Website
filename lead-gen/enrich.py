#!/usr/bin/env python3
"""
MIBK buyer-contact enrichment via Crawl4AI.

Takes the lead list in data/mibk_leads_brazil.json, crawls each company's own
site for its procurement / commercial contact channels, and writes an xlsx in
the exact column layout of MIBI_NITISH.xlsx.

Design notes
------------
Extraction is deterministic first (regex over the crawled markdown) and LLM
second (optional). The regex pass needs no API key and never invents a value,
which matters here: a plausible-looking wrong email is worse than a blank cell.

Contacts are scored so that PURCHASING mailboxes outrank consumer service ones.
A paint company's `0800` SAC line will not buy your MIBK; `compras@` might.

Usage
-----
    pip install -r requirements.txt
    crawl4ai-setup                      # one-time: installs the Playwright browser
    python enrich.py                    # regex only
    python enrich.py --llm              # + LLM pass (needs ANTHROPIC_API_KEY)
    python enrich.py --only CBMM,Vale   # substring filter on company name

Requires real outbound internet. It will NOT work inside a sandbox whose egress
proxy denies general web access.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).parent
DATA = HERE / "data" / "mibk_leads_brazil.json"
OUT_XLSX = HERE / "out" / "MIBK_Leads_Brazil_enriched.xlsx"
OUT_JSON = HERE / "out" / "enrichment_raw.json"

# Column layout of the source workbook, preserved exactly.
BASE_COLUMNS = [
    "Company Name",
    "City",
    "Country",
    "Sector",
    "Estimated MIBK Consumption (MT/Year)",
    "Confidence",
    "Contact person name",
    "Mobile No",
    "Email ID",
    "Linked In ID",
]
# Appended to the right so the original format is untouched.
EXTRA_COLUMNS = [
    "Website",
    "MIBK Use Case",
    "Buyer Type",
    "Priority",
    "HSN Code",
    "Contact Source URL",
    "Contact Quality",
    "Notes",
]

# Paths worth trying on a corporate site, best first. Portuguese first: the
# target market is Brazil and pt-BR pages carry the local numbers.
CONTACT_PATHS = [
    "/contato",
    "/fale-conosco",
    "/pt-br/contato",
    "/pt/contato",
    "/contato/",
    "/suprimentos",
    "/fornecedores",
    "/compras",
    "/pt-br/fornecedores",
    "/contact",
    "/contact-us",
    "/en/contact",
    "/suppliers",
    "/procurement",
    "/about/contact",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Brazilian formats: (11) 3177-7208, +55 11 91234-5678, 0800 702 4037
PHONE_RE = re.compile(
    r"(?:\+55[\s.\-]?)?(?:\(?\d{2}\)?[\s.\-]?)?(?:0800[\s.\-]?\d{3}[\s.\-]?\d{4}"
    r"|9?\d{4}[\s.\-]\d{4})"
)

# Mailbox scoring. Higher = closer to someone who signs a purchase order.
MAILBOX_SCORES = {
    "compras": 100, "suprimentos": 100, "procurement": 95, "purchasing": 95,
    "sourcing": 90, "supply": 85, "fornecedor": 85, "supplier": 85,
    "comercial": 70, "vendas": 55, "sales": 55,
    "industrial": 60, "quimica": 60, "rawmaterial": 75,
    "contato": 40, "info": 35, "faleconosco": 30, "contact": 35,
    "sac": 5, "atendimento": 10, "ouvidoria": 5, "consumidor": 5,
}
# Never report these.
EMAIL_BLOCKLIST = re.compile(
    r"(noreply|no-reply|donotreply|postmaster|abuse|webmaster|privacy|dpo|"
    r"lgpd|imprensa|press|media|jobs|carreira|recruit|rh@|curriculo|"
    r"example\.|sentry\.|wixpress|\.png|\.jpg|\.svg|\.webp)",
    re.I,
)


@dataclass
class Contact:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    person: str = ""
    linkedin: str = ""
    source_url: str = ""
    quality: str = ""


def score_email(addr: str) -> int:
    local = addr.split("@", 1)[0].lower().replace(".", "").replace("-", "").replace("_", "")
    for key, val in MAILBOX_SCORES.items():
        if key in local:
            return val
    # A named individual's work address - useful, but it is personal data.
    # Ranked below a role mailbox on purpose.
    return 45


def clean_emails(raw: list[str], domain_hint: str) -> list[str]:
    seen, out = set(), []
    for e in raw:
        e = e.strip().strip(".,;:)")
        low = e.lower()
        if low in seen or EMAIL_BLOCKLIST.search(low):
            continue
        seen.add(low)
        out.append(e)
    # Prefer addresses on the company's own domain.
    root = domain_hint.replace("www.", "").split("/")[0]
    out.sort(key=lambda e: (-score_email(e), root not in e.lower()))
    return out


def clean_phones(raw: list[str]) -> list[str]:
    seen, out = set(), []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if not (8 <= len(digits) <= 13):
            continue
        if len(set(digits)) <= 2:  # 0000-0000 style placeholders
            continue
        if digits in seen:
            continue
        seen.add(digits)
        out.append(re.sub(r"\s+", " ", p.strip()))
    return out


def grade(c: Contact) -> str:
    if not c.emails and not c.phones:
        return "NOT FOUND - verify manually"
    top = score_email(c.emails[0]) if c.emails else 0
    if top >= 85:
        return "HIGH - purchasing mailbox"
    if top >= 55:
        return "MEDIUM - commercial mailbox"
    if top > 0:
        return "LOW - general/consumer channel, reroute before offering"
    return "PHONE ONLY"


async def crawl_company(crawler, lead: dict, run_cfg, max_pages: int = 4) -> Contact:
    site = lead.get("website", "").strip()
    if not site:
        return Contact(quality="NO WEBSITE - add one to the JSON")
    base = site if site.startswith("http") else f"https://{site}"

    contact = Contact()
    tried = 0
    for path in CONTACT_PATHS:
        if tried >= max_pages:
            break
        url = urljoin(base, path)
        try:
            res = await crawler.arun(url=url, config=run_cfg)
        except Exception as exc:  # noqa: BLE001 - one bad page must not kill the run
            print(f"    ! {url}: {type(exc).__name__}", file=sys.stderr)
            continue
        if not getattr(res, "success", False):
            continue
        tried += 1
        text = (getattr(res, "markdown", "") or "") + "\n" + (getattr(res, "html", "") or "")[:80_000]
        emails = clean_emails(EMAIL_RE.findall(text), site)
        phones = clean_phones(PHONE_RE.findall(text))
        if emails or phones:
            contact.emails = emails[:5]
            contact.phones = phones[:5]
            contact.source_url = url
            break

    contact.quality = grade(contact)
    return contact


async def llm_refine(crawler, lead: dict, contact: Contact, run_cfg_factory) -> Contact:
    """Optional second pass: ask an LLM which contact is the actual buyer."""
    import os

    from crawl4ai import LLMConfig
    from crawl4ai.extraction_strategy import LLMExtractionStrategy

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key or not contact.source_url:
        return contact

    schema = {
        "type": "object",
        "properties": {
            "contact_person": {"type": "string"},
            "role": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "linkedin": {"type": "string"},
        },
    }
    strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider="anthropic/claude-sonnet-4-5", api_token=key),
        schema=schema,
        extraction_type="schema",
        instruction=(
            "From this company contact page, extract ONLY the contact channel a raw-material "
            "SUPPLIER should use to offer a bulk solvent (procurement, supply chain, sourcing, "
            "or industrial/commercial division). Ignore consumer service (SAC), press, HR and "
            "investor relations. If no such channel is shown, return empty strings. "
            "Never guess or construct an address that is not written on the page."
        ),
    )
    try:
        res = await crawler.arun(url=contact.source_url, config=run_cfg_factory(strategy))
        data = json.loads(res.extracted_content or "[]")
        rec = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        # Only ever promote an address the regex pass already saw on the page.
        # This is the guard against the LLM inventing a plausible mailbox.
        picked = (rec.get("email") or "").strip()
        if picked in contact.emails:
            contact.emails.remove(picked)
            contact.emails.insert(0, picked)
        contact.person = (rec.get("contact_person") or "").strip()
        contact.linkedin = (rec.get("linkedin") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"    ! LLM pass failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return contact


def resolve_contact(lead: dict, crawled: Contact) -> Contact:
    """Combine what merge_apify.py stored on the lead with any live crawl result."""
    c = Contact(
        emails=list(crawled.emails),
        phones=list(crawled.phones),
        person=crawled.person,
        linkedin=crawled.linkedin,
        source_url=crawled.source_url,
    )
    if lead.get("phone") and lead["phone"] not in c.phones:
        c.phones.insert(0, lead["phone"])
    for e in lead.get("emails_found") or []:
        if e not in c.emails:
            c.emails.append(e)
    c.emails = clean_emails(c.emails, lead.get("website", ""))
    people = lead.get("people") or []
    if people and not c.person:
        c.person = people[0].get("name", "")
        c.linkedin = c.linkedin or people[0].get("linkedin", "")
        if people[0].get("mobile"):
            c.phones.insert(0, people[0]["mobile"])
    if not c.source_url and lead.get("phone_source"):
        c.source_url = lead["phone_source"]
    c.quality = grade(c)
    return c


def write_xlsx(payload: dict, results: dict[str, Contact]) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    prod = payload["product"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet2"

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F4E79")

    def style_header(sheet):
        for cell in sheet[1]:
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Sheet2 keeps the source workbook's exact 10 columns, nothing appended.
    ws.append(BASE_COLUMNS)
    style_header(ws)

    intel = wb.create_sheet("Lead Intel")
    intel.append(["Company Name", "Priority", "Buyer Type", "MIBK Use Case", "Website",
                  "HSN Code", "All Emails Found", "Contact Quality", "Data Source", "Notes"])
    style_header(intel)

    prio_fill = {
        "A": PatternFill("solid", fgColor="C6EFCE"),
        "B": PatternFill("solid", fgColor="FFEB9C"),
        "C": PatternFill("solid", fgColor="F2F2F2"),
    }

    for lead in payload["leads"]:
        c = resolve_contact(lead, results.get(lead["company"], Contact()))
        ws.append([
            lead["company"],
            lead.get("city", ""),
            "Brazil",
            lead.get("sector", ""),
            lead.get("consumption", ""),
            lead.get("confidence", ""),
            c.person,
            c.phones[0] if c.phones else "",
            c.emails[0] if c.emails else "",
            c.linkedin,
        ])
        intel.append([
            lead["company"],
            lead.get("priority", ""),
            lead.get("buyer_type", ""),
            lead.get("use_case", ""),
            lead.get("website", ""),
            prod["hsn_code"],
            "; ".join(c.emails),
            c.quality,
            c.source_url,
            lead.get("notes", ""),
        ])
        if lead.get("priority") in prio_fill:
            intel.cell(row=intel.max_row, column=2).fill = prio_fill[lead["priority"]]

    for i, w in enumerate([34, 22, 10, 32, 22, 12, 22, 22, 36, 26], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for i, w in enumerate([34, 8, 22, 48, 24, 12, 46, 34, 30, 44], 1):
        intel.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for sheet in (ws, intel):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

    meta = wb.create_sheet("Product & Method")
    meta.append(["Field", "Value"])
    meta["A1"].font = meta["B1"].font = Font(bold=True)
    for k, v in [
        ("Description", prod["description"]),
        ("Subheading", f'{prod["subheading"]} ({prod["subheading_description"]})'),
        ("Full HSN Code", prod["hsn_code"]),
        ("CAS", prod["cas"]),
        ("Market", prod["market"]),
        ("Estimates", payload["meta"]["note"]),
        ("City basis", payload["meta"]["city_basis"]),
    ]:
        meta.append([k, v])
    meta.column_dimensions["A"].width = 18
    meta.column_dimensions["B"].width = 110
    for row in meta.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_XLSX)
    print(f"wrote {OUT_XLSX}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="run the optional LLM refinement pass")
    ap.add_argument("--only", default="", help="comma-separated substrings of company names")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-crawl", action="store_true", help="just rebuild the xlsx from data")
    args = ap.parse_args()

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    leads = payload["leads"]
    if args.only:
        needles = [s.strip().lower() for s in args.only.split(",") if s.strip()]
        leads = [l for l in leads if any(n in l["company"].lower() for n in needles)]

    results: dict[str, Contact] = {}

    if not args.no_crawl:
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        except ImportError:
            print("crawl4ai is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
            return 2

        def run_cfg_factory(strategy=None):
            return CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                extraction_strategy=strategy,
                page_timeout=45_000,
                word_count_threshold=1,
            )

        browser_cfg = BrowserConfig(headless=True, verbose=False)
        sem = asyncio.Semaphore(args.concurrency)

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            run_cfg = run_cfg_factory()

            async def work(lead: dict) -> None:
                async with sem:
                    print(f"  -> {lead['company']}")
                    c = await crawl_company(crawler, lead, run_cfg)
                    if args.llm:
                        c = await llm_refine(crawler, lead, c, run_cfg_factory)
                    results[lead["company"]] = c

            await asyncio.gather(*(work(l) for l in leads))

        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps({k: vars(v) for k, v in results.items()}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    write_xlsx(payload, results)

    found = sum(1 for c in results.values() if c.emails or c.phones)
    high = sum(1 for c in results.values() if c.quality.startswith("HIGH"))
    if results:
        print(f"contacts found: {found}/{len(results)}  (purchasing-grade: {high})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
