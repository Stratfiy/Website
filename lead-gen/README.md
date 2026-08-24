# MIBK Lead Generation — HSN 29141300

Buyer prospecting for **4-methylpentan-2-one (methyl isobutyl ketone)**, HSN
`29141300` (subheading `291413`), CAS `108-10-1`. Market: Brazil.

| File | What it is |
| --- | --- |
| `data/mibk_leads_brazil.json` | The lead list — 45 companies, editable by hand |
| `data/apify_google_maps.json` | Verified phones/emails pulled from Google Maps |
| `merge_apify.py` | Folds Apify results into the lead list |
| `enrich.py` | Crawl4AI pipeline + xlsx writer |
| `out/MIBK_Leads_Brazil_enriched.xlsx` | Generated deliverable (git-ignored) |

`Sheet2` of the xlsx is **exactly** the 10 columns of `MIBI_NITISH.xlsx`, in
order, with nothing appended. The extra intelligence (priority, use case, all
emails found, contact quality, source) lives on a separate `Lead Intel` sheet
so the original format stays clean.

## Two routes to contact data

**Route 1 — Apify (works, used for the current data).** Apify runs scrapers on
its own cloud, so it works even where outbound network access is restricted.
The Google Maps Scraper (`compass/crawler-google-places`) returned verified
switchboard numbers for 39 of 45 companies and corrected 7 wrong cities.

```bash
# via the Apify MCP server or API: compass/crawler-google-places
#   searchStringsArray: ["<company> <city>", ...]
#   locationQuery: "Brazil", scrapePlaceDetailPage: true, scrapeContacts: true
python merge_apify.py data/apify_google_maps.json
python enrich.py --no-crawl
```

**Route 2 — Crawl4AI (`enrich.py`).** Crawls each company's own contact pages
directly. Needs real outbound internet.

### What the two routes actually yield

Generic website contact-scraping mostly returns the wrong department. Measured
on a test batch: `cbmm.com` gave a REACH mailbox and their outside law firm;
`killing.com.br` gave `dpo@` and `recrutamento@`. Large Brazilian corporates do
not publish `compras@`. Google Maps is the better source for a verified
switchboard number, which is the realistic way in — ask for *suprimentos*.

One genuine exception found: **AkzoNobel publishes `sourcing@akzonobel.com`**.

## Run it

```bash
pip install -r requirements.txt
crawl4ai-setup          # one-time: installs the Playwright browser

python enrich.py                    # regex extraction, no API key needed
python enrich.py --llm              # + LLM pass to pick the buyer contact
python enrich.py --only CBMM,Vale   # test on a couple of companies first
python enrich.py --no-crawl         # rebuild the xlsx without crawling
```

**Route 2 needs real outbound internet.** It will not work inside a sandbox
whose egress proxy blocks general web access; use Route 1 (Apify) there.

## How contacts are found

Two passes, deterministic first:

1. **Regex.** Crawl each company's own contact pages (pt-BR paths first, since
   the local pages carry the local numbers), then pull emails and Brazilian
   phone formats straight out of the markdown. No API key, and it cannot
   invent a value.
2. **LLM (optional, `--llm`).** Re-reads the same page and picks which contact
   a raw-material supplier should actually use. It can only *promote* an
   address the regex pass already saw on the page — it is never allowed to
   introduce one. That guard is the whole point.

### Mailbox scoring

The scoring is the part that matters commercially. A paint company's `0800`
SAC line will not buy your MIBK. Mailboxes are ranked by how close they sit to
someone who signs a purchase order:

| Score | Mailbox | Meaning |
| --- | --- | --- |
| 100 | `compras@`, `suprimentos@` | Purchasing — offer here |
| 95 | `procurement@`, `purchasing@` | Purchasing (EN sites) |
| 85 | `fornecedores@`, `supply@` | Supplier onboarding |
| 70 | `comercial@` | Commercial, usually reroutes correctly |
| 45 | named individual | Useful, but personal data — handle accordingly |
| 35 | `info@`, `contato@` | General; expect to be rerouted |
| 5 | `sac@`, `ouvidoria@` | Consumer service — **do not offer here** |

`noreply@`, HR, press and legal/LGPD addresses are dropped outright.

The `Contact Quality` column carries the grade forward, so you can filter to
`HIGH` before anyone starts sending offers.

## Data honesty

- **Consumption figures are analyst estimates**, derived from sector, plant
  scale and the MIBK intensity of the end-use process. They are not verified
  purchase data. The `Confidence` column grades them; treat `Low` as a
  hypothesis to test on the call, not a number to quote back.
- **Cities** are the primary Brazilian plant or head-office location from
  public company information. Verify before using on a shipping document.
- **Contact cells are blank when unverified.** Nothing in this pipeline
  fabricates a contact, and nothing should be added by hand without a source
  URL in the `Contact Source URL` column.

## Why these companies

MIBK demand in Brazil concentrates in five end-uses:

1. **Coatings** — solvent for nitrocellulose, acrylic and vinyl systems. Wood
   lacquers (Sayerlack, Farben) are the most MIBK-intensive segment of all.
2. **Adhesives** — solvent-borne contact adhesives. The Vale dos Sinos
   footwear cluster in RS (Artecola, Killing) is the concentration point.
3. **Mining** — MIBK is the feedstock for MIBC flotation frother, and the
   classic solvent-extraction agent for niobium and tantalum. **CBMM in Araxá
   is the single highest-intensity MIBK user in the country** and was absent
   from the original list.
4. **Rubber** — rubber cement solvent and the 6PPD antidegradant chain.
5. **Agrochemicals & pharma** — EC/SC formulation solvent; antibiotic
   extraction.

**Distributors** (Brenntag, Univar, IMCD, Química Anastácio) are listed as
priority A separately: they buy to resell, so they carry the largest single
order sizes and the shortest qualification cycle for a trader.
