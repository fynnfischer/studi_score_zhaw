"""Score-Logik. Reine Funktionen ohne DB-Zugriff, damit sie einzeln testbar sind.

Ablauf (Details: docs/score.qmd):
  1. n_k      = Anzahl POIs der Kategorie k im Umkreis r
  2. ref_k(r) = 99. Perzentil von n_k über alle CH-PLZ beim gleichen Radius r (Import)
  3. s_k      = 100 * min(1, ln(1 + n_k) / ln(1 + ref_k))    Teilscore 0..100
  4. w_k      = LEVEL_WEIGHTS[Antwort]                       0.5 / 1 / 2
  5. Score    = sum(w_k * s_k) / sum(w_k)                    0..100
"""

import math

from categories import CATEGORIES, LEVEL_LABELS, LEVEL_WEIGHTS

EARTH_RADIUS_KM = 6378.1  # Erdradius wie in der MongoDB-Doku für $centerSphere
RADII = [0.5 * i for i in range(1, 11)]  # erlaubte Radien (Slider): 0.5 .. 5 km
REF_PERCENTILE = 99


def snap_radius(radius_km):
    """Radius auf die 0.5-km-Stufen runden (nur für diese gibt es Referenzwerte)."""
    return min(RADII, key=lambda r: abs(r - radius_km))


def radius_index(radius_km):
    return RADII.index(snap_radius(radius_km))


def area_km2(radius_km):
    return math.pi * radius_km ** 2


def density(count, radius_km):
    return count / area_km2(radius_km)


def subscore(count, ref):
    """Log-Normierung gegen Referenzanzahl ref (P99 CH, gleicher Radius). Abnehmender Grenznutzen."""
    if ref <= 0:
        return 0.0
    return 100 * min(1.0, math.log1p(count) / math.log1p(ref))


def percentile_value(values, q):
    """q-Perzentil (0..100) mit linearer Interpolation, wie numpy.percentile."""
    values = sorted(values)
    pos = (len(values) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def total_score(subscores, weights):
    """Gewichteter Mittelwert. subscores/weights: dict key -> Wert."""
    w_sum = sum(weights.values())
    return sum(weights[k] * subscores[k] for k in weights) / w_sum


def weights_from_levels(levels):
    """levels: dict key -> 0/1/2 (Antworten). Fehlende Antworten = mittel."""
    return {c["key"]: LEVEL_WEIGHTS[levels.get(c["key"], 1)] for c in CATEGORIES}


def compute(counts, radius_km, refs, levels):
    """Berechnet Score + Aufschlüsselung pro Kategorie (für Radar-Chart und Tabelle)."""
    weights = weights_from_levels(levels)
    w_sum = sum(weights.values())
    rows, subs = [], {}
    for c in CATEGORIES:
        k = c["key"]
        n = counts.get(k, 0)
        d = density(n, radius_km)
        s = subscore(n, refs[k])
        subs[k] = s
        rows.append({
            "key": k,
            "label": c["label"],
            "color": c["color"],
            "count": n,
            "density": round(d, 2),
            "ref": round(refs[k], 2),
            "subscore": round(s, 1),
            "level": levels.get(k, 1),
            "level_label": LEVEL_LABELS[levels.get(k, 1)],
            "weight": weights[k],
            "contribution": round(weights[k] * s / w_sum, 1),  # Punkte am Gesamtscore
        })
    return {"score": round(total_score(subs, weights)), "categories": rows}


def percentile(score, distribution):
    """Anteil (in %) der Werte in distribution, die kleiner als score sind."""
    if not distribution:
        return None
    below = sum(1 for x in distribution if x < score)
    return math.floor(100 * below / len(distribution))  # abrunden: nie "100 %", wenn andere gleich gut sind


def haversine_m(lat1, lon1, lat2, lon2):
    """Distanz in Metern zwischen zwei WGS84-Punkten."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * 1000 * math.asin(math.sqrt(a))


if __name__ == "__main__":
    # Kleiner Selbsttest: python app/scoring.py
    refs = {c["key"]: 50.0 for c in CATEGORIES}
    assert snap_radius(1.3) == 1.5 and radius_index(5) == 9
    assert percentile_value([1, 2, 3, 4, 5], 50) == 3
    assert subscore(0, 50) == 0
    assert subscore(50, 50) == 100
    assert subscore(500, 50) == 100
    r_all_mid = compute({k: 100 for k in refs}, 1.5, refs, {})
    r_party = compute({"nachtleben": 300}, 1.5, refs, {"nachtleben": 2})
    r_noparty = compute({"nachtleben": 300}, 1.5, refs, {"nachtleben": 0})
    assert r_party["score"] > r_noparty["score"]
    assert percentile(50, [10, 20, 60, 70]) == 50
    assert 19000 < haversine_m(47.3779, 8.5403, 47.5000, 8.7237) < 20500  # ZH HB - Winterthur HB
    print("ok", r_all_mid["score"], r_party["score"], r_noparty["score"])
