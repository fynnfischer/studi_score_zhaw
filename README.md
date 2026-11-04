# StudiScore

📄 **Doku:** <https://fynnfischer.github.io/studi_score_zhaw/>

Wie studierendenfreundlich ist deine Region? PLZ eingeben, Radius + Prioritäten wählen → Score 0–100,
Karte mit allen passenden Orten, Radar-Chart zur Score-Zusammensetzung.

DS.PM3 · ZHAW · HS26 · Team 3 (Lewis Birrer, Fynn Fischer, Fiton Sallahaj)

**Stack:** MongoDB · Flask · jQuery · Leaflet · Chart.js (Vorgaben DS.PM3)

## Setup

Voraussetzungen: Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), MongoDB Community (läuft auf `localhost:27017`).

```bash
# MongoDB (macOS)
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community

# Python-Abhängigkeiten
uv sync

# Daten importieren (einmalig, wenige Sekunden)
#   data/osm-output.zip = Kurs-Datensatz (Moodle SW 1) nach data/ kopieren
uv run python app/import_osm.py            # -> osm.amenities
uv run python app/import_plz.py            # -> osm.plz, osm.meta (lädt swisstopo-CSV)

# Server starten
uv run python app/server.py                # http://127.0.0.1:5000/  (anderer Port: PORT=5001 ...)
```

Selbsttest Score-Logik: `uv run python app/scoring.py`

## Struktur

```
app/
  server.py        Flask-App, Routen (/api/...)
  db.py            MongoClient, Collections
  categories.py    6 Kategorien, amenities, Fragen, Gewichte
  scoring.py       Score-Berechnung (reine Funktionen)
  import_osm.py    Importer OSM -> MongoDB
  import_plz.py    Importer PLZ-Zentren + Referenzwerte -> MongoDB
  static/          Frontend (index.html, css/, js/)
data/              Rohdaten (nicht im Git)
docs/              Quarto-Website (Doku)
mongod.conf        MongoDB-Config-Vorlage
```

## Doku

```bash
cd docs
quarto preview                 # lokal
```

GitHub Pages: automatisch per GitHub Action (`.github/workflows/publish.yml`) bei jedem Push auf `main`
mit Änderungen in `docs/`. Einmalig: Settings → Pages → Source „GitHub Actions“.
