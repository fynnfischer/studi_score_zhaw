# data/

Nicht im Git (siehe `.gitignore`).

| Datei | Quelle | Verwendet von |
|---|---|---|
| `osm-output.zip` | Kurs-Datensatz DS.PM3 (Moodle, SW 1), Format `{"nodes": [...]}` | `app/import_osm.py` |
| `ortschaftenverzeichnis_plz_4326.csv.zip` | swisstopo, Amtliches Ortschaftenverzeichnis (WGS84), wird automatisch geladen | `app/import_plz.py` |
