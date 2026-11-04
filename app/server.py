"""StudiScore Flask-Server.

Start:  uv run python app/server.py   ->  http://127.0.0.1:5000/

Liefert das Frontend aus static/ und JSON-APIs (immer dict, nie Liste – siehe Slides SW 3).
"""

import os
import re

from flask import Flask, request
from pymongo.errors import PyMongoError

import scoring
from categories import CATEGORIES, CATEGORY_KEYS
from db import amenities, meta, plz

app = Flask(__name__)

RADIUS_MIN, RADIUS_MAX = scoring.RADII[0], scoring.RADII[-1]
PLZ_RE = re.compile(r"^\d{4}$")


# ---------- Hilfsfunktionen ----------

def error(message, status):
    return {"error": message}, status


def parse_radius(value):
    """Radius in km aus Request lesen und auf 0.5-km-Stufen zwischen 0.5 und 5 km runden."""
    try:
        return scoring.snap_radius(float(value))
    except (TypeError, ValueError):
        return None


def location_doc(doc):
    return {
        "plz": doc["_id"],
        "name": doc["name"],
        "gemeinde": doc["gemeinde"],
        "canton": doc["canton"],
        "lat": doc["lat"],
        "lon": doc["lon"],
        "center_source": doc["center_source"],
    }


def geo_filter(lat, lon, radius_km):
    # $centerSphere erwartet [lon, lat] und den Radius in Radiant
    return {"location": {"$geoWithin": {"$centerSphere": [[lon, lat], radius_km / scoring.EARTH_RADIUS_KM]}}}


def count_by_category(lat, lon, radius_km):
    counts = {k: 0 for k in CATEGORY_KEYS}
    pipeline = [{"$match": geo_filter(lat, lon, radius_km)},
                {"$group": {"_id": "$category", "n": {"$sum": 1}}}]
    for row in amenities.aggregate(pipeline):
        counts[row["_id"]] = row["n"]
    return counts


_ref_cache = {}


def reference_data():
    """Referenzwerte + Zählwerte aller PLZ (einmal laden, ändern sich nur beim Import)."""
    if not _ref_cache:
        doc = meta.find_one({"_id": "refs"})
        if doc is None:
            return None
        _ref_cache["refs"] = doc["refs"]              # Liste parallel zu RADII
        _ref_cache["percentile"] = doc["percentile"]
        _ref_cache["plz_counts"] = [d["counts"] for d in plz.find({}, {"counts": 1})]
    return _ref_cache


@app.errorhandler(PyMongoError)
def db_error(e):
    app.logger.error("MongoDB-Fehler: %s", e)
    return error("Datenbank nicht erreichbar (läuft mongod?)", 503)


# ---------- Routen ----------

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/categories")
def get_categories():
    return {"categories": CATEGORIES, "radius": {"min": RADIUS_MIN, "max": RADIUS_MAX, "default": 1.5}}


@app.route("/api/plz/<code>")
def get_plz(code):
    if not PLZ_RE.match(code):
        return error("PLZ muss 4-stellig sein", 400)
    doc = plz.find_one({"_id": code})
    if doc is None:
        return error(f"PLZ {code} nicht gefunden", 404)
    return location_doc(doc)


@app.route("/api/search")
def search_plz():
    """Autocomplete: PLZ-Anfang oder Ortsname, max. 8 Treffer."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return {"results": []}
    if q.isdigit():
        query = {"_id": {"$regex": "^" + q}}
    else:
        query = {"name": {"$regex": "^" + re.escape(q), "$options": "i"}}
    cursor = plz.find(query, {"name": 1, "canton": 1}).sort("_id", 1).limit(8)
    return {"results": [{"plz": d["_id"], "name": d["name"], "canton": d["canton"]} for d in cursor]}


@app.route("/api/score", methods=["POST"])
def post_score():
    """Score für PLZ + Radius + Antworten. Form-Felder: plz, radius, w_<kategorie> (0/1/2)."""
    code = (request.form.get("plz") or "").strip()
    app.logger.info("score: plz=%s radius=%s", code, request.form.get("radius"))
    if not PLZ_RE.match(code):
        return error("Bitte eine 4-stellige PLZ eingeben", 400)
    radius = parse_radius(request.form.get("radius", 1.5))
    if radius is None:
        return error("Ungültiger Radius", 400)

    levels = {}
    for k in CATEGORY_KEYS:
        try:
            levels[k] = min(max(int(request.form.get("w_" + k, 1)), 0), 2)
        except ValueError:
            levels[k] = 1

    doc = plz.find_one({"_id": code})
    if doc is None:
        return error(f"PLZ {code} nicht gefunden", 404)

    ref = reference_data()
    if ref is None:
        return error("Referenzwerte fehlen -> app/import_plz.py ausführen", 503)
    i = scoring.radius_index(radius)
    refs = ref["refs"][i]
    counts = count_by_category(doc["lat"], doc["lon"], radius)
    result = scoring.compute(counts, radius, refs, levels)

    # Vergleich: gleiche Gewichte + gleicher Radius auf alle CH-PLZ anwenden -> Perzentil
    weights = scoring.weights_from_levels(levels)
    distribution = []
    for c in ref["plz_counts"]:
        subs = {k: scoring.subscore(c[i][k], refs[k]) for k in CATEGORY_KEYS}
        distribution.append(round(scoring.total_score(subs, weights)))

    result.update(
        location=location_doc(doc),
        radius=radius,
        area_km2=round(scoring.area_km2(radius), 2),
        total_pois=sum(counts.values()),
        percentile=scoring.percentile(result["score"], distribution),
        ref_percentile=ref["percentile"],
        n_plz=len(distribution),
    )
    return result


@app.route("/api/pois")
def get_pois():
    """Alle POIs im Umkreis, optional gefiltert: ?lat=..&lon=..&radius=..&categories=lernen,essen"""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return error("lat und lon sind Pflicht", 400)
    radius = parse_radius(request.args.get("radius", 1.5))
    if radius is None:
        return error("Ungültiger Radius", 400)

    query = geo_filter(lat, lon, radius)
    cats = request.args.get("categories")
    if cats:
        query["category"] = {"$in": [c for c in cats.split(",") if c in CATEGORY_KEYS]}

    res = []
    for d in amenities.find(query):
        p_lon, p_lat = d["location"]["coordinates"]
        res.append({
            "id": d["_id"],
            "name": d.get("name"),
            "amenity": d["amenity"],
            "category": d["category"],
            "lat": p_lat,
            "lon": p_lon,
            "dist": round(scoring.haversine_m(lat, lon, p_lat, p_lon)),
            "street": " ".join(x for x in [d.get("street"), d.get("housenumber")] if x) or None,
            "opening_hours": d.get("opening_hours"),
            "website": d.get("website"),
        })
    res.sort(key=lambda p: p["dist"])
    return {"count": len(res), "pois": res}


if __name__ == "__main__":
    # Port per Umgebungsvariable änderbar, z.B. PORT=5001 (macOS: AirPlay belegt teils 5000)
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
