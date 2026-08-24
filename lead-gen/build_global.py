#!/usr/bin/env python3
"""Build the worldwide MIBK buyer list, prioritised for an India-based exporter."""
import json, pathlib

U = {
 "nc": "Nitrocellulose/acrylic lacquer solvent - the largest MIBK end-use",
 "wood": "NC wood lacquer solvent - the most MIBK-intensive coating segment",
 "refin": "Automotive refinish lacquer and thinner formulation",
 "marine": "Marine/protective coating solvent blends",
 "adh": "Solvent-borne contact adhesive formulation (footwear, laminates)",
 "tyre": "Rubber cement solvent; 6PPD antidegradant chain",
 "agro": "EC/SC crop-protection formulation solvent",
 "pharma": "API extraction/purification solvent (incl. antibiotic recovery)",
 "mibc": "MIBC flotation frother feedstock - mining reagent chain",
 "sx": "Solvent extraction of Nb/Ta/Zr and rare earths",
 "dist": "Bulk solvent distribution - buys to resell, largest order sizes",
 "trade": "International chemical trading house - spot and term cargoes",
}
# (company, city, country, region, sector, use_case, buyer_type, priority)
ROWS = [
# ---------- GLOBAL / REGIONAL DISTRIBUTORS: fastest route to volume ----------
("Brenntag SE","Essen","Germany","Europe","Chemical distribution","dist","Distributor","A"),
("Univar Solutions","Downers Grove, IL","USA","North America","Chemical distribution","dist","Distributor","A"),
("IMCD Group","Rotterdam","Netherlands","Europe","Chemical distribution","dist","Distributor","A"),
("Azelis","Antwerp","Belgium","Europe","Chemical distribution","dist","Distributor","A"),
("Barentz International","Hoofddorp","Netherlands","Europe","Chemical distribution","dist","Distributor","A"),
("Biesterfeld AG","Hamburg","Germany","Europe","Chemical distribution","dist","Distributor","A"),
("HELM AG","Hamburg","Germany","Europe","Chemical trading","trade","Trader","A"),
("Stockmeier Chemie","Bielefeld","Germany","Europe","Chemical distribution","dist","Distributor","B"),
("Ravago Chemicals","Arendonk","Belgium","Europe","Chemical distribution","dist","Distributor","B"),
("Overlack AG","Moenchengladbach","Germany","Europe","Chemical distribution","dist","Distributor","B"),
("Tricon Energy","Houston, TX","USA","North America","Chemical trading","trade","Trader","A"),
("Vinmar International","Houston, TX","USA","North America","Chemical trading","trade","Trader","A"),
("Behn Meyer Group","Hamburg","Germany","Asia-Pacific","Chemical distribution","dist","Distributor","A"),
("Connell Brothers","San Francisco, CA","USA","Asia-Pacific","Chemical distribution","dist","Distributor","A"),
("Sojitz Corporation","Tokyo","Japan","East Asia","Chemical trading","trade","Trader","B"),
("Itochu Corporation","Tokyo","Japan","East Asia","Chemical trading","trade","Trader","B"),
("Marubeni Corporation","Tokyo","Japan","East Asia","Chemical trading","trade","Trader","B"),
("Petrochem Middle East","Dubai","UAE","Middle East","Chemical distribution","dist","Distributor","A"),
("Gulf Additives & Chemicals","Dubai","UAE","Middle East","Chemical distribution","dist","Distributor","A"),
("Chemical Trading & Consulting (CTC)","Dubai","UAE","Middle East","Chemical trading","trade","Trader","B"),
# ---------- MIDDLE EAST / GCC: shortest freight from Indian west-coast ports ----------
("National Paints Factories","Sharjah","UAE","Middle East","Paints & coatings","nc","End user","A"),
("Jotun UAE","Dubai","UAE","Middle East","Marine & protective coatings","marine","End user","A"),
("Berger Paints Emirates","Dubai","UAE","Middle East","Paints & coatings","nc","End user","A"),
("Hempel Paints UAE","Dubai","UAE","Middle East","Marine & protective coatings","marine","End user","B"),
("Al Gurair Paints","Dubai","UAE","Middle East","Industrial coatings","nc","End user","B"),
("Kansai Paint Middle East","Sharjah","UAE","Middle East","Paints & coatings","nc","End user","B"),
("Jazeera Paints","Riyadh","Saudi Arabia","Middle East","Paints & coatings","nc","End user","A"),
("National Paints Saudi","Dammam","Saudi Arabia","Middle East","Paints & coatings","nc","End user","A"),
("Sigma Paints Saudi Arabia (PPG)","Dammam","Saudi Arabia","Middle East","Protective coatings","marine","End user","B"),
("Arabian Chemical Company (Resins)","Jeddah","Saudi Arabia","Middle East","Resins & coatings","nc","End user","B"),
("Kuwait Paint Company","Kuwait City","Kuwait","Middle East","Paints & coatings","nc","End user","B"),
("Oman Paints & Chemicals","Muscat","Oman","Middle East","Paints & coatings","nc","End user","C"),
("Qatar Paint Company","Doha","Qatar","Middle East","Paints & coatings","nc","End user","C"),
# ---------- TURKEY: large coatings market, no domestic MIBK ----------
("DYO Boya","Izmir","Turkey","Europe","Paints & coatings","nc","End user","A"),
("Polisan Kansai Boya","Kocaeli","Turkey","Europe","Paints & coatings","nc","End user","A"),
("Betek Boya","Istanbul","Turkey","Europe","Paints & coatings","nc","End user","B"),
("Marshall Boya (AkzoNobel)","Istanbul","Turkey","Europe","Paints & coatings","nc","End user","B"),
("Casati Boya","Istanbul","Turkey","Europe","Wood coatings","wood","End user","B"),
("Ravago Petrokimya","Istanbul","Turkey","Europe","Chemical distribution","dist","Distributor","A"),
# ---------- SOUTH ASIA: shortest freight, high growth ----------
("Berger Paints Bangladesh","Dhaka","Bangladesh","South Asia","Paints & coatings","nc","End user","A"),
("Asian Paints Bangladesh","Dhaka","Bangladesh","South Asia","Paints & coatings","nc","End user","A"),
("Elite Paint & Chemical","Dhaka","Bangladesh","South Asia","Paints & coatings","nc","End user","B"),
("Roxy Paints","Dhaka","Bangladesh","South Asia","Paints & coatings","nc","End user","C"),
("Apex Footwear","Dhaka","Bangladesh","South Asia","Footwear adhesives","adh","End user","B"),
("Causeway Paints","Colombo","Sri Lanka","South Asia","Paints & coatings","nc","End user","B"),
("Multilac (Nippon Paint Lanka)","Colombo","Sri Lanka","South Asia","Paints & coatings","nc","End user","B"),
("Asian Paints Nepal","Kathmandu","Nepal","South Asia","Paints & coatings","nc","End user","C"),
# ---------- SOUTHEAST ASIA: footwear adhesives + coatings ----------
("TOA Paint Thailand","Bangkok","Thailand","Asia-Pacific","Paints & coatings","nc","End user","A"),
("Beger Paint","Bangkok","Thailand","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Nippon Paint Thailand","Bangkok","Thailand","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Chugoku Marine Paints Thailand","Rayong","Thailand","Asia-Pacific","Marine coatings","marine","End user","B"),
("Avian Brands","Surabaya","Indonesia","Asia-Pacific","Paints & coatings","nc","End user","A"),
("Propan Raya","Tangerang","Indonesia","Asia-Pacific","Wood coatings","wood","End user","A"),
("Mowilex Indonesia","Tangerang","Indonesia","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Pacific Paint (Kansai) Indonesia","Jakarta","Indonesia","Asia-Pacific","Paints & coatings","nc","End user","B"),
("PT AKR Corporindo","Jakarta","Indonesia","Asia-Pacific","Chemical distribution","dist","Distributor","A"),
("PT Lautan Luas","Jakarta","Indonesia","Asia-Pacific","Chemical distribution","dist","Distributor","A"),
("PT Justus Kimiaraya","Jakarta","Indonesia","Asia-Pacific","Chemical distribution","dist","Distributor","B"),
("4 Oranges Co.","Ho Chi Minh City","Vietnam","Asia-Pacific","Paints & coatings","nc","End user","A"),
("Kova Paint","Ho Chi Minh City","Vietnam","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Joton Paint","Hanoi","Vietnam","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Pou Chen Vietnam","Dong Nai","Vietnam","Asia-Pacific","Footwear manufacturing","adh","End user","A"),
("Feng Tay Enterprises Vietnam","Ho Chi Minh City","Vietnam","Asia-Pacific","Footwear manufacturing","adh","End user","A"),
("VietChem","Hanoi","Vietnam","Asia-Pacific","Chemical distribution","dist","Distributor","A"),
("Duc Giang Chemicals","Hanoi","Vietnam","Asia-Pacific","Chemical manufacturing","dist","Distributor","B"),
("Nippon Paint Malaysia","Shah Alam","Malaysia","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Kansai Paint Malaysia","Shah Alam","Malaysia","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Chemical Company of Malaysia","Kuala Lumpur","Malaysia","Asia-Pacific","Chemical distribution","dist","Distributor","B"),
("Pacific Paint (Boysen) Philippines","Manila","Philippines","Asia-Pacific","Paints & coatings","nc","End user","B"),
("Davies Paints Philippines","Manila","Philippines","Asia-Pacific","Paints & coatings","nc","End user","C"),
# ---------- AFRICA ----------
("Paints & Chemical Industries (Pachin)","Cairo","Egypt","Africa","Paints & coatings","nc","End user","A"),
("Sipes Egypt","Cairo","Egypt","Africa","Paints & coatings","nc","End user","B"),
("GLC Paints","Cairo","Egypt","Africa","Paints & coatings","nc","End user","B"),
("Scib Paints (Asian Paints)","Cairo","Egypt","Africa","Paints & coatings","nc","End user","B"),
("Kansai Plascon South Africa","Johannesburg","South Africa","Africa","Paints & coatings","nc","End user","A"),
("Duram (Sherwin-Williams)","Cape Town","South Africa","Africa","Paints & coatings","nc","End user","B"),
("Senmin International","Sasolburg","South Africa","Africa","Mining chemicals","mibc","Formulator","A"),
("Axis House","Cape Town","South Africa","Africa","Mining chemicals","mibc","Formulator","A"),
("Betachem","Durban","South Africa","Africa","Mining chemicals","mibc","Formulator","B"),
("Colorado SA","Casablanca","Morocco","Africa","Paints & coatings","nc","End user","B"),
("Astral Paints","Casablanca","Morocco","Africa","Paints & coatings","nc","End user","C"),
("Berger Paints Nigeria","Lagos","Nigeria","Africa","Paints & coatings","nc","End user","B"),
("CAP Plc (Portland Paints)","Lagos","Nigeria","Africa","Paints & coatings","nc","End user","C"),
("Crown Paints Kenya","Nairobi","Kenya","Africa","Paints & coatings","nc","End user","B"),
("Basco Paints","Nairobi","Kenya","Africa","Paints & coatings","nc","End user","C"),
# ---------- EUROPE: wood coatings are the MIBK-heavy segment ----------
("IVM Chemicals (Milesi)","Parona","Italy","Europe","Wood coatings","wood","End user","A"),
("ICA Group","Civitanova Marche","Italy","Europe","Wood coatings","wood","End user","A"),
("Sirca S.p.A.","Vicenza","Italy","Europe","Wood coatings","wood","End user","B"),
("Boero Bartolomeo","Genoa","Italy","Europe","Marine & protective coatings","marine","End user","B"),
("Renner Italia","Bologna","Italy","Europe","Wood coatings","wood","End user","B"),
("Barpimo S.A.","Logrono","Spain","Europe","Wood coatings","wood","End user","B"),
("Industrias Titan","Barcelona","Spain","Europe","Paints & coatings","nc","End user","B"),
("Valresa Coatings","Valencia","Spain","Europe","Wood coatings","wood","End user","C"),
("CIN Corporacion Industrial","Maia","Portugal","Europe","Paints & coatings","nc","End user","B"),
("Sniezka S.A.","Lubzina","Poland","Europe","Paints & coatings","nc","End user","B"),
("Tikkurila Polska","Debica","Poland","Europe","Paints & coatings","nc","End user","C"),
# ---------- NORTH AMERICA ----------
("Sherwin-Williams","Cleveland, OH","USA","North America","Paints & coatings","nc","End user","B"),
("PPG Industries","Pittsburgh, PA","USA","North America","Paints & coatings","nc","End user","B"),
("RPM International","Medina, OH","USA","North America","Coatings & sealants","nc","End user","B"),
("Palmer Holland","North Olmsted, OH","USA","North America","Chemical distribution","dist","Distributor","B"),
("Charkit Chemical","Norwalk, CT","USA","North America","Chemical distribution","dist","Distributor","C"),
("Solvay Mining Solutions (Cytec)","Tempe, AZ","USA","North America","Mining chemicals","mibc","Formulator","B"),
# ---------- LATIN AMERICA (non-Brazil) ----------
("Grupo Pochteca","Mexico City","Mexico","Latin America","Chemical distribution","dist","Distributor","A"),
("Quimica Delta","Mexico City","Mexico","Latin America","Chemical distribution","dist","Distributor","B"),
("Comex (PPG)","Mexico City","Mexico","Latin America","Paints & coatings","nc","End user","B"),
("Pintuco (Grupo Orbis)","Medellin","Colombia","Latin America","Paints & coatings","nc","End user","B"),
("Sinteplast","Buenos Aires","Argentina","Latin America","Paints & coatings","nc","End user","B"),
("Tersuave","Cordoba","Argentina","Latin America","Paints & coatings","nc","End user","C"),
("Orica Chile","Santiago","Chile","Latin America","Mining chemicals","mibc","Formulator","A"),
("Clariant Chile","Santiago","Chile","Latin America","Mining chemicals","mibc","Formulator","A"),
("Quimpac","Lima","Peru","Latin America","Chemical manufacturing","mibc","Distributor","B"),
]

p = pathlib.Path("data/mibk_leads_brazil.json")
d = json.loads(p.read_text(encoding="utf-8"))
for l in d["leads"]:
    l.setdefault("country", "Brazil")
    l.setdefault("region", "Latin America")
existing = {l["company"] for l in d["leads"]}
added = 0
for co, city, country, region, sector, uk, btype, prio in ROWS:
    if co in existing:
        continue
    d["leads"].append({
        "company": co, "city": city, "country": country, "region": region,
        "sector": sector, "consumption": "", "confidence": "",
        "use_case": U[uk], "buyer_type": btype, "priority": prio,
        "origin": "global",
    })
    added += 1
d["product"]["market"] = "Worldwide (export from India)"
d["meta"]["scope"] = (
    "Worldwide MIBK buyer list built for an India-based exporter. Priority A/B/C "
    "weighs freight distance from Indian ports, absence of domestic MIBK production, "
    "and order size. Distributors and trading houses rank high because they buy to "
    "resell and qualify fastest."
)
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"added {added} global companies -> {len(d['leads'])} total")
import collections
print("by region:", dict(collections.Counter(l["region"] for l in d["leads"])))
print("by priority:", dict(collections.Counter(l.get("priority","") for l in d["leads"])))
