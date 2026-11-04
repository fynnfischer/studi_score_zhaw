"""Importer: osm-output.json (Kurs-Datensatz) -> MongoDB osm.amenities

Aufruf:
    uv run python app/import_osm.py [data/osm-output.zip | data/osm-output.json]

- Liest das Kursformat {"nodes": [{"id": "..", "lat": "..", "lon": "..", "amenity": .., ...}]}
  (direkt aus dem ZIP oder entpackt). Das Overpass-Format {"elements": [...]} geht auch.
- Übernimmt nur amenities, die zu einer StudiScore-Kategorie gehören.
- Speichert die Position als GeoJSON-Point und legt einen 2dsphere-Index an (Umkreissuche).
"""

import json
import sys
import zipfile
from pathlib import Path

from categories import AMENITY_TO_CATEGORY
from db import amenities

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "osm-output.zip"

# Tags, die wir zusätzlich speichern (fürs Popup auf der Karte). Kursformat ohne "addr:"-Präfix.
EXTRA_TAGS = ["street", "housenumber", "postcode", "city", "opening_hours", "website", "wheelchair", "cuisine"]


def load_nodes(path):
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".json"))
            raw = json.loads(z.read(name))
    else:
        raw = json.loads(path.read_text())

    if "nodes" in raw:  # Kursformat: flache Keys, Werte als Strings
        return raw["nodes"]
    # Overpass-Format: tags verschachtelt, "addr:" Präfix -> wie Kursformat flach machen
    nodes = []
    for el in raw["elements"]:
        node = {k.removeprefix("addr:"): v for k, v in el.get("tags", {}).items()}
        node.update(id=el["id"], lat=el["lat"], lon=el["lon"])
        nodes.append(node)
    return nodes


def to_document(node):
    """Node -> Mongo-Dokument. Gibt None zurück, wenn der Node nicht relevant/kaputt ist."""
    category = AMENITY_TO_CATEGORY.get(node.get("amenity"))
    if category is None:
        return None
    try:
        lat, lon = float(node["lat"]), float(node["lon"])
    except (KeyError, ValueError):
        return None
    doc = {
        "_id": int(node["id"]),
        "name": node.get("name"),  # kann fehlen (z.B. Bankomaten)
        "amenity": node["amenity"],
        "category": category,
        "location": {"type": "Point", "coordinates": [lon, lat]},  # GeoJSON: [lon, lat]!
    }
    for tag in EXTRA_TAGS:
        if tag in node:
            doc[tag] = node[tag]
    return doc


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    nodes = load_nodes(path)
    docs = [d for d in map(to_document, nodes) if d is not None]
    print(f"{len(nodes):,} Nodes gelesen, {len(docs):,} relevant")

    amenities.drop()
    for i in range(0, len(docs), 5000):
        amenities.insert_many(docs[i:i + 5000])
    amenities.create_index([("location", "2dsphere")])
    amenities.create_index("category")
    amenities.create_index("postcode")

    for row in amenities.aggregate([{"$group": {"_id": "$category", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]):
        print(f"  {row['_id']:<12} {row['n']:>6,}")
    print(f"OK: {amenities.count_documents({}):,} Dokumente in osm.amenities")


if __name__ == "__main__":
    main()
