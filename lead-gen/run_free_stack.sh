#!/usr/bin/env bash
# Free, self-hosted enrichment for the MIBK lead list. No paid APIs.
# Run this on a machine with real outbound internet.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/3  Receita Federal CNPJ open data (free, official, no key)"
# Fills phone + email for any lead that carries a "cnpj" field.
python3 free_enrich.py --cnpj || echo "    (skipped)"

echo "==> 2/3  Google Maps via gosom/google-maps-scraper (free, self-hosted)"
# Install once:
#   go install github.com/gosom/google-maps-scraper@latest
# or grab a release binary from https://github.com/gosom/google-maps-scraper/releases
if command -v google-maps-scraper >/dev/null 2>&1; then
  python3 - <<'PY' > queries.txt
import json
for l in json.load(open("data/mibk_leads_brazil.json"))["leads"]:
    print(f"{l['company'].split('(')[0].split(' - ')[0].strip()} {l.get('city','').split(',')[0].strip()}")
PY
  # -email turns on address/email extraction from each place's website.
  # Check `google-maps-scraper --help`; flags do change between releases.
  google-maps-scraper -input queries.txt -results gmaps.csv -email -depth 1 -c 4 -lang pt
  python3 free_enrich.py --gmaps gmaps.csv
else
  echo "    google-maps-scraper not on PATH - skipping"
fi

echo "==> 3/3  Company websites via Crawl4AI (free, already wired)"
python3 enrich.py || echo "    (skipped)"

echo "==> Rebuilding workbook"
python3 enrich.py --no-crawl
echo "Done: out/MIBK_Leads_Brazil_enriched.xlsx"
