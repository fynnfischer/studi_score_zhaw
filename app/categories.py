"""Die 6 StudiScore-Kategorien: OSM amenity-Werte, Farbe und Frage fürs Frontend.

Auswahl der amenities basiert auf der EDA (docs/eda.ipynb).
"""

CATEGORIES = [
    {
        "key": "lernen",
        "label": "Lernen",
        "color": "#2a78d6",
        "question": "Wie wichtig sind dir Bibliotheken und Hochschulen?",
        "amenities": ["library", "university", "college"],
    },
    {
        "key": "essen",
        "label": "Essen & Kaffee",
        "color": "#eb6834",
        "question": "Wie wichtig sind dir Cafés und Restaurants?",
        "amenities": ["cafe", "restaurant", "fast_food", "food_court", "ice_cream"],
    },
    {
        "key": "nachtleben",
        "label": "Nachtleben",
        "color": "#8e44ad",
        "question": "Wie wichtig ist dir Nachtleben?",
        "amenities": ["bar", "pub", "nightclub", "biergarten"],
    },
    {
        "key": "kultur",
        "label": "Kultur & Freizeit",
        "color": "#eda100",
        "question": "Wie wichtig sind dir Kino, Theater und Kultur?",
        "amenities": ["cinema", "theatre", "arts_centre", "community_centre", "events_venue"],
    },
    {
        "key": "mobilitaet",
        "label": "Mobilität",
        "color": "#1baf7a",
        "question": "Wie wichtig sind dir Velo-Verleih, Sharing und ÖV-Knoten?",
        "amenities": ["bicycle_rental", "bus_station", "car_sharing", "ferry_terminal"],
    },
    {
        "key": "alltag",
        "label": "Alltag & Gesundheit",
        "color": "#e05a7a",
        "question": "Wie wichtig sind dir Apotheke, Arzt, Bank und Post?",
        "amenities": ["pharmacy", "doctors", "atm", "bank", "post_office", "marketplace"],
    },
]

CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
AMENITY_TO_CATEGORY = {a: c["key"] for c in CATEGORIES for a in c["amenities"]}

# Antwort auf eine Frage -> Gewicht im Score (0 = nicht wichtig, 1 = mittel, 2 = wichtig)
LEVEL_WEIGHTS = {0: 0.5, 1: 1.0, 2: 2.0}
LEVEL_LABELS = {0: "nicht wichtig", 1: "mittel", 2: "wichtig"}
