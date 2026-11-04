"""Verbindung zu MongoDB (Datenbank "osm", wie in den Slides SW 4)."""

import os

from pymongo import MongoClient

MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))

client = MongoClient(host=MONGO_HOST, port=MONGO_PORT, serverSelectionTimeoutMS=3000)
db = client["osm"]

amenities = db["amenities"]  # POIs als GeoJSON-Point, 2dsphere-Index
plz = db["plz"]              # PLZ -> Zentrum (lat/lon) + Referenz-Dichten
meta = db["meta"]            # Referenzwerte für die Normierung (ref pro Kategorie)
