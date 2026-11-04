"""Importer: PLZ -> Zentrum + Referenzwerte für den Score -> MongoDB osm.plz / osm.meta

Aufruf (nach import_osm.py!):
    uv run python app/import_plz.py

1. Lädt das Amtliche Ortschaftenverzeichnis (swisstopo, CSV WGS84) nach data/, falls nicht vorhanden.
2. Pro PLZ eine Zeile (grösster Adressanteil) -> Name, Kanton, Koordinate.
3. Zentrum: Median der OSM-POIs mit postcode == PLZ (liegt meist im Ortskern), falls >= 5 POIs
   und < 3 km vom swisstopo-Punkt entfernt. Sonst swisstopo-Punkt.
4. Referenz: Anzahl POIs pro Kategorie für jeden Radius 0.5..5 km um jedes Zentrum (osm.plz.counts).
   ref_k(r) = 99. Perzentil über alle PLZ -> osm.meta (für die Normierung im Score).
"""

import csv
import io
import statistics
import urllib.request
import zipfile
from pathlib import Path

from categories import CATEGORY_KEYS
from db import amenities, meta, plz
from scoring import RADII, REF_PERCENTILE, haversine_m, percentile_value

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CSV_ZIP = DATA_DIR / "ortschaftenverzeichnis_plz_4326.csv.zip"
CSV_URL = ("https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
           "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_4326.csv.zip")

MIN_TAGGED = 5        # min. POIs mit PLZ-Tag, um den Median als Zentrum zu nehmen
MAX_SHIFT_M = 3000    # max. Abstand Median <-> swisstopo-Punkt


def read_ortschaften():
    if not CSV_ZIP.exists():
        print("Lade Ortschaftenverzeichnis von swisstopo ...")
        DATA_DIR.mkdir(exist_ok=True)
        urllib.request.urlretrieve(CSV_URL, CSV_ZIP)
    with zipfile.ZipFile(CSV_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name).decode("utf-8-sig")
    best = {}  # PLZ -> Zeile mit grösstem Adressanteil
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        share = float(row["Adressenanteil"].replace("%", "").strip() or 0)
        key = row["PLZ4"]
        if key not in best or share > best[key][0]:
            best[key] = (share, row)
    return [row for _, row in best.values()]


def center_for(code, lat, lon):
    """Median der POIs mit diesem PLZ-Tag, falls plausibel. Sonst swisstopo-Punkt."""
    pts = [d["location"]["coordinates"] for d in amenities.find({"postcode": code}, {"location": 1})]
    if len(pts) >= MIN_TAGGED:
        m_lon = statistics.median(p[0] for p in pts)
        m_lat = statistics.median(p[1] for p in pts)
        if haversine_m(lat, lon, m_lat, m_lon) < MAX_SHIFT_M:
            return m_lat, m_lon, "osm"
    return lat, lon, "swisstopo"


def counts_per_radius(lat, lon):
    """Anzahl POIs pro Kategorie für alle Radien in RADII (kumuliert).

    Eine Query pro PLZ: $geoNear liefert die Distanz, danach in 500-m-Ringe gruppieren.
    Rückgabe: Liste parallel zu RADII, z.B. counts[2] = {"lernen": 4, ...} für r = 1.5 km.
    """
    step_m = RADII[0] * 1000
    pipeline = [
        {"$geoNear": {"near": {"type": "Point", "coordinates": [lon, lat]}, "distanceField": "dist",
                      "maxDistance": RADII[-1] * 1000, "spherical": True}},
        {"$group": {"_id": {"cat": "$category",
                            "ring": {"$max": [1, {"$ceil": {"$divide": ["$dist", step_m]}}]}},
                    "n": {"$sum": 1}}},
    ]
    rings = [{k: 0 for k in CATEGORY_KEYS} for _ in RADII]
    for row in amenities.aggregate(pipeline):
        rings[int(row["_id"]["ring"]) - 1][row["_id"]["cat"]] += row["n"]
    counts, running = [], {k: 0 for k in CATEGORY_KEYS}
    for ring in rings:
        running = {k: running[k] + ring[k] for k in CATEGORY_KEYS}
        counts.append(running)
    return counts


def main():
    if amenities.count_documents({}) == 0:
        raise SystemExit("osm.amenities ist leer -> zuerst app/import_osm.py ausführen")

    docs = []
    for row in read_ortschaften():
        code = row["PLZ4"]
        lat, lon, source = center_for(code, float(row["N"]), float(row["E"]))
        docs.append({
            "_id": code,
            "name": row["Ortschaftsname"],
            "gemeinde": row["Gemeindename"],
            "canton": row["Kantonskürzel"],
            "lat": lat,
            "lon": lon,
            "center_source": source,
            "counts": counts_per_radius(lat, lon),
        })
    plz.drop()
    plz.insert_many(docs)
    plz.create_index("name")

    # refs[i][k] = P99 der Anzahl in Kategorie k beim Radius RADII[i]
    refs = [{k: percentile_value([d["counts"][i][k] for d in docs], REF_PERCENTILE) for k in CATEGORY_KEYS}
            for i in range(len(RADII))]
    meta.replace_one({"_id": "refs"},
                     {"_id": "refs", "percentile": REF_PERCENTILE, "radii": RADII, "refs": refs}, upsert=True)

    n_osm = sum(d["center_source"] == "osm" for d in docs)
    print(f"OK: {len(docs):,} PLZ ({n_osm:,} Zentrum aus OSM, {len(docs) - n_osm:,} aus swisstopo)")
    print(f"Referenz P{REF_PERCENTILE} bei 1.5 km:", {k: round(v, 1) for k, v in refs[RADII.index(1.5)].items()})


if __name__ == "__main__":
    main()
