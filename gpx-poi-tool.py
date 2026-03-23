#!/usr/bin/env python3
"""
gpx-poi-tool.py
Sucht Points of Interest (POIs) wie Wasser, Essen oder Toiletten entlang
einer GPX-Route und erzeugt Garmin-kompatible FIT- und GPX-Dateien.
"""

import sys
import os
import math
import glob
import time
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from types import SimpleNamespace

import gpxpy
import requests

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.course_message import CourseMessage
from fit_tool.profile.messages.course_point_message import CoursePointMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.profile_type import FileType, Manufacturer, Sport, CoursePoint
import argparse


# ─────────────────────────────────────────────────────────────
# Konfiguration
# ─────────────────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SAMPLE_DISTANCE_M = 500       # Jeden X Meter einen Stützpunkt nehmen
DEDUP_RADIUS_M    = 40        # Wasserstellen näher als X m zusammenfassen
CHUNK_SIZE        = 40        # Overpas-Abfrage in Blöcken (Punkte pro Request)
REQUEST_DELAY_S   = 2.0       # Wartezeit zwischen Overpass-Requests

# Welche OSM-Elemente mit welchen Tags sollen gesucht werden?
# (Aufgeteilt nach Kategorien für CLI-Bedienung)
POI_CATEGORIES = {
    "water": [
        'node["amenity"="drinking_water"]',
        'node["amenity"="fountain"]',
        'node["natural"="spring"]',
        'node["man_made"="water_tap"]',
        'node["amenity"="water_point"]',
        'node["amenity"="kneipp_water_cure"]',
        'node["amenity"="public_bath"]',
    ],
    "toilets": [
        'node["amenity"="toilets"]',
    ],
    "food": [
        'node["shop"="organic"]',
        'node["shop"="supermarket"]',
        'node["shop"="convenience"]',
        'node["shop"="health_food"]',
        'node["shop"="bakery"]',
        'node["amenity"="restaurant"]',
        'node["amenity"="cafe"]',
        'node["amenity"="food_court"]',
        'node["amenity"="fast_food"]',
    ],
    "bike": [
        'node["amenity"="bicycle_repair_station"]',
        'node["shop"="bicycle"]',
    ],
    "shelter": [
        'node["amenity"="shelter"]',
    ]
}

# OSM-Tags die als POI (Point of Interest) gelten
# POI_QUERIES = [
#     'node["amenity"="drinking_water"]',
#     'node["amenity"="fountain"]["drinking_water"!="no"]',
#     'node["natural"="spring"]["drinking_water"!="no"]',
#     'node["man_made"="water_tap"]',
#     'node["amenity"="water_point"]',
#     'node["amenity"="shelter"]',
#     'node["shop"="supermarket"]',
#     'node["shop"="convenience"]',
#     'node["shop"="health_food"]',
#     'node["shop"="bakery"]',
#     'node["amenity"="kneipp_water_cure"]',
#     'node["amenity"="public_bath"]',
#     'node["amenity"="toilets"]',
#     'node["shop"="organic"]',
#     'node["amenity"="restaurant"]',
#     'node["amenity"="cafe"]',
#     'node["amenity"="food_court"]',
#     'node["amenity"="fast_food"]',
#     'node["amenity"="bicycle_repair_station"]',
#     'node["shop"="bicycle"]',
# ]

# Garmin-Symbolname, Anzeigename und Garmin Connect Course-Typ je Typ
TYPE_INFO = {
    "drinking_water": ("Trinkwasser",   "Water Source", "WATER"),
    "fountain":       ("Brunnen",       "Water Source", "WATER"),
    "spring":         ("Quelle",        "Water Source", "WATER"),
    "water_tap":      ("Wasserhahn",    "Water Source", "WATER"),
    "water_point":    ("Wasserpunkt",   "Water Source", "WATER"),
    "shelter":        ("Unterstand",    "Lodge", "GENERIC"),
    "supermarket":    ("Supermarkt",    "Shopping Center", "FOOD"),
    "convenience":    ("Kiosk/Laden",   "Convenience Store", "FOOD"),
    "health_food":    ("Reformhaus",    "Convenience Store", "FOOD"),
    "bakery":         ("Bäckerei",      "Convenience Store", "FOOD"),
    "kneipp_water_cure":("Kneippanlage","Water Source", "WATER"),
    "public_bath":    ("Freibad/Bad",   "Swimming Area", "GENERIC"),
    "toilets":        ("WC/Toilette",   "Restroom", "GENERIC"),
    "organic":        ("Bioladen",      "Convenience Store", "FOOD"),
    "restaurant":     ("Restaurant",    "Restaurant", "FOOD"),
    "cafe":           ("Cafe",          "Restaurant", "FOOD"),
    "food_court":     ("Food Court",    "Restaurant", "FOOD"),
    "fast_food":      ("Fast Food",     "Fast Food", "FOOD"),
    "bicycle":        ("Fahrradgeschäft","Waypoint", "GENERIC"),
    "bicycle_repair_station": ("Fahrrad-Service", "Waypoint", "GENERIC"),
    "unknown":        ("POI",           "Waypoint", "GENERIC"),
}

# FIT CoursePoint-Typ je OSM-Typ
TYPE_TO_COURSE_POINT = {
    "drinking_water":        CoursePoint.WATER,
    "fountain":              CoursePoint.WATER,
    "spring":                CoursePoint.WATER,
    "water_tap":             CoursePoint.WATER,
    "water_point":           CoursePoint.WATER,
    "kneipp_water_cure":     CoursePoint.WATER,
    "toilets":               CoursePoint.GENERIC,
    "public_bath":           CoursePoint.GENERIC,
    "restaurant":            CoursePoint.FOOD,
    "cafe":                  CoursePoint.FOOD,
    "food_court":            CoursePoint.FOOD,
    "fast_food":             CoursePoint.FOOD,
    "supermarket":           CoursePoint.FOOD,
    "convenience":           CoursePoint.FOOD,
    "health_food":           CoursePoint.FOOD,
    "bakery":                CoursePoint.FOOD,
    "organic":               CoursePoint.FOOD,
    "shelter":               CoursePoint.GENERIC,
    "bicycle":               CoursePoint.GENERIC,
    "bicycle_repair_station":CoursePoint.GENERIC,
}


# ─────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────


def compute_cumulative_distances(track_points):
    """Gibt für jeden Trackpunkt die kumulierte Distanz vom Start (in Metern) zurück."""
    dists = [0.0]
    for i in range(1, len(track_points)):
        p, q = track_points[i - 1], track_points[i]
        dists.append(dists[-1] + haversine(p.latitude, p.longitude, q.latitude, q.longitude))
    return dists


def find_nearest_track_idx(poi_lat, poi_lon, track_points):
    """Findet den Index des nächstgelegenen Trackpunktes zum POI."""
    min_dist = float('inf')
    nearest = 0
    for i, tp in enumerate(track_points):
        d = haversine(poi_lat, poi_lon, tp.latitude, tp.longitude)
        if d < min_dist:
            min_dist, nearest = d, i
    return nearest, min_dist

def haversine(lat1, lon1, lat2, lon2):
    """Entfernung in Metern zwischen zwei GPS-Koordinaten."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def sample_track(track_points, step_m=SAMPLE_DISTANCE_M):
    """Erzeugt Stützpunkte in ungefähr konstanten Abständen entlang der Route."""
    if not track_points:
        return []
    sampled = [SimpleNamespace(latitude=track_points[0].latitude,
                               longitude=track_points[0].longitude)]
    distance_since_start = 0.0
    next_sample_at = float(step_m)

    for i in range(1, len(track_points)):
        p, q = track_points[i - 1], track_points[i]
        seg_len = haversine(p.latitude, p.longitude, q.latitude, q.longitude)
        if seg_len <= 0:
            continue

        while distance_since_start + seg_len >= next_sample_at:
            ratio = (next_sample_at - distance_since_start) / seg_len
            sampled.append(SimpleNamespace(
                latitude=p.latitude + (q.latitude - p.latitude) * ratio,
                longitude=p.longitude + (q.longitude - p.longitude) * ratio,
            ))
            next_sample_at += step_m

        distance_since_start += seg_len

    end_pt = track_points[-1]
    if haversine(sampled[-1].latitude, sampled[-1].longitude,
                 end_pt.latitude, end_pt.longitude) > 0.01:
        sampled.append(SimpleNamespace(latitude=end_pt.latitude,
                                       longitude=end_pt.longitude))
    return sampled


def classify_node(node):
    """Gibt den Typ einer OSM-Node zurück."""
    tags = node.get("tags", {})
    amenity = tags.get("amenity", "")
    natural = tags.get("natural", "")
    man_made = tags.get("man_made", "")
    shop = tags.get("shop", "")
    
    if amenity == "drinking_water": return "drinking_water"
    if amenity == "fountain": return "fountain"
    if natural == "spring": return "spring"
    if man_made == "water_tap": return "water_tap"
    if amenity == "water_point": return "water_point"
    if amenity == "shelter": return "shelter"
    if amenity == "kneipp_water_cure": return "kneipp_water_cure"
    if amenity == "public_bath": return "public_bath"
    if amenity == "toilets": return "toilets"
    if amenity == "restaurant": return "restaurant"
    if amenity == "cafe": return "cafe"
    if amenity == "food_court": return "food_court"
    if amenity == "fast_food": return "fast_food"
    if amenity == "bicycle_repair_station": return "bicycle_repair_station"
    
    if shop == "supermarket": return "supermarket"
    if shop == "convenience": return "convenience"
    if shop == "health_food": return "health_food"
    if shop == "bakery": return "bakery"
    if shop == "organic": return "organic"
    if shop == "bicycle": return "bicycle"
    
    return "unknown"


def deduplicate(waypoints, radius_m=DEDUP_RADIUS_M):
    """Entfernt nahe Dubletten nur innerhalb desselben POI-Typs."""
    kept = []
    for wp in waypoints:
        too_close = False
        for k in kept:
            if wp["type"] != k["type"]:
                continue
            if haversine(wp["lat"], wp["lon"], k["lat"], k["lon"]) < radius_m:
                too_close = True
                break
        if not too_close:
            kept.append(wp)
    return kept


# ─────────────────────────────────────────────────────────────
# Overpass-Abfrage
# ─────────────────────────────────────────────────────────────

def build_overpass_query_bbox(chunk_points, radius_m, active_queries):
    """Baut eine Overpass-Abfrage mittels Bounding Box für die gegebenen Queries."""
    min_lat = min(p[0] for p in chunk_points)
    max_lat = max(p[0] for p in chunk_points)
    min_lon = min(p[1] for p in chunk_points)
    max_lon = max(p[1] for p in chunk_points)

    # Puffern um den Radius (ca. 1 Grad = 111km)
    buffer = max(radius_m / 50000.0, 0.005)
    s = min_lat - buffer
    n = max_lat + buffer
    w = min_lon - buffer
    e = max_lon + buffer

    bbox = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"

    unions = []
    for pq in active_queries:
        unions.append(f'  {pq}({bbox});')
    
    body = "\n".join(unions)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout body;"


def query_overpass(centers, radius_m, categories):
    """
    Fragt die Overpass-API für eine Liste von (lat, lon)-Stützpunkten ab,
    aber nur für die vom User gewählten Kategorien.
    """
    # Flache Liste aller Queries für die ausgewählten Kategorien erstellen
    active_queries = []
    for cat in categories:
        if cat in POI_CATEGORIES:
            active_queries.extend(POI_CATEGORIES[cat])
    
    if not active_queries:
        return []

    results = {}  # id → node-dict

    # Die Abfrage wird in Blöcken (chunks) von Punkten durchgeführt,
    # um die URL-Länge zu begrenzen und Overpass nicht zu überlasten.
    # Für jeden Block wird eine Bounding Box Abfrage gemacht.
    chunks = [centers[i:i + CHUNK_SIZE] for i in range(0, len(centers), CHUNK_SIZE)]
    total_chunks = len(chunks)

    for idx, chunk in enumerate(chunks):
        query = build_overpass_query_bbox(chunk, radius_m, active_queries)
        retries = 3
        wait_time = 5
        
        chunk_nodes = []
        for attempt in range(retries):
            spinner_msg(f"Lade Karte ({idx + 1}/{total_chunks})")
            try:
                resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
                if resp.status_code in (429, 504):
                    spinner_msg(f"Warte ... Rate-Limit ...")
                    time.sleep(wait_time)
                    wait_time *= 2
                    continue
                resp.raise_for_status()
                data = resp.json()
                for elem in data.get("elements", []):
                    if elem.get("type") == "node":
                        chunk_nodes.append(elem)
                break
            except requests.RequestException:
                time.sleep(wait_time)
                wait_time *= 2
        
        # NACH DEM LADEN: Distanz exakt prüfen, da wir mittels BBOX alles in einem Rechteck geholt haben
        for node in chunk_nodes:
            n_id = node["id"]
            if n_id in results:
                continue
            n_lat, n_lon = node["lat"], node["lon"]
            for p in chunk:
                if haversine(n_lat, n_lon, p[0], p[1]) <= radius_m:
                    results[n_id] = node
                    break

        if idx < total_chunks - 1:
            time.sleep(1.0)

    return list(results.values())


# ─────────────────────────────────────────────────────────────
# Spinner
# ─────────────────────────────────────────────────────────────

_spinner_text = ""
_spinner_running = False

def spinner_msg(text):
    global _spinner_text
    _spinner_text = text

def _spin():
    chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    i = 0
    while _spinner_running:
        print(f"\r{chars[i % len(chars)]} {_spinner_text}   ", end="", flush=True)
        time.sleep(0.1)
        i += 1
    print("\r" + " " * 70 + "\r", end="", flush=True)

def start_spinner():
    global _spinner_running
    _spinner_running = True
    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    return t

def stop_spinner():
    global _spinner_running
    _spinner_running = False
    time.sleep(0.15)


# ─────────────────────────────────────────────────────────────
# GPX-Output
# ─────────────────────────────────────────────────────────────

def nodes_to_waypoints(nodes, track_points=None):
    """Wandelt OSM-Nodes in eine einheitliche Waypoint-Liste um.
       Erstellt optional 100m-Vorwarnpunkte, wenn track_points gegeben sind."""
    wpts = []
    # Group nodes by their classified type
    by_type = {}
    for node in nodes:
        typ = classify_node(node)
        if typ not in by_type:
            by_type[typ] = []
        by_type[typ].append(node)

    for typ, nodes_of_type in by_type.items():
        name_de, sym, ctype = TYPE_INFO.get(typ, TYPE_INFO["unknown"])
        for node in nodes_of_type:
            poi_lat, poi_lon = node["lat"], node["lon"]
            tags = node.get("tags", {})
            osm_name = tags.get("name", "")
            display = osm_name if osm_name else name_de
            desc_parts = [name_de]
            if osm_name:
                desc_parts.append(f'Name: {osm_name}')
            note = tags.get("description", tags.get("note", ""))
            if note:
                desc_parts.append(note)
            
            # Google Maps Link
            gmaps_link = f"https://www.google.com/maps/search/?api=1&query={poi_lat},{poi_lon}"
            desc_parts.append(f"Maps: {gmaps_link}")
            
            wpts.append({
                "lat":  poi_lat,
                "lon":  poi_lon,
                "name": display[:30],
                "sym":  sym,
                "ctype": ctype,
                "cmt":  gmaps_link,
                "desc": " | ".join(desc_parts),
                "type": typ,
            })
            
            # 100m Warnpunkt auf dem Track berechnen
            if track_points:
                min_dist, closest_idx = float('inf'), 0
                for i, tp in enumerate(track_points):
                    d = haversine(poi_lat, poi_lon, tp.latitude, tp.longitude)
                    if d < min_dist:
                        min_dist, closest_idx = d, i
                
                # Warnpunkte für POIs in der Nähe der Route
                # (Wir nehmen hier 1.5x den Suchradius als Puffer für Warnpunkte)
                max_alert_dist = 250 # Standard-Warnung
                if min_dist <= max_alert_dist:
                    dist_accum = 0.0
                    warn_idx = closest_idx
                    while warn_idx > 0 and dist_accum < 100.0:
                        d = haversine(track_points[warn_idx].latitude, track_points[warn_idx].longitude,
                                      track_points[warn_idx-1].latitude, track_points[warn_idx-1].longitude)
                        dist_accum += d
                        warn_idx -= 1
                    
                    if dist_accum >= 30.0:  # Genug Distanz für einen Warnpunkt
                        wpts.append({
                            "lat": track_points[warn_idx].latitude,
                            "lon": track_points[warn_idx].longitude,
                            "name": f"100m! {display}"[:30],
                            "sym": "Danger Area",
                            "ctype": "GENERIC",
                            "cmt": f"Warnpunkt 100m vor: {display}",
                            "desc": f"100m vorher! {display}",
                            "type": f"{typ}_warn",
                        })
    return wpts


def write_gpx_integrated(original_gpx_path, waypoints, out_path):
    """
    Kopiert die Original-GPX-Datei und fügt die Wegpunkte (Wasserstellen)
    vor dem ersten <trk> oder <rte> Block ein, damit die Route erhalten bleibt.
    """
    import re
    with open(original_gpx_path, "r", encoding="utf-8") as f:
        content = f.read()

    wpt_lines = []
    for wp in waypoints:
        lat = f'{wp["lat"]:.7f}'
        lon = f'{wp["lon"]:.7f}'
        name = _esc(wp["name"])
        desc = _esc(wp.get("desc", ""))
        sym  = _esc(wp.get("sym", "Waypoint"))
        ctype = _esc(wp.get("ctype", "GENERIC"))
        cmt = _esc(wp.get("cmt", ""))
        
        cmt_line = f'\n    <cmt>{cmt}</cmt>' if cmt else ""
        wpt_lines.append(
            f'  <wpt lat="{lat}" lon="{lon}">\n'
            f'    <name>{name}</name>{cmt_line}\n'
            f'    <desc>{desc}</desc>\n'
            f'    <sym>{sym}</sym>\n'
            f'    <type>{ctype}</type>\n'
            f'  </wpt>'
        )
    wpt_str = "\n" + "\n".join(wpt_lines) + "\n"

    # In GPX gehören <wpt> (Wegpunkte) vor <rte> (Routen) und <trk> (Tracks).
    # Wir suchen nach dem ersten <trk oder <rte und fügen die Wegpunkte davor ein.
    match = re.search(r'<(?:trk|rte)>|<(?:trk|rte)\s', content)
    
    if match:
        insert_pos = match.start()
        new_content = content[:insert_pos] + wpt_str + content[insert_pos:]
    else:
        # Fallback, falls kein <trk> / <rte> existiert
        insert_pos = content.rfind("</gpx>")
        if insert_pos != -1:
            new_content = content[:insert_pos] + wpt_str + content[insert_pos:]
        else:
            new_content = content  # Nichts ändern

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def _esc(text):
    """XML-Entities escapen."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def truncate_utf8(text, max_bytes=15):
    """
    Schneidet einen String so ab, dass er in UTF-8 kodiert maximal
    `max_bytes` lang ist, ohne Multi-Byte-Zeichen zu zerschneiden.
    Wichtig für Garmins strenges 15-Byte-Limit für POI-Namen.
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    
    # Rückwärts prüfen, bis wir auf ein Star-Byte eines UTF-8 Zeichens stoßen
    # (Oder wir schneiden einfach Zeichen für Zeichen ab, bis es passt)
    while len(text.encode('utf-8')) > max_bytes:
        text = text[:-1]
    return text


# ─────────────────────────────────────────────────────────────
# FIT-Kurs-Ausgabe
# ─────────────────────────────────────────────────────────────


def write_fit_course(route_name, track_points, cum_dists, waypoints, out_path):
    """
    Erzeugt eine Garmin-FIT-Datei mit:
    - FileIdMessage (COURSE)
    - CourseMessage (Name, Sport)
    - RecordMessages (ausgedünnter Track, max. 3000 Punkte)
    - LapMessage (Gesamtüberblick)
    - CoursePointMessages (je POI: echte lat/lon, distance = exakte kumulierte Streckendistanz)

    Encoding-Konventionen von fit-tool (0.9.15):
    - timestamp/time_created/start_time: Unix-Millisekunden (scale=0.001, offset=-631065600000)
    - position_lat/long:                 Dezimalgrad (scale=2^31/180 intern, kein _to_semicircles!)
    - distance:                          Meter (scale=100 intern)
    - total_elapsed_time/timer_time:     Sekunden (scale=1000 intern)
    """
    # ── Track ausdünnen (max 3000 Punkte für handliche FIT-Größe) ──
    # Wir behalten die zugehörigen Original-Distanzen aus cum_dists,
    # um Kurvenverkürzungen zu vermeiden.
    MAX_RECORD_POINTS = 3000
    if len(track_points) > MAX_RECORD_POINTS:
        step = len(track_points) / MAX_RECORD_POINTS
        indices = sorted(set(int(i * step) for i in range(MAX_RECORD_POINTS)))
        # Immer Start- und Endpunkt einschließen
        if 0 not in indices: indices.insert(0, 0)
        if len(track_points) - 1 not in indices: indices.append(len(track_points) - 1)
        fit_track = [(track_points[i], cum_dists[i]) for i in indices]
    else:
        fit_track = list(zip(track_points, cum_dists))

    total_dist = cum_dists[-1]

    # FIT-Zeit: Sekunden seit FIT-Epoch (31.12.1989 00:00:00 UTC)
    FIT_EPOCH = 631065600  # = datetime(1989,12,31,tzinfo=utc).timestamp()
    now_fit = int(datetime.now(timezone.utc).timestamp()) - FIT_EPOCH

    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    # ── FileIdMessage ──
    # fit-tool time_created-Feld: scale=0.001, offset=-631065600000
    # → Wert in Unix-Millisekunden übergeben:
    now_unix_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    file_id = FileIdMessage()
    file_id.type = FileType.COURSE
    file_id.manufacturer = Manufacturer.GARMIN.value
    file_id.product = 0
    file_id.time_created = now_unix_ms
    file_id.serial_number = 0x12345678
    builder.add(file_id)

    # ── CourseMessage ──
    course = CourseMessage()
    course.course_name = (route_name or "Course")[:16]
    course.sport = Sport.CYCLING
    builder.add(course)

    # ── RecordMessages ──
    # Koordinaten als Dezimalgrad, Distanz in Metern, Timestamp als Unix-ms
    # Wir berechnen die Zeit anhand der echten Distanz (simulierte 5 m/s = 18 km/h),
    # das verhindert Timestamp-Sprünge beim Ausdünnen von Kurven.
    VIRTUAL_SPEED_MPS = 5.0
    for tp, dist in fit_track:
        rec = RecordMessage()
        time_offset_sec = int(dist / VIRTUAL_SPEED_MPS)
        rec.timestamp = (now_fit + time_offset_sec) * 1000 + FIT_EPOCH * 1000  # → Unix-ms
        rec.position_lat = tp.latitude
        rec.position_long = tp.longitude
        rec.distance = dist
        builder.add(rec)

    # ── LapMessage ──
    lap = LapMessage()
    total_time_sec = int(total_dist / VIRTUAL_SPEED_MPS)
    lap.timestamp = (now_fit + total_time_sec) * 1000 + FIT_EPOCH * 1000
    lap.start_time = now_fit * 1000 + FIT_EPOCH * 1000
    lap.start_position_lat = fit_track[0][0].latitude
    lap.start_position_long = fit_track[0][0].longitude
    lap.end_position_lat = fit_track[-1][0].latitude
    lap.end_position_long = fit_track[-1][0].longitude
    lap.total_distance = total_dist
    lap.total_elapsed_time = float(total_time_sec)
    lap.total_timer_time = float(total_time_sec)
    builder.add(lap)

    # ── CoursePointMessages ──
    # Nur echte POIs, keine *_warn Vorwarnpunkte
    pending_cps = []
    poi_waypoints = [wp for wp in waypoints if not wp["type"].endswith("_warn")]
    for wp in poi_waypoints:
        poi_lat, poi_lon = wp["lat"], wp["lon"]
        # Wir projizieren den Punkt auf den HOCHAUFLÖSENDEN Original-Track!
        # Das liefert eine viel exaktere Distanz, als wenn wir auf die ausgedünnten
        # Kanten projizieren (verhindert das "zu früh"-Triggern in Kurven).
        nearest_idx, nearest_dist = find_nearest_track_idx(poi_lat, poi_lon, track_points)

        # Nur POIs in sinnvoller Nähe der Original-Route in FIT aufnehmen
        if nearest_dist > 500:
            continue

        cp = CoursePointMessage()
        cp_dist = cum_dists[nearest_idx]
        time_offset_sec = int(cp_dist / VIRTUAL_SPEED_MPS)
        
        cp.timestamp = (now_fit + time_offset_sec) * 1000 + FIT_EPOCH * 1000
        cp.position_lat = poi_lat
        cp.position_long = poi_lon
        cp.distance = cp_dist       # <– Exakte Streckenposition
        cp.type = TYPE_TO_COURSE_POINT.get(wp["type"], CoursePoint.GENERIC)
        # Maximal 15 Bytes (UTF-8) für Garmin, sonst droht Crash
        cp.course_point_name = truncate_utf8(wp["name"], 15)
        pending_cps.append((cp_dist, cp))

    for _, cp in sorted(pending_cps, key=lambda item: item[0]):
        builder.add(cp)

    fit_file = builder.build()
    fit_file.to_file(out_path)


# ─────────────────────────────────────────────────────────────
# Hauptprogramm
# ─────────────────────────────────────────────────────────────

def pick_gpx_file():
    """Findet eine GPX-Datei im aktuellen Verzeichnis oder fragt nach."""
    gpx_files = sorted(glob.glob("*.gpx"))
    # Ausgabedateien ignorieren
    gpx_files = [f for f in gpx_files if not f.endswith("_pois.gpx") and not f.endswith("_wasserstellen.gpx")]

    if len(gpx_files) == 1:
        print(f"📂 Verwende GPX-Datei: {gpx_files[0]}")
        return gpx_files[0]
    elif len(gpx_files) > 1:
        print("📂 Mehrere GPX-Dateien gefunden:")
        for i, f in enumerate(gpx_files, 1):
            print(f"   [{i}] {f}")
        while True:
            choice = input("   Welche Datei verwenden? Nummer eingeben: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(gpx_files):
                return gpx_files[int(choice) - 1]
    else:
        path = input("📂 Kein GPX gefunden. Pfad zur GPX-Datei eingeben: ").strip()
        path = path.strip('"').strip("'")
        if os.path.isfile(path):
            return path
        print("❌ Datei nicht gefunden.")
        sys.exit(1)


def print_banner():
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        🗺️  GPX POI-Finder für Garmin  🗺️         ║")
    print("╚══════════════════════════════════════════════════╝")
    print()


def print_summary(waypoints, radius_m):
    """Zeigt eine schöne Zusammenfassung der gefundenen Wasserstellen."""
    from collections import Counter
    counts = Counter(wp["type"] for wp in waypoints)
    type_labels = {k: v[0] for k, v in TYPE_INFO.items()}

    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  Gefunden ({radius_m} m Radius):             │")
    for typ, cnt in counts.most_common():
        label = type_labels.get(typ, typ)
        line = f"     • {label}: {cnt}"
        print(f"  │  {line:<36}│")
    print(f"  │                                     │")
    print(f"  │  Gesamt: {len(waypoints)} POI{'s' if len(waypoints) != 1 else ' ':<30}│")
    print(f"  └─────────────────────────────────────┘")


def main():
    print_banner()

    parser = argparse.ArgumentParser(description="Findet POIs auf einer GPX-Route und erzeugt eine Garmin FIT-Datei und ein GPX mit Wegpunkten.")
    parser.add_argument("gpx_file", nargs="?", help="Pfad zur GPX-Route.")
    parser.add_argument(
        "--radius", type=int, default=250,
        help="Suchradius in Metern um die Route (Standard: 250)."
    )
    
    valid_categories = list(POI_CATEGORIES.keys()) + ["all"]
    parser.add_argument(
        "--categories", nargs="+", choices=valid_categories, default=["water"],
        help="Welche POI-Typen sollen gesucht werden? (water, food, toilets, shelter, bike, all). Standard: water."
    )
    
    args = parser.parse_args()

    # Auflösen der Kategorien
    if "all" in args.categories:
        categories = list(POI_CATEGORIES.keys())
    else:
        categories = list(dict.fromkeys(args.categories))

    radius_m = args.radius

    # GPX-Datei bestimmen
    if args.gpx_file:
        gpx_path = args.gpx_file
        if not os.path.isfile(gpx_path):
            print(f"❌ Datei nicht gefunden: {gpx_path}")
            sys.exit(1)
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        gpx_path = pick_gpx_file()

    # GPX einlesen
    print(f"\n🗺️  Lese Route ...")
    with open(gpx_path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    track_points = []
    for track in gpx.tracks:
        for seg in track.segments:
            track_points.extend(seg.points)
    for route in gpx.routes:
        track_points.extend(route.points)

    if not track_points:
        print("❌ Keine Trackpunkte in der GPX-Datei gefunden.")
        sys.exit(1)

    length_km = sum(
        haversine(track_points[i].latitude, track_points[i].longitude,
                  track_points[i+1].latitude, track_points[i+1].longitude)
        for i in range(len(track_points) - 1)
    ) / 1000

    route_name = ""
    if gpx.tracks:
        route_name = gpx.tracks[0].name or ""
    if not route_name and gpx.name:
        route_name = gpx.name

    print(f"   Route: {route_name or os.path.basename(gpx_path)}")
    print(f"   Länge: {length_km:.1f} km  |  {len(track_points)} Punkte")

    # Stützpunkte ausdünnen
    sampled = [(p.latitude, p.longitude) for p in sample_track(track_points)]
    print(f"   Stützpunkte für Abfrage: {len(sampled)}")

    print(f"\n🔍 Suche POIs ({', '.join(categories)}) in max. {radius_m} m Nähe ...")
    spinner_msg(f"Frage OpenStreetMap an ...")
    start_spinner()
    nodes_close = query_overpass(sampled, radius_m, categories)
    stop_spinner()

    wpts_close = deduplicate(nodes_to_waypoints(nodes_close, track_points=track_points))

    if wpts_close:
        print(f"\n✅ {len(wpts_close)} POI{'s' if len(wpts_close) != 1 else ''} in {radius_m} m Nähe gefunden!")
        print_summary(wpts_close, radius_m)
    else:
        print(f"\n⚠️  Keine passenden Orte in {radius_m} m Nähe gefunden.")

    # ── Ausgabe ─────────────────────────────────────────────
    if not wpts_close:
        sys.exit(0)

    base     = os.path.splitext(os.path.basename(gpx_path))[0]
    out_dir  = os.path.dirname(os.path.abspath(gpx_path))
    out_path = os.path.join(out_dir, f"{base}_pois.gpx")

    gpx_wpts = [wp for wp in wpts_close if not wp["type"].endswith("_warn")]
    write_gpx_integrated(gpx_path, gpx_wpts, out_path)

    # ── FIT-Kurs erzeugen ──────────────────────────────────────────
    fit_path = os.path.join(out_dir, f"{base}_pois.fit")
    spinner_msg("Erstelle FIT-Kurs ...")
    start_spinner()
    try:
        # Volle Distanzen berechnen VOR dem FIT-Aufruf, damit sie
        # nicht durch Ausdünnung verkürzt werden.
        full_cum_dists = compute_cumulative_distances(track_points)
        write_fit_course(route_name or base, track_points, full_cum_dists, wpts_close, fit_path)
        stop_spinner()
        print(f"\n💾 Ausgabedateien gespeichert:")
        print(f"   GPX → {out_path}")
        print(f"   FIT → {fit_path}")
        print(f"\n   → FIT-Datei in Garmin/NEWFILES/ kopieren (Edge erkennt Kurs automatisch).")
        print(f"   → GPX für BaseCamp / gpx.studio / Garmin Connect nutzen.")
    except Exception as e:
        stop_spinner()
        print(f"\n💾 Integrierte GPX-Datei gespeichert:")
        print(f"   {out_path}")
        print(f"\n⚠️  FIT-Export fehlgeschlagen: {e}")
    print()
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  🎉  Fertig! {len(wpts_close)} Wegpunkte gespeichert.{' '*(21-len(str(len(wpts_close))))}║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
