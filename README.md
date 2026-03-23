# Garmin GPX POI Finder

Python-Tool zum Anreichern von GPX-Routen mit Points of Interest entlang der Strecke und zum Export als Garmin-kompatible `FIT`- und `GPX`-Dateien.

Das Projekt enthält zwei Varianten:

- `gpx-poi-tool.py`: Kommandozeilen-Tool
- `gpx_poi_gui.py`: Desktop-GUI für macOS/Linux/Windows

## Funktionen

- Liest GPX-Tracks und GPX-Routen ein
- Sucht POIs entlang der Strecke über OpenStreetMap / Overpass
- Unterstützt u. a.:
  - Trinkwasser
  - Brunnen
  - Quellen
  - Toiletten
  - Restaurants, Cafés, Fast Food
  - Supermärkte, Bäckereien, Bioläden
  - Unterstände
  - Fahrradläden und Reparaturstationen
- Exportiert:
  - `*_pois.gpx` mit Strecke und echten Wegpunkten
  - `*_pois.fit` für Garmin Edge
- Erstellt in FIT-Dateien Vorwarnpunkte vor relevanten POIs
- GUI kann Touren zusätzlich in Etappen aufteilen und separate GPX-/FIT-Dateien je Etappe erzeugen

## Voraussetzungen

- Python 3.10 oder neuer
- Internetzugang für die Overpass-Abfrage

Benötigte Python-Pakete:

- `gpxpy`
- `requests`
- `fit-tool`
- `customtkinter` für die GUI

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install gpxpy requests fit-tool customtkinter
```

## CLI verwenden

Basisaufruf:

```bash
python3 gpx-poi-tool.py route.gpx
```

Mit Optionen:

```bash
python3 gpx-poi-tool.py route.gpx --radius 250 --categories water food toilets
```

Verfügbare Kategorien:

- `water`
- `food`
- `toilets`
- `shelter`
- `bike`
- `all`

Ausgabe:

- `route_pois.gpx`
- `route_pois.fit`

Wenn keine GPX-Datei übergeben wird, sucht das CLI im aktuellen Ordner nach `.gpx`-Dateien.

## GUI starten

```bash
python3 gpx_poi_gui.py
```

Die GUI unterstützt:

- Auswahl einzelner POI-Typen
- Radius-Einstellung
- Vorwarn-Distanz für FIT-Dateien
- GPX- und FIT-Export
- automatisches oder manuelles Splitten mehrtägiger Touren

## Garmin-Hinweise

- Die `FIT`-Datei ist für Garmin-Edge-Kurse gedacht.
- Vorwarnungen erscheinen nur in der `FIT`-Datei, nicht in der `GPX`.
- Damit Hinweise auf dem Gerät erscheinen, muss der Kurs auf dem Garmin aktiv navigiert werden.
- Die genaue Darstellung von Course Points hängt vom jeweiligen Edge-Modell und dessen Einstellungen ab.

## Projektdateien

- [gpx-poi-tool.py](/Users/stoegex/Desktop/gpx-POI-Garmin/gpx-poi-tool.py)
- [gpx_poi_gui.py](/Users/stoegex/Desktop/gpx-POI-Garmin/gpx_poi_gui.py)
- [README.md](/Users/stoegex/Desktop/gpx-POI-Garmin/README.md)

## Typische Ausgabe

Nach erfolgreicher Suche entstehen im Zielordner je nach Auswahl:

- eine GPX mit eingebetteten Wegpunkten
- eine FIT-Datei mit Course Points für Garmin
- bei Nutzung des Splitters zusätzliche Etappen-Dateien

## Hinweise

- Overpass kann bei vielen Anfragen rate-limitieren oder temporär langsam sein.
- Sehr lange oder extrem detailreiche Kurse können auf Garmin-Geräten intern begrenzt werden.
- Die Qualität der Treffer hängt von den OSM-Daten entlang der Route ab.
