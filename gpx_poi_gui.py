#!/usr/bin/env python3
"""
GPX POI Tool – Strava-Style GUI  v2.1
Fixes: individuelle POI-Checkboxen, Radius-Snap 50m, Vorwarn-Distanz einstellbar,
       Abbrechen-Button, korrekter Workflow-Ablauf, Fahrradshop/Werkstatt
"""

import sys
import os
import math
import time
import threading
import queue
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
import tkintermapview

# ─────────────────────────────────────────────
# Strava-Farbpalette
# ─────────────────────────────────────────────
STRAVA_ORANGE  = "#FC4C02"
STRAVA_DARK    = "#1A1A1A"
STRAVA_DARKER  = "#111111"
STRAVA_CARD    = "#242424"
STRAVA_CARD2   = "#2C2C2C"
STRAVA_BORDER  = "#333333"
STRAVA_TEXT    = "#FFFFFF"
STRAVA_MUTED   = "#9A9A9A"
STRAVA_GREEN   = "#2ECC71"
STRAVA_BLUE    = "#3498DB"
STRAVA_HOVER   = "#FF6B35"
STRAVA_WARN    = "#F39C12"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ─────────────────────────────────────────────
# Alle individuellen POI-Typen
# (Anzeige-Label, OSM-Key, Overpass-Query, default_on)
# ─────────────────────────────────────────────
POI_ITEMS = [
    # Wasser
    ("💧 Trinkwasser",             "drinking_water",         'node["amenity"="drinking_water"]',         True),
    ("⛲ Brunnen",                 "fountain",               'node["amenity"="fountain"]',               True),
    ("🌿 Quelle",                  "spring",                 'node["natural"="spring"]',                 True),
    ("🚰 Wasserhahn",              "water_tap",              'node["man_made"="water_tap"]',             True),
    ("💦 Wasserpunkt",             "water_point",            'node["amenity"="water_point"]',            False),
    ("🦵 Kneippanlage",            "kneipp_water_cure",      'node["amenity"="kneipp_water_cure"]',      False),
    ("🏊 Freibad / Bad",           "public_bath",            'node["amenity"="public_bath"]',            False),
    # Essen & Einkaufen
    ("🍽  Restaurant",             "restaurant",             'node["amenity"="restaurant"]',             False),
    ("☕ Café",                    "cafe",                   'node["amenity"="cafe"]',                   False),
    ("🥙 Imbiss / Food Court",     "food_court",             'node["amenity"="food_court"]',             False),
    ("🍔 Fast Food",               "fast_food",              'node["amenity"="fast_food"]',              False),
    ("🛒 Supermarkt",              "supermarket",            'node["shop"="supermarket"]',               False),
    ("🏪 Kiosk / Laden",           "convenience",            'node["shop"="convenience"]',               False),
    ("🌿 Reformhaus",              "health_food",            'node["shop"="health_food"]',               False),
    ("🥐 Bäckerei",                "bakery",                 'node["shop"="bakery"]',                    False),
    ("🌱 Bioladen",                "organic",                'node["shop"="organic"]',                   False),
    # Sanitär
    ("🚻 WC / Toilette",           "toilets",                'node["amenity"="toilets"]',                False),
    # Unterstand
    ("🏕  Unterstand",             "shelter",                'node["amenity"="shelter"]',                False),
    # Fahrrad
    ("🚲 Fahrradshop / Werkstatt", "bicycle",                'node["shop"="bicycle"]',                   False),
    ("🔧 Fahrrad-Service",         "bicycle_repair_station", 'node["amenity"="bicycle_repair_station"]', False),
]

# Gruppen für die Anzeige
POI_GROUPS = [
    ("💧 Wasser",             ["drinking_water","fountain","spring","water_tap","water_point","kneipp_water_cure","public_bath"]),
    ("🍽  Essen & Einkaufen", ["restaurant","cafe","food_court","fast_food","supermarket","convenience","health_food","bakery","organic"]),
    ("🚻 Sanitär",            ["toilets"]),
    ("🏕  Unterstand",        ["shelter"]),
    ("🚲 Fahrrad",            ["bicycle","bicycle_repair_station"]),
]

TYPE_INFO = {
    "drinking_water":        ("Trinkwasser",          "Water Source",     "WATER"),
    "fountain":              ("Brunnen",               "Water Source",     "WATER"),
    "spring":                ("Quelle",                "Water Source",     "WATER"),
    "water_tap":             ("Wasserhahn",            "Water Source",     "WATER"),
    "water_point":           ("Wasserpunkt",           "Water Source",     "WATER"),
    "kneipp_water_cure":     ("Kneippanlage",          "Water Source",     "WATER"),
    "public_bath":           ("Freibad/Bad",           "Swimming Area",    "GENERIC"),
    "shelter":               ("Unterstand",            "Lodge",            "GENERIC"),
    "supermarket":           ("Supermarkt",            "Shopping Center",  "FOOD"),
    "convenience":           ("Kiosk/Laden",           "Convenience Store","FOOD"),
    "health_food":           ("Reformhaus",            "Convenience Store","FOOD"),
    "bakery":                ("Bäckerei",              "Convenience Store","FOOD"),
    "organic":               ("Bioladen",              "Convenience Store","FOOD"),
    "toilets":               ("WC/Toilette",           "Restroom",         "GENERIC"),
    "restaurant":            ("Restaurant",            "Restaurant",       "FOOD"),
    "cafe":                  ("Cafe",                  "Restaurant",       "FOOD"),
    "food_court":            ("Imbiss",                "Restaurant",       "FOOD"),
    "fast_food":             ("Fast Food",             "Fast Food",        "FOOD"),
    "bicycle":               ("Fahrradshop/Werkstatt", "Waypoint",         "GENERIC"),
    "bicycle_repair_station":("Fahrrad-Service",       "Waypoint",         "GENERIC"),
    "unknown":               ("POI",                   "Waypoint",         "GENERIC"),
}

# Emoji + Farbe je POI-Typ für Kartenmarker
POI_MARKER_STYLE = {
    "drinking_water":         ("💧", "#3498DB"),
    "fountain":               ("⛲", "#3498DB"),
    "spring":                 ("🌿", "#3498DB"),
    "water_tap":              ("🚰", "#3498DB"),
    "water_point":            ("💦", "#3498DB"),
    "kneipp_water_cure":      ("🦵", "#3498DB"),
    "public_bath":            ("🏊", "#3498DB"),
    "restaurant":             ("🍽", "#E67E22"),
    "cafe":                   ("☕", "#E67E22"),
    "food_court":             ("🥙", "#E67E22"),
    "fast_food":              ("🍔", "#E67E22"),
    "supermarket":            ("🛒", "#E67E22"),
    "convenience":            ("🏪", "#E67E22"),
    "health_food":            ("🌿", "#E67E22"),
    "bakery":                 ("🥐", "#E67E22"),
    "organic":                ("🌱", "#E67E22"),
    "toilets":                ("🚻", "#9B59B6"),
    "shelter":                ("🏕", "#2ECC71"),
    "bicycle":                ("🚲", "#E74C3C"),
    "bicycle_repair_station": ("🔧", "#E74C3C"),
}


# ─────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def compute_cumulative_distances(track_points):
    dists = [0.0]
    for i in range(1, len(track_points)):
        p, q = track_points[i-1], track_points[i]
        dists.append(dists[-1] + haversine(p["lat"], p["lon"], q["lat"], q["lon"]))
    return dists


def _parse_gpx_etree(gpx_path):
    try:
        tree = ET.parse(gpx_path)
    except ET.ParseError as e:
        raise ValueError(f"Ungültige GPX/XML-Datei: {e}") from e

    root = tree.getroot()

    def _read_points(tag):
        pts = []
        for el in root.findall(f".//{{*}}{tag}"):
            lat = el.attrib.get("lat")
            lon = el.attrib.get("lon")
            if lat is None or lon is None:
                continue
            ele_el = el.find(".//{*}ele")
            ele = float(ele_el.text) if (ele_el is not None and ele_el.text) else 0.0
            pts.append({"lat": float(lat), "lon": float(lon), "ele": ele})
        return pts

    points = _read_points("trkpt") + _read_points("rtept")

    name = ""
    trk_name = root.find(".//{*}trk/{*}name")
    meta_name = root.find(".//{*}metadata/{*}name")
    gpx_name = root.find(".//{*}name")
    if trk_name is not None and trk_name.text:
        name = trk_name.text
    elif meta_name is not None and meta_name.text:
        name = meta_name.text
    elif gpx_name is not None and gpx_name.text:
        name = gpx_name.text

    return points, name


def parse_gpx(gpx_path):
    try:
        import gpxpy
        with open(gpx_path, "r", encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        points = []
        for track in gpx.tracks:
            for seg in track.segments:
                for pt in seg.points:
                    points.append({"lat": pt.latitude, "lon": pt.longitude,
                                   "ele": pt.elevation or 0.0})
        for route in gpx.routes:
            for pt in route.points:
                points.append({"lat": pt.latitude, "lon": pt.longitude,
                               "ele": pt.elevation or 0.0})
        name = ""
        if gpx.tracks and gpx.tracks[0].name:
            name = gpx.tracks[0].name
        elif gpx.name:
            name = gpx.name
        return points, name
    except ModuleNotFoundError:
        return _parse_gpx_etree(gpx_path)
    except Exception:
        # Fallback auf ET, wenn gpxpy mit dem GPX nicht klarkommt
        return _parse_gpx_etree(gpx_path)


def compute_elevation_gain(track_points):
    gain = 0.0
    for i in range(1, len(track_points)):
        diff = track_points[i]["ele"] - track_points[i-1]["ele"]
        if diff > 0:
            gain += diff
    return gain


def sample_track(track_points, step_m=500):
    """Sample track at step_m intervals. Always includes first and last point."""
    if not track_points:
        return []
    sampled = [{"lat": track_points[0]["lat"], "lon": track_points[0]["lon"]}]
    distance_since_start = 0.0
    next_sample_at = float(step_m)

    for i in range(1, len(track_points)):
        p, q = track_points[i-1], track_points[i]
        seg_len = haversine(p["lat"], p["lon"], q["lat"], q["lon"])
        if seg_len <= 0:
            continue

        while distance_since_start + seg_len >= next_sample_at:
            ratio = (next_sample_at - distance_since_start) / seg_len
            sampled.append({
                "lat": p["lat"] + (q["lat"] - p["lat"]) * ratio,
                "lon": p["lon"] + (q["lon"] - p["lon"]) * ratio,
            })
            next_sample_at += step_m

        distance_since_start += seg_len

    end_pt = track_points[-1]
    if haversine(sampled[-1]["lat"], sampled[-1]["lon"],
                 end_pt["lat"], end_pt["lon"]) > 0.01:
        sampled.append({"lat": end_pt["lat"], "lon": end_pt["lon"]})
    return sampled


def adaptive_sample_step(radius_m):
    """Wählt den Sample-Abstand so, dass kein POI zwischen zwei Punkten durchfällt.
    Faustregel: Schritt = 80% des Suchradius, mind. 200m, max. 800m.
    """
    return max(200, min(800, int(radius_m * 0.8)))


def classify_node(node):
    tags = node.get("tags", {})
    amenity  = tags.get("amenity", "")
    natural  = tags.get("natural", "")
    man_made = tags.get("man_made", "")
    shop     = tags.get("shop", "")
    if amenity == "drinking_water":          return "drinking_water"
    if amenity == "fountain":                return "fountain"
    if natural == "spring":                  return "spring"
    if man_made == "water_tap":              return "water_tap"
    if amenity == "water_point":             return "water_point"
    if amenity == "shelter":                 return "shelter"
    if amenity == "kneipp_water_cure":       return "kneipp_water_cure"
    if amenity == "public_bath":             return "public_bath"
    if amenity == "toilets":                 return "toilets"
    if amenity == "restaurant":              return "restaurant"
    if amenity == "cafe":                    return "cafe"
    if amenity == "food_court":              return "food_court"
    if amenity == "fast_food":               return "fast_food"
    if amenity == "bicycle_repair_station":  return "bicycle_repair_station"
    if shop == "supermarket":               return "supermarket"
    if shop == "convenience":               return "convenience"
    if shop == "health_food":               return "health_food"
    if shop == "bakery":                    return "bakery"
    if shop == "organic":                   return "organic"
    if shop == "bicycle":                   return "bicycle"
    return "unknown"


def deduplicate(waypoints, radius_m=40):
    kept = []
    for wp in waypoints:
        if not any(wp["type"] == k["type"]
                   and haversine(wp["lat"], wp["lon"], k["lat"], k["lon"]) < radius_m
                   for k in kept):
            kept.append(wp)
    return kept


def truncate_utf8(text, max_bytes=15):
    while len(text.encode("utf-8")) > max_bytes:
        text = text[:-1]
    return text


def _esc(t):
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


# ─────────────────────────────────────────────
# Overpass-Abfrage mit Cancel-Support
# ─────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CHUNK_SIZE   = 40
# "bbox" reduziert die Query-Größe drastisch (schneller), lokal wird danach
# noch per Radius gefiltert. "around" ist genauer am Server, aber sehr langsam.
OVERPASS_MODE = "bbox"  # "bbox" oder "around"


def _build_query(chunk_points, radius_m, queries):
    """Baut eine Overpass-Query.
    - mode "around": exakter Kreis pro Punkt (sehr viele Abfragen, langsam)
    - mode "bbox": eine Bounding-Box pro Chunk (schneller), Radius wird lokal geprüft
    """
    if OVERPASS_MODE == "around":
        parts = []
        for q in queries:
            for lat, lon in chunk_points:
                parts.append(f"  {q}(around:{radius_m},{lat:.6f},{lon:.6f});")
        union = "\n".join(parts)
        return f"[out:json][timeout:90];\n(\n{union}\n);\nout body;"

    # bbox mode
    lats = [p[0] for p in chunk_points]
    lons = [p[1] for p in chunk_points]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    lat_mean = (lat_min + lat_max) / 2.0
    # grobe Umrechnung Meter -> Grad
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.2, math.cos(math.radians(lat_mean))))
    south = lat_min - dlat
    north = lat_max + dlat
    west  = lon_min - dlon
    east  = lon_max + dlon

    parts = [f"  {q}({south:.6f},{west:.6f},{north:.6f},{east:.6f});" for q in queries]
    union = "\n".join(parts)
    return f"[out:json][timeout:90];\n(\n{union}\n);\nout body;"


def query_overpass_cancelable(centers, radius_m, queries, cancel_ev,
                               progress_cb=None, log_fn=None):
    import requests
    results  = {}
    chunks   = [centers[i:i+CHUNK_SIZE] for i in range(0, len(centers), CHUNK_SIZE)]
    total    = len(chunks)

    for idx, chunk in enumerate(chunks):
        if cancel_ev.is_set():
            if log_fn: log_fn("  ⛔ Abgebrochen.")
            return None

        query = _build_query(chunk, radius_m, queries)
        wait  = 5
        for attempt in range(3):
            if cancel_ev.is_set():
                return None
            if log_fn:
                log_fn(f"  Chunk {idx+1}/{total} …")
            try:
                resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
                if resp.status_code in (429, 504):
                    if log_fn: log_fn(f"  ⚠️  Rate-Limit – warte {wait}s …")
                    for _ in range(wait):
                        if cancel_ev.is_set(): return None
                        time.sleep(1)
                    wait *= 2
                    continue
                resp.raise_for_status()
                for elem in resp.json().get("elements", []):
                    if elem.get("type") == "node":
                        n_id = elem["id"]
                        if n_id not in results:
                            for p in chunk:
                                if haversine(elem["lat"], elem["lon"], p[0], p[1]) <= radius_m:
                                    results[n_id] = elem
                                    break
                break
            except Exception as e:
                if log_fn: log_fn(f"  ⚠️  Netzfehler: {e}")
                for _ in range(wait):
                    if cancel_ev.is_set(): return None
                    time.sleep(1)
                wait *= 2

        if progress_cb:
            progress_cb(idx + 1, total)
        if idx < total - 1 and not cancel_ev.is_set():
            time.sleep(1.0)

    return list(results.values())


def nodes_to_waypoints(nodes, track_points, warn_dist_m=100):
    wpts   = []
    by_type = {}
    for node in nodes:
        typ = classify_node(node)
        by_type.setdefault(typ, []).append(node)

    for typ, nlist in by_type.items():
        name_de, sym, ctype = TYPE_INFO.get(typ, TYPE_INFO["unknown"])
        for node in nlist:
            poi_lat, poi_lon = node["lat"], node["lon"]
            tags     = node.get("tags", {})
            osm_name = tags.get("name", "")
            display  = osm_name if osm_name else name_de
            gmaps    = f"https://www.google.com/maps/search/?api=1&query={poi_lat},{poi_lon}"
            desc     = " | ".join(filter(None, [name_de,
                                                f"Name: {osm_name}" if osm_name else "",
                                                tags.get("description", tags.get("note", "")),
                                                f"Maps: {gmaps}"]))
            wpts.append({"lat": poi_lat, "lon": poi_lon, "name": display[:30],
                         "sym": sym, "ctype": ctype, "cmt": gmaps,
                         "desc": desc, "type": typ})
            # Vorwarnpunkt
            if track_points and warn_dist_m > 0:
                best_d, best_i = float("inf"), 0
                for i, tp in enumerate(track_points):
                    d = haversine(poi_lat, poi_lon, tp["lat"], tp["lon"])
                    if d < best_d:
                        best_d, best_i = d, i
                if best_d <= 250:
                    acc, wi = 0.0, best_i
                    while wi > 0 and acc < warn_dist_m:
                        acc += haversine(track_points[wi]["lat"], track_points[wi]["lon"],
                                         track_points[wi-1]["lat"], track_points[wi-1]["lon"])
                        wi -= 1
                    if acc >= 30.0:
                        wpts.append({
                            "lat": track_points[wi]["lat"], "lon": track_points[wi]["lon"],
                            "name": f"{warn_dist_m}m! {display}"[:30],
                            "sym": "Danger Area", "ctype": "GENERIC",
                            "cmt": f"Warnpunkt {warn_dist_m}m vor: {display}",
                            "desc": f"{warn_dist_m}m vorher! {display}",
                            "type": f"{typ}_warn",
                        })
    return wpts


def write_gpx_with_waypoints(original_gpx_path, waypoints, out_path, overwrite_existing=False):
    with open(original_gpx_path, "r", encoding="utf-8") as f:
        content = f.read()
    if overwrite_existing:
        # Entfernt vorhandene <wpt>...</wpt> Blöcke (ohne Namespaces) aus dem Original
        content = re.sub(r"\s*<wpt\b[\s\S]*?</wpt>\s*", "\n", content, flags=re.IGNORECASE)
    wpt_lines = []
    for wp in waypoints:
        cmt_line = f'\n    <cmt>{_esc(wp.get("cmt",""))}</cmt>' if wp.get("cmt") else ""
        wpt_lines.append(
            f'  <wpt lat="{wp["lat"]:.7f}" lon="{wp["lon"]:.7f}">\n'
            f'    <name>{_esc(wp["name"])}</name>{cmt_line}\n'
            f'    <desc>{_esc(wp.get("desc",""))}</desc>\n'
            f'    <sym>{_esc(wp.get("sym","Waypoint"))}</sym>\n'
            f'    <type>{_esc(wp.get("ctype","GENERIC"))}</type>\n'
            f'  </wpt>'
        )
    wpt_str = "\n" + "\n".join(wpt_lines) + "\n"
    match = re.search(r'<(?:trk|rte)>|<(?:trk|rte)\s', content)
    pos   = match.start() if match else max(content.rfind("</gpx>"), 0)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content[:pos] + wpt_str + content[pos:])


def write_fit_course(route_name, track_points, cum_dists, waypoints, out_path):
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.course_message import CourseMessage
    from fit_tool.profile.messages.course_point_message import CoursePointMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer, Sport, CoursePoint

    TYPE_TO_CP = {
        "drinking_water": CoursePoint.WATER, "fountain": CoursePoint.WATER,
        "spring": CoursePoint.WATER, "water_tap": CoursePoint.WATER,
        "water_point": CoursePoint.WATER, "kneipp_water_cure": CoursePoint.WATER,
        "restaurant": CoursePoint.FOOD, "cafe": CoursePoint.FOOD,
        "food_court": CoursePoint.FOOD, "fast_food": CoursePoint.FOOD,
        "supermarket": CoursePoint.FOOD, "convenience": CoursePoint.FOOD,
        "health_food": CoursePoint.FOOD, "bakery": CoursePoint.FOOD, "organic": CoursePoint.FOOD,
    }

    FIT_EPOCH = 631065600
    SPEED     = 5.0
    now_fit   = int(datetime.now(timezone.utc).timestamp()) - FIT_EPOCH
    now_ms    = int(datetime.now(timezone.utc).timestamp() * 1000)

    MAX = 3000
    if len(track_points) > MAX:
        step = len(track_points) / MAX
        idxs = sorted(set(int(i*step) for i in range(MAX)))
        if 0 not in idxs: idxs.insert(0, 0)
        if len(track_points)-1 not in idxs: idxs.append(len(track_points)-1)
        fit_track = [(track_points[i], cum_dists[i]) for i in idxs]
    else:
        fit_track = list(zip(track_points, cum_dists))

    total_dist = cum_dists[-1]
    builder    = FitFileBuilder(auto_define=True, min_string_size=50)

    fid = FileIdMessage()
    fid.type = FileType.COURSE; fid.manufacturer = Manufacturer.GARMIN.value
    fid.product = 0; fid.time_created = now_ms; fid.serial_number = 0x12345678
    builder.add(fid)

    course = CourseMessage()
    course.course_name = (route_name or "Course")[:16]
    course.sport = Sport.CYCLING
    builder.add(course)

    for tp, dist in fit_track:
        rec = RecordMessage()
        rec.timestamp = (now_fit + int(dist/SPEED)) * 1000 + FIT_EPOCH * 1000
        rec.position_lat = tp["lat"]; rec.position_long = tp["lon"]
        rec.distance = dist
        builder.add(rec)

    total_sec = int(total_dist / SPEED)
    lap = LapMessage()
    lap.timestamp           = (now_fit + total_sec) * 1000 + FIT_EPOCH * 1000
    lap.start_time          = now_fit * 1000 + FIT_EPOCH * 1000
    lap.start_position_lat  = fit_track[0][0]["lat"]
    lap.start_position_long = fit_track[0][0]["lon"]
    lap.end_position_lat    = fit_track[-1][0]["lat"]
    lap.end_position_long   = fit_track[-1][0]["lon"]
    lap.total_distance      = total_dist
    lap.total_elapsed_time  = float(total_sec)
    lap.total_timer_time    = float(total_sec)
    builder.add(lap)

    # ── CoursePoints sortiert in FIT eintragen ─────────────────────────────
    # FIT-Spec: CoursePointMessages MÜSSEN aufsteigend nach distance sortiert
    # sein – sonst ignoriert Garmin sie stillschweigend!
    # nodes_to_waypoints liefert sie nach Typ gruppiert (alle Wasser, dann
    # alle Essen ...) → nicht nach Streckenposition → muss sortiert werden.
    #
    # Warn-Punkte (_warn) werden EBENFALLS als CoursePoints in die FIT geschrieben:
    # Sie liegen 100m vor dem eigentlichen POI und lösen den Garmin-Alert aus.
    #
    # GENERIC-Typ = auf den meisten Garmin Edge kein Audio-Alert.
    # Toiletten bekommen DANGER (triggert Ton + Popup).

    TYPE_TO_CP_ALERT = dict(TYPE_TO_CP)
    TYPE_TO_CP_ALERT["toilets"] = CoursePoint.DANGER  # DANGER = Ton auf Garmin

    pending_cps = []  # (cp_dist, CoursePointMessage)

    for wp in waypoints:   # alle inkl. _warn
        raw_type  = wp["type"]
        is_warn   = raw_type.endswith("_warn")
        base_type = raw_type[:-5] if is_warn else raw_type  # "_warn" abschneiden

        # Nächsten Punkt auf dem hochauflösenden Original-Track finden
        best_d, best_i = float("inf"), 0
        for i, tp in enumerate(track_points):
            d = haversine(wp["lat"], wp["lon"], tp["lat"], tp["lon"])
            if d < best_d:
                best_d, best_i = d, i

        # Warn-Punkte liegen bereits auf dem Track → engere Toleranz
        max_dist = 200 if is_warn else 500
        if best_d > max_dist:
            continue

        cp_dist = cum_dists[best_i]
        cp = CoursePointMessage()
        cp.timestamp         = (now_fit + int(cp_dist / SPEED)) * 1000 + FIT_EPOCH * 1000
        cp.position_lat      = wp["lat"]
        cp.position_long     = wp["lon"]
        cp.distance          = cp_dist
        cp.type              = TYPE_TO_CP_ALERT.get(base_type, CoursePoint.GENERIC)
        cp.course_point_name = truncate_utf8(wp["name"], 15)
        pending_cps.append((cp_dist, cp, TYPE_TO_CP_ALERT.get(base_type, CoursePoint.GENERIC)))

    # ── Garmin Edge: max. 100 Course Points ────────────────────────────────
    # Garmin Edge ignoriert stillschweigend alles über ~100 CoursePoints.
    # Priorität: WATER > FOOD > DANGER (Toiletten-Warn) > GENERIC
    # Bei Überschreitung zuerst GENERIC-Punkte entfernen, dann FOOD, nie WATER.
    GARMIN_CP_LIMIT = 100
    if len(pending_cps) > GARMIN_CP_LIMIT:
        def cp_priority(item):
            cp_type = item[2]
            if cp_type == CoursePoint.WATER:  return 0
            if cp_type == CoursePoint.FOOD:   return 1
            if cp_type == CoursePoint.DANGER: return 2  # Toiletten
            return 3  # GENERIC zuletzt
        # Sortiere nach Priorität, dann nach Distanz (frühere Punkte bevorzugt)
        pending_cps.sort(key=lambda x: (cp_priority(x), x[0]))
        removed = len(pending_cps) - GARMIN_CP_LIMIT
        pending_cps = pending_cps[:GARMIN_CP_LIMIT]
        # (log_fn nicht verfügbar hier – stille Kürzung ist OK)

    # Aufsteigend nach Streckendistanz sortieren (FIT-Pflicht)
    for cp_dist_val, cp, _ in sorted(pending_cps, key=lambda x: x[0]):
        builder.add(cp)

    builder.build().to_file(out_path)


# ─────────────────────────────────────────────
# Tour-Splitter
# ─────────────────────────────────────────────

def _bisect_cum_dists(cum_dists, target_m):
    """Binäre Suche: findet den Track-Index, dessen kumulative Distanz target_m am nächsten ist."""
    lo, hi = 0, len(cum_dists) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum_dists[mid] < target_m:
            lo = mid + 1
        else:
            hi = mid
    # lo ist der erste Index >= target_m; prüfe ob lo-1 näher ist
    if lo > 0 and abs(cum_dists[lo - 1] - target_m) < abs(cum_dists[lo] - target_m):
        return lo - 1
    return lo


def _find_nearest_track_idx(track_points, lat, lon):
    """Findet den nächsten Track-Punkt-Index zu einer gegebenen Koordinate."""
    best_d, best_i = float("inf"), 0
    for j, tp in enumerate(track_points):
        d = haversine(lat, lon, tp["lat"], tp["lon"])
        if d < best_d:
            best_d, best_i = d, j
    return best_i, best_d


def _precompute_water_at_track(track_points, water_pts, max_dist=1000):
    """Vorberechnung: für jeden Track-Punkt die Distanz zur nächsten Wasserquelle.

    Gibt ein Array zurück mit der Distanz in Metern (capped bei max_dist).
    So muss find_best_split nur noch per Index nachschlagen statt O(W) pro Kandidat.
    """
    n = len(track_points)
    water_dist = [max_dist] * n

    if not water_pts:
        return water_dist

    # Track-Punkte ausdünnen: nur jeden k-ten prüfen (nah beieinander = ähnliche Distanz)
    # und dann interpolieren für die dazwischen
    step = max(1, n // 500)  # ~500 Stichproben reichen für km-Genauigkeit
    sampled = list(range(0, n, step))
    if sampled[-1] != n - 1:
        sampled.append(n - 1)

    # Für die gesampelten Punkte: volle Berechnung
    sampled_dists = []
    for si in sampled:
        tp = track_points[si]
        closest = min(
            haversine(tp["lat"], tp["lon"], wlat, wlon)
            for wlat, wlon in water_pts
        )
        sampled_dists.append(min(closest, max_dist))

    # Interpolation zwischen gesampelten Werten
    for k in range(len(sampled) - 1):
        i0, i1 = sampled[k], sampled[k + 1]
        d0, d1 = sampled_dists[k], sampled_dists[k + 1]
        span = i1 - i0
        for j in range(i0, i1 + 1):
            t = (j - i0) / span if span > 0 else 0
            water_dist[j] = d0 + t * (d1 - d0)

    return water_dist


def split_tour_auto(track_points, cum_dists, n_days, log_fn=None, poi_wpts=None):
    """Intelligenter Etappen-Splitter.

    Kriterien (gewichtet):
    1. Distanz-Score: Abweichung vom Etappen-Ziel (dominanter Faktor)
    2. Lokales Höhenminimum: Übernachtung im Tal des aktuellen Suchfensters
       (nicht globales Minimum → verhindert dass alle Splits ins selbe Tal fallen)
    3. POI-Bonus: Splitpunkt nahe an Trinkwasser oder Unterstand (Campingspot)
    """
    total_km = cum_dists[-1] / 1000.0
    if log_fn:
        log_fn(f"  Gesamt: {total_km:.1f} km → {n_days} Etappen (Ø {total_km/n_days:.1f} km)")

    # Wasser- und Unterstand-POIs für Bonus-Bewertung
    water_pts = []
    if poi_wpts:
        water_pts = [
            (w["lat"], w["lon"]) for w in poi_wpts
            if w["type"] in ("drinking_water", "fountain", "spring",
                             "water_tap", "water_point", "shelter")
            and not w["type"].endswith("_warn")
        ]

    # Vorberechnung: Wasser-Distanz pro Track-Punkt (O(n*W) einmalig statt pro Kandidat)
    water_dist = _precompute_water_at_track(track_points, water_pts)

    def find_best_split(start_idx, target_km, is_first_day=False):
        target_m = target_km * 1000
        start_d  = cum_dists[start_idx]

        # Fenster-Grenzen
        lo = target_m * (0.65 if is_first_day else 0.78)
        hi = target_m * (0.92 if is_first_day else 1.22)

        # Binäre Suche für Fenster-Start und -Ende statt linearer Scan
        search_end_m = start_d + hi * 1.5
        window_end = _bisect_cum_dists(cum_dists, search_end_m)
        window_end = min(window_end, len(track_points) - 1)

        # Lokales Höhenminimum im Suchfenster berechnen
        window_pts    = track_points[start_idx:window_end + 1]
        local_ele_min = min(p["ele"] for p in window_pts) if window_pts else 0
        local_ele_max = max(p["ele"] for p in window_pts) if window_pts else 1
        local_range   = max(local_ele_max - local_ele_min, 1.0)

        # Binäre Suche für Startpunkt des Scoring-Fensters (ab lo * 0.5)
        scan_start = _bisect_cum_dists(cum_dists, start_d + lo * 0.5)
        scan_start = max(scan_start, start_idx + 1)

        best_idx, best_score = -1, float("inf")

        for i in range(scan_start, window_end + 1):
            seg = cum_dists[i] - start_d

            # 1. Distanz-Score [0..∞]: Abweichung vom Ziel
            if lo <= seg <= hi:
                dist_score = abs(seg - target_m) / target_m
            else:
                dist_score = 0.5 + abs(seg - target_m) / target_m

            # 2. Lokales Höhen-Score [0..1]: 0 = lokales Tal, 1 = lokale Kuppe
            ele_norm = (track_points[i]["ele"] - local_ele_min) / local_range

            # 3. POI-Bonus [-0.35..0]: vorberechnete Wasser-Distanz nachschlagen
            water_bonus = 0.0
            wd = water_dist[i]
            if wd < 1000:
                water_bonus = 0.35 * (1.0 - wd / 1000.0)

            score = dist_score + ele_norm * 0.4 - water_bonus
            if score < best_score:
                best_score, best_idx = score, i

        if best_idx == -1:
            best_idx = min(start_idx + 1, len(track_points) - 1)
        return best_idx

    splits, cur = [], 0
    for day in range(1, n_days):
        rem_km = (cum_dists[-1] - cum_dists[cur]) / 1000.0
        target = rem_km / (n_days - day + 1)
        nxt    = find_best_split(cur, target, is_first_day=(day == 1))
        splits.append(nxt)
        seg_km = (cum_dists[nxt] - cum_dists[cur]) / 1000.0
        # Nächste Wasserquelle vom Splitpunkt (vorberechnet)
        if water_pts and log_fn:
            closest_w = water_dist[nxt]
            water_info = f" | 💧 Wasser {closest_w:.0f}m" if closest_w < 1000 else ""
        else:
            water_info = ""
        if log_fn:
            log_fn(f"  📍 Etappe {day}: {seg_km:.1f} km  |  Split @ {cum_dists[nxt]/1000:.1f} km"
                   f"  |  Übernacht: {track_points[nxt]['ele']:.0f} m{water_info}")
        cur = nxt

    if log_fn:
        last_km = (cum_dists[-1] - cum_dists[cur]) / 1000.0
        log_fn(f"  📍 Etappe {n_days}: {last_km:.1f} km  |  Ziel: {track_points[-1]['ele']:.0f} m")
    return splits


def split_tour_manual(track_points, cum_dists, split_km_list):  # noqa: ARG001
    total_km = cum_dists[-1] / 1000.0

    # Sortieren, Werte außerhalb der Strecke verwerfen, Duplikate entfernen
    km_list = sorted(set(km for km in split_km_list if 0 < km < total_km))

    splits = []
    for km in km_list:
        target_m = km * 1000
        best_i = _bisect_cum_dists(cum_dists, target_m)
        if splits and best_i <= splits[-1]:
            continue
        splits.append(best_i)
    return splits


def extract_segment(track_points, cum_dists, start_idx, end_idx):
    seg_pts   = track_points[start_idx:end_idx + 1]
    seg_dists = [d - cum_dists[start_idx] for d in cum_dists[start_idx:end_idx + 1]]
    return seg_pts, seg_dists


def write_segment_gpx(seg_pts, route_name, out_path):
    root  = ET.Element("gpx", {"version":"1.1","creator":"GPX POI Tool",
                                "xmlns":"http://www.topografix.com/GPX/1/1"})
    trk   = ET.SubElement(root, "trk")
    ET.SubElement(trk, "name").text = route_name
    seg   = ET.SubElement(trk, "trkseg")
    for pt in seg_pts:
        tp = ET.SubElement(seg, "trkpt",
                           {"lat": f"{pt['lat']:.7f}", "lon": f"{pt['lon']:.7f}"})
        ET.SubElement(tp, "ele").text = f"{pt['ele']:.1f}"
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


def write_segment_fit(seg_pts, seg_dists, route_name, waypoints, out_path):
    """Wie write_fit_course, aber als Segment-Version mit Waypoints."""
    try:
        write_fit_course(route_name, seg_pts, seg_dists, waypoints, out_path)
        return True
    except Exception as e:
        return str(e)


# ══════════════════════════════════════════════
# GUI-Hilfsklassen
# ══════════════════════════════════════════════

class StravaButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", STRAVA_ORANGE)
        kwargs.setdefault("hover_color", STRAVA_HOVER)
        kwargs.setdefault("text_color", "#FFFFFF")
        kwargs.setdefault("font", ("Helvetica", 13, "bold"))
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("height", 38)
        super().__init__(master, **kwargs)


class StravaCard(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", STRAVA_CARD)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", STRAVA_BORDER)
        super().__init__(master, **kwargs)


# ══════════════════════════════════════════════
# Haupt-App
# ══════════════════════════════════════════════

TAB_NAMES = [
    "📂  Route",
    "⚙️  Einstellungen",
    "🔍  Suchen",
    "🗺  Karte & Filter",
    "✂  Tour aufteilen",
    "✅  Abschließen",
]
STEP_LABELS = [
    ("1", "Route laden"),
    ("2", "Einstellungen"),
    ("3", "POIs suchen"),
    ("4", "Karte & Filter"),
    ("5", "Tour aufteilen"),
    ("6", "Abschließen"),
]


class GPXPOIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GPX Route Planner  ·  for Garmin")
        self.geometry("1220x880")
        self.minsize(1020, 740)
        self.configure(fg_color=STRAVA_DARKER)

        self.gpx_path    = tk.StringVar()
        self.out_dir     = tk.StringVar(value=str(Path.home()))
        self.track_points = []
        self.cum_dists    = []
        self.route_name   = ""
        self.course_name_var = tk.StringVar()
        self.found_wpts   = []
        self.log_queue    = queue.Queue()
        self._cancel_ev   = threading.Event()

        self._build_ui()
        self._poll_log()
        self._set_step(0)

    # ──────────────────────────────────────────
    # UI aufbauen
    # ──────────────────────────────────────────

    def _build_ui(self):
        # Topbar
        topbar = ctk.CTkFrame(self, fg_color=STRAVA_DARK, height=52, corner_radius=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        lf = ctk.CTkFrame(topbar, fg_color="transparent")
        lf.pack(side="left", padx=20, pady=8)
        ctk.CTkFrame(lf, fg_color=STRAVA_ORANGE, width=5, height=32,
                     corner_radius=2).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(lf, text="GPX Route Planner",
                     font=("Helvetica", 17, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        ctk.CTkLabel(lf, text="  for Garmin",
                     font=("Helvetica", 12), text_color=STRAVA_MUTED).pack(side="left")
        ctk.CTkLabel(topbar, text="v2.1", font=("Helvetica", 10),
                     text_color=STRAVA_MUTED, fg_color=STRAVA_CARD,
                     corner_radius=4, padx=7, pady=2).pack(side="right", padx=16)

        # Schritt-Indikator
        step_bar = ctk.CTkFrame(self, fg_color=STRAVA_DARK, height=42, corner_radius=0)
        step_bar.pack(fill="x")
        step_bar.pack_propagate(False)
        self._step_badges = []
        self._step_lbls   = []
        inner = ctk.CTkFrame(step_bar, fg_color="transparent")
        inner.pack(expand=True)
        for i, (num, label) in enumerate(STEP_LABELS):
            sf = ctk.CTkFrame(inner, fg_color="transparent")
            sf.pack(side="left", padx=2)
            badge = ctk.CTkLabel(sf, text=num, width=24, height=24,
                                  corner_radius=12,
                                  font=("Helvetica", 10, "bold"),
                                  fg_color=STRAVA_BORDER, text_color=STRAVA_MUTED)
            badge.pack(side="left", padx=(0, 4))
            lbl = ctk.CTkLabel(sf, text=label, font=("Helvetica", 10),
                                text_color=STRAVA_MUTED)
            lbl.pack(side="left")
            self._step_badges.append(badge)
            self._step_lbls.append(lbl)
            if i < len(STEP_LABELS) - 1:
                ctk.CTkLabel(inner, text=" › ", font=("Helvetica", 13),
                              text_color=STRAVA_BORDER).pack(side="left")

        # Haupt-Layout
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # Sidebar
        sb = ctk.CTkFrame(main, fg_color=STRAVA_DARK, width=240, corner_radius=0)
        sb.pack(fill="y", side="left")
        sb.pack_propagate(False)
        self._build_sidebar(sb)

        # Tabs
        content = ctk.CTkFrame(main, fg_color=STRAVA_DARKER, corner_radius=0)
        content.pack(fill="both", expand=True, side="left")
        self.tabview = ctk.CTkTabview(
            content, fg_color=STRAVA_DARKER,
            segmented_button_fg_color=STRAVA_DARK,
            segmented_button_selected_color=STRAVA_ORANGE,
            segmented_button_selected_hover_color=STRAVA_HOVER,
            segmented_button_unselected_color=STRAVA_DARK,
            segmented_button_unselected_hover_color=STRAVA_CARD,
            text_color=STRAVA_TEXT,
            border_width=0, corner_radius=0,
        )
        self.tabview.pack(fill="both", expand=True)
        for name in TAB_NAMES:
            self.tabview.add(name)

        self._build_tab_route      (self.tabview.tab(TAB_NAMES[0]))
        self._build_tab_settings   (self.tabview.tab(TAB_NAMES[1]))
        self._build_tab_search     (self.tabview.tab(TAB_NAMES[2]))
        self._build_tab_map_filter (self.tabview.tab(TAB_NAMES[3]))
        self._build_tab_split      (self.tabview.tab(TAB_NAMES[4]))
        self._build_tab_finish     (self.tabview.tab(TAB_NAMES[5]))

    def _set_step(self, active):
        for i, (badge, lbl) in enumerate(zip(self._step_badges, self._step_lbls)):
            if i < active:
                badge.configure(fg_color="#1E3A12", text_color=STRAVA_GREEN)
                lbl.configure(text_color=STRAVA_GREEN, font=("Helvetica", 10))
            elif i == active:
                badge.configure(fg_color=STRAVA_ORANGE, text_color="#FFF")
                lbl.configure(text_color=STRAVA_TEXT, font=("Helvetica", 10, "bold"))
            else:
                badge.configure(fg_color=STRAVA_BORDER, text_color=STRAVA_MUTED)
                lbl.configure(text_color=STRAVA_MUTED, font=("Helvetica", 10))
        self.tabview.set(TAB_NAMES[active])

    # ── Sidebar ──────────────────────────────

    def _build_sidebar(self, sb):
        ctk.CTkLabel(sb, text="ROUTE", font=("Helvetica", 9, "bold"),
                     text_color=STRAVA_MUTED).pack(anchor="w", padx=18, pady=(20, 4))
        ctk.CTkFrame(sb, fg_color=STRAVA_BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=18, pady=(0, 10))

        fc = StravaCard(sb)
        fc.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(fc, text="GPX-Datei", font=("Helvetica", 11, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=12, pady=(10, 3))
        self.file_entry = ctk.CTkEntry(fc, textvariable=self.gpx_path,
                                        placeholder_text="Keine Datei gewählt",
                                        fg_color=STRAVA_CARD2, border_color=STRAVA_BORDER,
                                        text_color=STRAVA_TEXT,
                                        placeholder_text_color=STRAVA_MUTED, height=30)
        self.file_entry.pack(fill="x", padx=12, pady=(0, 5))
        StravaButton(fc, text="📂  GPX öffnen",
                     command=self._browse_gpx).pack(fill="x", padx=12, pady=(0, 10))

        sc = StravaCard(sb)
        sc.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(sc, text="ROUTENINFO", font=("Helvetica", 9, "bold"),
                     text_color=STRAVA_MUTED).pack(anchor="w", padx=12, pady=(10, 6))
        self.stat_dist  = self._srow(sc, "Distanz",     "– km")
        self.stat_elev  = self._srow(sc, "Höhenmeter",  "– m ↑")
        self.stat_pts   = self._srow(sc, "Punkte",      "–")
        self.stat_name  = self._srow(sc, "Name",        "–")
        ctk.CTkFrame(sc, fg_color="transparent", height=8).pack()

        oc = StravaCard(sb)
        oc.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(oc, text="AUSGABE", font=("Helvetica", 9, "bold"),
                     text_color=STRAVA_MUTED).pack(anchor="w", padx=12, pady=(10, 3))
        ctk.CTkEntry(oc, textvariable=self.out_dir,
                     fg_color=STRAVA_CARD2, border_color=STRAVA_BORDER,
                     text_color=STRAVA_TEXT, height=28).pack(fill="x", padx=12, pady=(0, 4))
        StravaButton(oc, text="📁  Ordner wählen",
                     fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                     border_width=1, border_color=STRAVA_BORDER,
                     command=self._browse_out).pack(fill="x", padx=12, pady=(0, 10))

    def _srow(self, parent, label, value):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(f, text=label, font=("Helvetica", 10),
                     text_color=STRAVA_MUTED, width=80, anchor="w").pack(side="left")
        lbl = ctk.CTkLabel(f, text=value, font=("Helvetica", 10, "bold"),
                            text_color=STRAVA_TEXT, anchor="e")
        lbl.pack(side="right")
        return lbl

    # ── Tab 1: Route ─────────────────────────

    def _build_tab_route(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)
        f = ctk.CTkFrame(tab, fg_color="transparent")
        f.pack(expand=True)
        ctk.CTkLabel(f, text="📂", font=("Helvetica", 64)).pack(pady=(0, 12))
        ctk.CTkLabel(f, text="GPX-Route laden",
                     font=("Helvetica", 22, "bold"),
                     text_color=STRAVA_TEXT).pack(pady=(0, 6))
        ctk.CTkLabel(f,
                     text="Wähle deine GPX-Datei – die App führt dich danach\n"
                          "Schritt für Schritt durch Suche, Split und Export.",
                     font=("Helvetica", 12), text_color=STRAVA_MUTED,
                     justify="center").pack(pady=(0, 28))
        StravaButton(f, text="  📂  GPX-Datei öffnen  ",
                     font=("Helvetica", 15, "bold"), height=52,
                     command=self._browse_gpx).pack(pady=(0, 16))
        ctk.CTkLabel(f, text="Unterstützte Formate: .gpx  (Track oder Route)",
                     font=("Helvetica", 11), text_color=STRAVA_MUTED).pack()

    # ── Tab 2: Einstellungen ─────────────────

    def _build_tab_settings(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)
        scroll = ctk.CTkScrollableFrame(tab, fg_color=STRAVA_DARKER)
        scroll.pack(fill="both", expand=True, padx=22, pady=16)

        ctk.CTkLabel(scroll, text="POI-Einstellungen",
                     font=("Helvetica", 20, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(scroll,
                     text="Welche Punkte sollen entlang der Route gesucht werden?",
                     font=("Helvetica", 12), text_color=STRAVA_MUTED).pack(anchor="w", pady=(0, 14))

        # ── POI-Checkboxen ───────────────────
        poi_card = StravaCard(scroll)
        poi_card.pack(fill="x", pady=(0, 14))

        hdr = ctk.CTkFrame(poi_card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="POI-Typen",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")

        # Alle / Keine
        for txt, val in [("Alle", True), ("Keine", False)]:
            v = val  # capture
            ctk.CTkButton(hdr, text=txt, width=56, height=24,
                           fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                           border_width=1, border_color=STRAVA_BORDER,
                           text_color=STRAVA_MUTED, font=("Helvetica", 10),
                           corner_radius=4,
                           command=lambda x=v: self._set_all_cats(x)
                           ).pack(side="right", padx=(4, 0))

        ctk.CTkFrame(poi_card, fg_color=STRAVA_BORDER,
                     height=1).pack(fill="x", padx=16, pady=(4, 0))

        self.poi_vars = {}  # osm_key → BooleanVar

        # Hilfswörterbuch für schnellen Zugriff
        item_by_key = {key: (label, query, default)
                       for label, key, query, default in POI_ITEMS}

        for grp_label, keys in POI_GROUPS:
            # Gruppen-Header
            gh = ctk.CTkFrame(poi_card, fg_color="transparent")
            gh.pack(fill="x", padx=16, pady=(10, 3))
            ctk.CTkLabel(gh, text=grp_label,
                         font=("Helvetica", 10, "bold"),
                         text_color=STRAVA_ORANGE).pack(side="left")

            # Items dieser Gruppe
            grp_frame = ctk.CTkFrame(poi_card, fg_color=STRAVA_CARD2,
                                      corner_radius=8)
            grp_frame.pack(fill="x", padx=16, pady=(0, 2))

            for i, key in enumerate(keys):
                label, _query, default = item_by_key[key]
                var = tk.BooleanVar(value=default)
                self.poi_vars[key] = var

                if i > 0:
                    ctk.CTkFrame(grp_frame, fg_color=STRAVA_BORDER,
                                  height=1).pack(fill="x", padx=12)

                ctk.CTkCheckBox(grp_frame, text=label, variable=var,
                                 fg_color=STRAVA_ORANGE,
                                 hover_color=STRAVA_HOVER,
                                 checkmark_color=STRAVA_TEXT,
                                 border_color=STRAVA_BORDER,
                                 text_color=STRAVA_TEXT,
                                 font=("Helvetica", 12)
                                 ).pack(anchor="w", padx=14, pady=5)

        ctk.CTkFrame(poi_card, fg_color="transparent", height=8).pack()

        # ── Radius-Slider (50 m Snapping) ────
        rad_card = StravaCard(scroll)
        rad_card.pack(fill="x", pady=(0, 14))
        rh = ctk.CTkFrame(rad_card, fg_color="transparent")
        rh.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(rh, text="Suchradius",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        self.radius_label = ctk.CTkLabel(rh, text="250 m",
                                          font=("Helvetica", 13, "bold"),
                                          text_color=STRAVA_ORANGE)
        self.radius_label.pack(side="right")

        self.radius_var = tk.IntVar(value=250)
        # 50 → 1000  in 50er-Schritten = 19 Stufen
        ctk.CTkSlider(rad_card, from_=50, to=1000, number_of_steps=19,
                       variable=self.radius_var,
                       fg_color=STRAVA_CARD2, progress_color=STRAVA_ORANGE,
                       button_color=STRAVA_ORANGE, button_hover_color=STRAVA_HOVER,
                       command=self._on_radius_slide,
                       ).pack(fill="x", padx=16, pady=(0, 4))
        tick = ctk.CTkFrame(rad_card, fg_color="transparent")
        tick.pack(fill="x", padx=16, pady=(0, 12))
        # Tick-Werte entsprechen den tatsächlichen Slider-Positionen (50–1000, linear)
        # 0%=50m  25%=287m  50%=525m  75%=762m  100%=1000m
        for t in ["50 m", "300 m", "525 m", "750 m", "1 km"]:
            ctk.CTkLabel(tick, text=t, font=("Helvetica", 9),
                         text_color=STRAVA_MUTED).pack(side="left", expand=True)

        # ── Vorwarn-Distanz (0 = aus) ────────
        warn_card = StravaCard(scroll)
        warn_card.pack(fill="x", pady=(0, 14))
        wh = ctk.CTkFrame(warn_card, fg_color="transparent")
        wh.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkLabel(wh, text="Vorwarn-Distanz",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        self.warn_label = ctk.CTkLabel(wh, text="100 m",
                                        font=("Helvetica", 13, "bold"),
                                        text_color=STRAVA_WARN)
        self.warn_label.pack(side="right")
        ctk.CTkLabel(warn_card,
                     text="Garmin gibt X Meter vor dem POI eine Ansage  (0 = deaktiviert)",
                     font=("Helvetica", 11), text_color=STRAVA_MUTED
                     ).pack(anchor="w", padx=16)
        self.warn_var = tk.IntVar(value=100)
        # 0, 50, 100 … 500  → 10 Stufen
        ctk.CTkSlider(warn_card, from_=0, to=500, number_of_steps=10,
                       variable=self.warn_var,
                       fg_color=STRAVA_CARD2, progress_color=STRAVA_WARN,
                       button_color=STRAVA_WARN, button_hover_color="#E67E22",
                       command=self._on_warn_slide,
                       ).pack(fill="x", padx=16, pady=(4, 4))
        wt = ctk.CTkFrame(warn_card, fg_color="transparent")
        wt.pack(fill="x", padx=16, pady=(0, 12))
        # Tick-Werte entsprechen den tatsächlichen Slider-Positionen (0–500, linear)
        # 0%=0m  20%=100m  40%=200m  60%=300m  80%=400m  100%=500m
        for t in ["Aus", "100 m", "200 m", "300 m", "400 m", "500 m"]:
            ctk.CTkLabel(wt, text=t, font=("Helvetica", 9),
                         text_color=STRAVA_MUTED).pack(side="left", expand=True)

        # ── Stützpunkt-Abstand (Sampling) ───
        samp_card = StravaCard(scroll)
        samp_card.pack(fill="x", pady=(0, 14))
        sh = ctk.CTkFrame(samp_card, fg_color="transparent")
        sh.pack(fill="x", padx=16, pady=(12, 2))
        ctk.CTkLabel(sh, text="Stützpunkt-Abstand",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        self.sample_label = ctk.CTkLabel(sh, text="Auto (200 m)",
                                          font=("Helvetica", 13, "bold"),
                                          text_color=STRAVA_BLUE)
        self.sample_label.pack(side="right")
        ctk.CTkLabel(samp_card,
                     text="Kleiner = genauer & langsamer, größer = schneller",
                     font=("Helvetica", 11), text_color=STRAVA_MUTED
                     ).pack(anchor="w", padx=16)

        self.sample_mode = tk.StringVar(value="auto")
        self.sample_var = tk.IntVar(value=adaptive_sample_step(self.radius_var.get()))

        mode_row = ctk.CTkFrame(samp_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkRadioButton(mode_row, text="Auto",
                           variable=self.sample_mode, value="auto",
                           fg_color=STRAVA_BLUE, hover_color=STRAVA_HOVER,
                           text_color=STRAVA_TEXT,
                           font=("Helvetica", 11),
                           command=self._toggle_sample_mode
                           ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(mode_row, text="Manuell",
                           variable=self.sample_mode, value="manual",
                           fg_color=STRAVA_BLUE, hover_color=STRAVA_HOVER,
                           text_color=STRAVA_TEXT,
                           font=("Helvetica", 11),
                           command=self._toggle_sample_mode
                           ).pack(side="left")

        self.sample_slider = ctk.CTkSlider(
            samp_card, from_=100, to=1200, number_of_steps=22,
            variable=self.sample_var,
            fg_color=STRAVA_CARD2, progress_color=STRAVA_BLUE,
            button_color=STRAVA_BLUE, button_hover_color=STRAVA_HOVER,
            command=self._on_sample_slide,
        )
        self.sample_slider.pack(fill="x", padx=16, pady=(4, 4))
        st = ctk.CTkFrame(samp_card, fg_color="transparent")
        st.pack(fill="x", padx=16, pady=(0, 12))
        for t in ["100 m", "300 m", "500 m", "800 m", "1.2 km"]:
            ctk.CTkLabel(st, text=t, font=("Helvetica", 9),
                         text_color=STRAVA_MUTED).pack(side="left", expand=True)
        # initial state
        self._toggle_sample_mode()

        # ── Ausgabe-Optionen ─────────────────
        out_card = StravaCard(scroll)
        out_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(out_card, text="Ausgabe-Formate",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 8))

        # Course Name für FIT-Export
        cn_row = ctk.CTkFrame(out_card, fg_color="transparent")
        cn_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(cn_row, text="Course Name (FIT):",
                     font=("Helvetica", 12), text_color=STRAVA_TEXT).pack(side="left")
        ctk.CTkLabel(cn_row, text="max 16 Zeichen",
                     font=("Helvetica", 9), text_color=STRAVA_MUTED).pack(side="right")
        self.course_name_entry = ctk.CTkEntry(
            out_card, textvariable=self.course_name_var,
            placeholder_text="wird aus GPX-Route übernommen",
            fg_color=STRAVA_CARD2, border_color=STRAVA_BORDER,
            text_color=STRAVA_TEXT, placeholder_text_color=STRAVA_MUTED,
            font=("Helvetica", 13), height=36)
        self.course_name_entry.pack(fill="x", padx=16, pady=(0, 10))

        self.var_fit = tk.BooleanVar(value=True)
        self.var_gpx = tk.BooleanVar(value=True)
        self.var_overwrite_wpt = tk.BooleanVar(value=True)
        orow = ctk.CTkFrame(out_card, fg_color="transparent")
        orow.pack(fill="x", padx=16, pady=(0, 12))
        for var, lbl in [(self.var_fit, "FIT-Datei (Garmin Edge)"),
                         (self.var_gpx, "GPX mit Wegpunkten")]:
            ctk.CTkCheckBox(orow, text=lbl, variable=var,
                             fg_color=STRAVA_ORANGE, hover_color=STRAVA_HOVER,
                             text_color=STRAVA_TEXT,
                             font=("Helvetica", 12)).pack(side="left", padx=12)
        ctk.CTkCheckBox(out_card, text="Vorhandene POIs überschreiben",
                         variable=self.var_overwrite_wpt,
                         fg_color=STRAVA_ORANGE, hover_color=STRAVA_HOVER,
                         text_color=STRAVA_TEXT,
                         font=("Helvetica", 11)
                         ).pack(anchor="w", padx=16, pady=(0, 12))

        # Weiter
        StravaButton(scroll, text="Weiter  →  POIs suchen",
                     font=("Helvetica", 13, "bold"), height=44,
                     command=lambda: self._set_step(2)).pack(fill="x", pady=(4, 0))

    # ── Tab 3: Suchen ────────────────────────

    def _build_tab_search(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)
        scroll = ctk.CTkScrollableFrame(tab, fg_color=STRAVA_DARKER)
        scroll.pack(fill="both", expand=True, padx=22, pady=16)

        ctk.CTkLabel(scroll, text="POIs suchen",
                     font=("Helvetica", 20, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(scroll,
                     text="Fragt OpenStreetMap (Overpass API) entlang der Route ab.",
                     font=("Helvetica", 12), text_color=STRAVA_MUTED).pack(anchor="w", pady=(0, 14))

        # Einstellungs-Zusammenfassung
        sc = StravaCard(scroll)
        sc.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(sc, text="Aktuelle Einstellungen",
                     font=("Helvetica", 12, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self.summary_lbl = ctk.CTkLabel(sc, text="–",
                                         font=("Helvetica", 11), text_color=STRAVA_MUTED,
                                         justify="left")
        self.summary_lbl.pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkButton(sc, text="← Einstellungen ändern", width=180, height=26,
                       fg_color="transparent", hover_color=STRAVA_CARD,
                       text_color=STRAVA_ORANGE, font=("Helvetica", 11),
                       command=lambda: self._set_step(1)
                       ).pack(anchor="w", padx=12, pady=(0, 10))

        # Buttons
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))
        self.search_btn = StravaButton(
            btn_row, text="🔍  POIs suchen & Dateien erstellen",
            font=("Helvetica", 14, "bold"), height=50,
            command=self._start_poi_search)
        self.search_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cancel_btn = StravaButton(
            btn_row, text="⛔ Abbrechen",
            fg_color="#4A2020", hover_color="#6A3030",
            font=("Helvetica", 12, "bold"), height=50, width=140,
            state="disabled", command=self._cancel_search)
        self.cancel_btn.pack(side="left")

        # Progress
        self.poi_progress = ctk.CTkProgressBar(scroll,
                                                fg_color=STRAVA_CARD,
                                                progress_color=STRAVA_ORANGE, height=7)
        self.poi_progress.pack(fill="x", pady=(0, 4))
        self.poi_progress.set(0)
        self.poi_status = ctk.CTkLabel(scroll, text="Bereit.",
                                        font=("Helvetica", 11), text_color=STRAVA_MUTED)
        self.poi_status.pack(anchor="w", pady=(0, 14))

        # Ergebnis
        rc = StravaCard(scroll)
        rc.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(rc, text="Suchergebnis",
                     font=("Helvetica", 12, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self.result_lbl = ctk.CTkLabel(rc, text="Noch keine Suche durchgeführt.",
                                        font=("Helvetica", 11), text_color=STRAVA_MUTED)
        self.result_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # Weiter
        StravaButton(scroll, text="Weiter  →  Karte & Filter",
                     font=("Helvetica", 13, "bold"), height=44,
                     fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                     border_width=1, border_color=STRAVA_BORDER,
                     command=lambda: self._set_step(3)).pack(fill="x")

    # ── Tab 4: Karte & POI-Filter ──────────

    def _build_tab_map_filter(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)

        # Hauptlayout: Links Karte, rechts Filter-Panel
        main = ctk.CTkFrame(tab, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=10)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # ── Linke Seite: Karte ──
        map_frame = ctk.CTkFrame(main, fg_color=STRAVA_CARD, corner_radius=10)
        map_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        map_frame.grid_rowconfigure(1, weight=1)
        map_frame.grid_columnconfigure(0, weight=1)

        # Karten-Header
        mh = ctk.CTkFrame(map_frame, fg_color="transparent")
        mh.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(mh, text="🗺  Route & POIs",
                     font=("Helvetica", 15, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        self._map_status = ctk.CTkLabel(mh, text="Keine POIs geladen",
                                         font=("Helvetica", 10),
                                         text_color=STRAVA_MUTED)
        self._map_status.pack(side="right")

        # Karte
        self._map_widget = tkintermapview.TkinterMapView(
            map_frame, corner_radius=8)
        self._map_widget.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._map_widget.set_tile_server(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self._map_widget.set_position(47.5, 13.0)  # Österreich default
        self._map_widget.set_zoom(6)

        # Interne State-Listen für Marker
        self._map_markers = []       # Liste von (marker_obj, wpt_index)
        self._map_path = None        # Polyline-Objekt
        self._poi_enabled = []       # bool pro POI (parallel zu found_wpts)
        self._map_right_click_tol_m = 80  # Klick-Toleranz zum nächsten POI
        self._map_hover_tol_m = 60
        self._delete_popup = None
        self._delete_popup_idx = None
        self._hover_poi_idx = None

        # Rechtsklick: POI in der Nähe löschen
        try:
            # ohne add="+" damit wir die Default-Right-Click-Coords unterdrücken
            self._map_widget.canvas.bind("<Button-3>", self._on_map_right_click)
            self._map_widget.canvas.bind("<Button-1>", self._on_map_left_click, add="+")
            self._map_widget.canvas.bind("<Motion>", self._on_map_motion, add="+")
            self._map_widget.canvas.bind("<Leave>", self._on_map_leave, add="+")
        except Exception:
            # Fallback: wenn canvas nicht verfügbar ist, still ignorieren
            pass

        # ── Rechte Seite: Filter-Panel ──
        filter_frame = ctk.CTkFrame(main, fg_color=STRAVA_CARD, corner_radius=10)
        filter_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        filter_frame.grid_rowconfigure(2, weight=1)
        filter_frame.grid_columnconfigure(0, weight=1)

        # Filter-Header
        fh = ctk.CTkFrame(filter_frame, fg_color="transparent")
        fh.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(fh, text="POI-Filter",
                     font=("Helvetica", 14, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        self._filter_count_lbl = ctk.CTkLabel(
            fh, text="0 / 0", font=("Helvetica", 11, "bold"),
            text_color=STRAVA_ORANGE)
        self._filter_count_lbl.pack(side="right")

        # Schnell-Buttons
        btn_row = ctk.CTkFrame(filter_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkButton(btn_row, text="Alle", width=60, height=26,
                       fg_color=STRAVA_GREEN, hover_color="#27AE60",
                       text_color="#FFF", font=("Helvetica", 10, "bold"),
                       corner_radius=4,
                       command=lambda: self._set_all_pois_enabled(True)
                       ).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Keine", width=60, height=26,
                       fg_color="#E74C3C", hover_color="#C0392B",
                       text_color="#FFF", font=("Helvetica", 10, "bold"),
                       corner_radius=4,
                       command=lambda: self._set_all_pois_enabled(False)
                       ).pack(side="left", padx=2)

        # Kategorie-Filter Buttons
        self._cat_filter_btns = {}
        cat_row = ctk.CTkFrame(filter_frame, fg_color="transparent")
        cat_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(28, 4))
        for grp_label, grp_keys in POI_GROUPS:
            emoji = grp_label.split()[0]
            btn = ctk.CTkButton(
                cat_row, text=emoji, width=32, height=26,
                fg_color=STRAVA_CARD2, hover_color=STRAVA_BORDER,
                text_color=STRAVA_TEXT, font=("Helvetica", 12),
                corner_radius=4,
                command=lambda keys=grp_keys: self._toggle_category(keys))
            btn.pack(side="left", padx=1)
            for k in grp_keys:
                self._cat_filter_btns[k] = btn

        # Scrollbare POI-Liste
        self._poi_list_frame = ctk.CTkScrollableFrame(
            filter_frame, fg_color=STRAVA_CARD,
            scrollbar_button_color=STRAVA_BORDER,
            scrollbar_button_hover_color=STRAVA_MUTED)
        self._poi_list_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(4, 6))
        self._poi_list_frame.grid_columnconfigure(0, weight=1)
        self._poi_cb_vars = []    # tk.BooleanVar pro POI
        self._poi_cb_widgets = [] # Checkbox-Widgets

        # Platzhalter-Text
        self._poi_list_placeholder = ctk.CTkLabel(
            self._poi_list_frame, text="Zuerst POIs suchen\n(Tab 3)",
            font=("Helvetica", 12), text_color=STRAVA_MUTED)
        self._poi_list_placeholder.pack(pady=30)

        # Navigation
        nav = ctk.CTkFrame(filter_frame, fg_color="transparent")
        nav.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        StravaButton(nav, text="Weiter → Tour aufteilen",
                     font=("Helvetica", 12, "bold"), height=38,
                     command=lambda: self._set_step(4)).pack(fill="x", pady=(0, 4))
        ctk.CTkButton(nav, text="← Zurück zur Suche", width=180, height=26,
                       fg_color="transparent", hover_color=STRAVA_CARD2,
                       text_color=STRAVA_ORANGE, font=("Helvetica", 10),
                       command=lambda: self._set_step(2)).pack(fill="x")

    # ── Tab 5: Tour aufteilen ────────────────

    def _build_tab_split(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)
        scroll = ctk.CTkScrollableFrame(tab, fg_color=STRAVA_DARKER)
        scroll.pack(fill="both", expand=True, padx=22, pady=16)

        ctk.CTkLabel(scroll, text="Tour in Etappen aufteilen",
                     font=("Helvetica", 20, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(scroll,
                     text="Optional: Erstellt separate FIT & GPX Dateien pro Etappe.",
                     font=("Helvetica", 12), text_color=STRAVA_MUTED).pack(anchor="w", pady=(0, 14))

        # Modus
        mc = StravaCard(scroll)
        mc.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(mc, text="Aufteilungsmodus",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 8))
        self.split_mode = tk.StringVar(value="auto")
        mr = ctk.CTkFrame(mc, fg_color="transparent")
        mr.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkRadioButton(mr, text="🤖  Automatisch optimieren",
                            variable=self.split_mode, value="auto",
                            fg_color=STRAVA_ORANGE, hover_color=STRAVA_HOVER,
                            text_color=STRAVA_TEXT, font=("Helvetica", 12),
                            command=self._toggle_split_mode).pack(side="left", padx=(0, 24))
        ctk.CTkRadioButton(mr, text="✏️  Manuell eingeben",
                            variable=self.split_mode, value="manual",
                            fg_color=STRAVA_ORANGE, hover_color=STRAVA_HOVER,
                            text_color=STRAVA_TEXT, font=("Helvetica", 12),
                            command=self._toggle_split_mode).pack(side="left")

        # Auto
        self.auto_card = StravaCard(scroll)
        self.auto_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(self.auto_card, text="🤖  Automatische Optimierung",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 6))
        dr = ctk.CTkFrame(self.auto_card, fg_color="transparent")
        dr.pack(fill="x", padx=16)
        ctk.CTkLabel(dr, text="Anzahl Etappen:",
                     font=("Helvetica", 12), text_color=STRAVA_TEXT).pack(side="left")
        self.days_label = ctk.CTkLabel(dr, text="4",
                                        font=("Helvetica", 14, "bold"),
                                        text_color=STRAVA_ORANGE)
        self.days_label.pack(side="right")
        self.days_var = tk.IntVar(value=4)
        ctk.CTkSlider(self.auto_card, from_=2, to=14, number_of_steps=12,
                       variable=self.days_var,
                       fg_color=STRAVA_CARD2, progress_color=STRAVA_ORANGE,
                       button_color=STRAVA_ORANGE, button_hover_color=STRAVA_HOVER,
                       command=lambda v: self.days_label.configure(text=str(int(v)))
                       ).pack(fill="x", padx=16, pady=(4, 4))
        dt = ctk.CTkFrame(self.auto_card, fg_color="transparent")
        dt.pack(fill="x", padx=16, pady=(0, 6))
        for v in ["2", "4", "7", "10", "14"]:
            ctk.CTkLabel(dt, text=v, font=("Helvetica", 9),
                         text_color=STRAVA_MUTED).pack(side="left", expand=True)
        opt_f = ctk.CTkFrame(self.auto_card, fg_color=STRAVA_CARD2, corner_radius=8)
        opt_f.pack(fill="x", padx=16, pady=(0, 12))
        for icon, txt in [("🏔", "Tag 1 kürzer / leichter starten"),
                           ("🏕", "Übernachtung in möglichst tiefer Lage"),
                           ("⚖", "Gleichmäßige Distanz- & Höhenmeter-Verteilung")]:
            r = ctk.CTkFrame(opt_f, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(r, text=icon, font=("Helvetica", 13)).pack(side="left", padx=(0,6))
            ctk.CTkLabel(r, text=txt, font=("Helvetica", 11),
                         text_color=STRAVA_MUTED).pack(side="left")
        ctk.CTkFrame(opt_f, fg_color="transparent", height=6).pack()

        # Manuell
        self.manual_card = StravaCard(scroll)
        self.manual_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(self.manual_card, text="✏️  Manuelle Split-Punkte",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(self.manual_card,
                     text='Kilometer-Werte getrennt durch  " – "  oder Komma:',
                     font=("Helvetica", 11), text_color=STRAVA_MUTED
                     ).pack(anchor="w", padx=16, pady=(0, 4))
        self.manual_entry = ctk.CTkEntry(
            self.manual_card,
            placeholder_text="z. B.   110 – 235 – 345   oder   110, 235, 345",
            fg_color=STRAVA_CARD2, border_color=STRAVA_BORDER,
            text_color=STRAVA_TEXT, placeholder_text_color=STRAVA_MUTED,
            font=("Helvetica", 13), height=40)
        self.manual_entry.pack(fill="x", padx=16, pady=(0, 8))
        hint = ctk.CTkFrame(self.manual_card, fg_color="#1C2A1C",
                             corner_radius=6, border_width=1, border_color="#2E4A2E")
        hint.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(hint,
                     text='💡  Letzten Wert weglassen oder "Ende" schreiben = automatisch bis Streckenende',
                     font=("Helvetica", 10), text_color="#7EC87E").pack(padx=12, pady=6)

        # Vorschau
        pv = StravaCard(scroll)
        pv.pack(fill="x", pady=(0, 14))
        ph = ctk.CTkFrame(pv, fg_color="transparent")
        ph.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(ph, text="Etappen-Vorschau",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left")
        ctk.CTkButton(ph, text="Berechnen", width=96, height=28,
                       fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                       border_width=1, border_color=STRAVA_ORANGE,
                       text_color=STRAVA_ORANGE, font=("Helvetica", 11, "bold"),
                       corner_radius=4, command=self._preview_split).pack(side="right")
        self.preview_inner = ctk.CTkFrame(pv, fg_color="transparent")
        self.preview_inner.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(self.preview_inner,
                     text="GPX laden → 'Berechnen' drücken",
                     font=("Helvetica", 11), text_color=STRAVA_MUTED).pack(pady=8)

        # Ausgabe-Format
        so = StravaCard(scroll)
        so.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(so, text="Ausgabe-Formate",
                     font=("Helvetica", 13, "bold"),
                     text_color=STRAVA_TEXT).pack(anchor="w", padx=16, pady=(12, 8))
        self.var_split_fit = tk.BooleanVar(value=True)
        self.var_split_gpx = tk.BooleanVar(value=True)
        sr = ctk.CTkFrame(so, fg_color="transparent")
        sr.pack(fill="x", padx=16, pady=(0, 12))
        for var, lbl in [(self.var_split_fit, "FIT-Dateien (Garmin)"),
                         (self.var_split_gpx, "GPX-Dateien")]:
            ctk.CTkCheckBox(sr, text=lbl, variable=var,
                             fg_color=STRAVA_ORANGE, hover_color=STRAVA_HOVER,
                             text_color=STRAVA_TEXT,
                             font=("Helvetica", 12)).pack(side="left", padx=12)

        # Aufteilen-Button
        self.split_btn = StravaButton(scroll,
                                       text="✂  Tour aufteilen & Dateien erstellen",
                                       font=("Helvetica", 14, "bold"), height=50,
                                       command=self._start_split)
        self.split_btn.pack(fill="x", pady=(0, 8))
        self.split_progress = ctk.CTkProgressBar(scroll,
                                                   fg_color=STRAVA_CARD,
                                                   progress_color=STRAVA_ORANGE, height=7)
        self.split_progress.pack(fill="x", pady=(0, 4))
        self.split_progress.set(0)
        self.split_status = ctk.CTkLabel(scroll, text="Bereit.",
                                          font=("Helvetica", 11), text_color=STRAVA_MUTED)
        self.split_status.pack(anchor="w", pady=(0, 8))

        StravaButton(scroll, text="Weiter  →  Abschließen",
                     font=("Helvetica", 13, "bold"), height=44,
                     fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                     border_width=1, border_color=STRAVA_BORDER,
                     command=lambda: self._set_step(5)).pack(fill="x")

        self._toggle_split_mode()

    # ── Tab 6: Abschließen ───────────────────

    def _build_tab_finish(self, tab):
        tab.configure(fg_color=STRAVA_DARKER)
        f = ctk.CTkFrame(tab, fg_color="transparent")
        f.pack(expand=True)
        ctk.CTkLabel(f, text="✅", font=("Helvetica", 58)).pack(pady=(0, 8))
        ctk.CTkLabel(f, text="Fertig!",
                     font=("Helvetica", 26, "bold"),
                     text_color=STRAVA_TEXT).pack(pady=(0, 6))
        self.finish_info = ctk.CTkLabel(f, text="Alle Dateien wurden erstellt.",
                                         font=("Helvetica", 13), text_color=STRAVA_MUTED)
        self.finish_info.pack(pady=(0, 28))

        brow = ctk.CTkFrame(f, fg_color="transparent")
        brow.pack()
        StravaButton(brow, text="📁  Ausgabe-Ordner öffnen",
                     font=("Helvetica", 13, "bold"), height=46, width=230,
                     command=self._open_output_folder).pack(side="left", padx=5)
        StravaButton(brow, text="🔄  Neue Route laden",
                     fg_color=STRAVA_CARD2, hover_color=STRAVA_CARD,
                     border_width=1, border_color=STRAVA_BORDER,
                     font=("Helvetica", 13, "bold"), height=46, width=185,
                     command=self._restart).pack(side="left", padx=5)
        StravaButton(brow, text="✖  Beenden",
                     fg_color="#3A1010", hover_color="#5A2020",
                     font=("Helvetica", 13, "bold"), height=46, width=130,
                     command=self.destroy).pack(side="left", padx=5)

    # ──────────────────────────────────────────
    # Aktionen
    # ──────────────────────────────────────────

    def _browse_gpx(self):
        path = filedialog.askopenfilename(
            title="GPX-Datei auswählen",
            filetypes=[("GPX-Dateien", "*.gpx"), ("Alle Dateien", "*.*")]
        )
        if path:
            self.gpx_path.set(path)
            self._load_gpx(path)

    def _browse_out(self):
        d = filedialog.askdirectory(title="Ausgabe-Ordner wählen")
        if d:
            self.out_dir.set(d)

    def _load_gpx(self, path):
        self._log(f"📂 Lade: {os.path.basename(path)}")
        try:
            pts, name = parse_gpx(path)
            if not pts:
                raise ValueError("Keine Track- oder Routenpunkte in der GPX gefunden.")
            self.track_points = pts
            self.cum_dists    = compute_cumulative_distances(pts)
            self.route_name   = name
            self.course_name_var.set((name or "")[:16])
            total_km = self.cum_dists[-1] / 1000
            gain     = compute_elevation_gain(pts)
            self.stat_dist.configure(text=f"{total_km:.1f} km")
            self.stat_elev.configure(text=f"{gain:.0f} m ↑")
            self.stat_pts.configure(text=f"{len(pts):,}")
            self.stat_name.configure(text=(name[:20]+"…" if len(name)>20 else name) or "–")
            self.out_dir.set(os.path.dirname(os.path.abspath(path)))
            self._log(f"  ✅ {len(pts)} Punkte | {total_km:.1f} km | {gain:.0f} m Hm")
            self._set_step(1)
        except Exception as e:
            self._log(f"  ❌ {e}")
            messagebox.showerror("Fehler", f"GPX konnte nicht gelesen werden:\n{e}")

    def _on_radius_slide(self, v):
        snapped = max(50, min(1000, round(v / 50) * 50))
        self.radius_var.set(snapped)
        self.radius_label.configure(text=f"{snapped} m")
        if self.sample_mode.get() == "auto":
            auto_step = adaptive_sample_step(snapped)
            self.sample_var.set(auto_step)
            self.sample_label.configure(text=f"Auto ({auto_step} m)")

    def _on_warn_slide(self, v):
        snapped = max(0, min(500, round(v / 50) * 50))
        self.warn_var.set(snapped)
        if snapped == 0:
            self.warn_label.configure(text="Aus", text_color=STRAVA_MUTED)
        else:
            self.warn_label.configure(text=f"{snapped} m", text_color=STRAVA_WARN)

    def _on_sample_slide(self, v):
        snapped = max(100, min(1200, round(v / 50) * 50))
        self.sample_var.set(snapped)
        if self.sample_mode.get() == "manual":
            self.sample_label.configure(text=f"{snapped} m", text_color=STRAVA_BLUE)

    def _toggle_sample_mode(self):
        if self.sample_mode.get() == "auto":
            auto_step = adaptive_sample_step(self.radius_var.get())
            self.sample_var.set(auto_step)
            self.sample_label.configure(text=f"Auto ({auto_step} m)", text_color=STRAVA_BLUE)
            self.sample_slider.configure(state="disabled")
        else:
            self.sample_label.configure(text=f"{self.sample_var.get()} m", text_color=STRAVA_BLUE)
            self.sample_slider.configure(state="normal")

    def _set_all_cats(self, val):
        for var in self.poi_vars.values():
            var.set(val)

    def _toggle_split_mode(self):
        is_auto = self.split_mode.get() == "auto"
        self.auto_card.configure(border_color=STRAVA_ORANGE if is_auto else STRAVA_BORDER)
        self.manual_card.configure(border_color=STRAVA_ORANGE if not is_auto else STRAVA_BORDER)

    def _update_summary(self):
        selected = [lbl for lbl, key, *_ in POI_ITEMS
                    if self.poi_vars.get(key, tk.BooleanVar(value=False)).get()]
        r = self.radius_var.get()
        w = self.warn_var.get()
        if self.sample_mode.get() == "auto":
            s = f"Auto ({self.sample_var.get()} m)"
        else:
            s = f"{self.sample_var.get()} m"
        w_str = f"{w} m vor POI" if w > 0 else "deaktiviert"
        cat_str = ", ".join(selected[:5])
        if len(selected) > 5:
            cat_str += f" … +{len(selected)-5} weitere"
        if not selected:
            cat_str = "⚠️  Keine Kategorie ausgewählt!"
        self.summary_lbl.configure(
            text=f"Kategorien ({len(selected)}): {cat_str}\n"
                 f"Radius: {r} m   ·   Vorwarnung: {w_str}\n"
                 f"Stützpunkt-Abstand: {s}"
        )

    # ── Karte & Filter ───────────────────────

    def _populate_map(self):
        """Zeichnet Route + POI-Marker auf die Karte und baut die Filter-Liste."""
        # Alte Marker/Pfad entfernen
        self._clear_map()

        wpts = self.found_wpts
        # POIs ohne _warn Suffix
        poi_wpts = [(i, w) for i, w in enumerate(wpts) if not w["type"].endswith("_warn")]

        # Enable-State initialisieren (alle an)
        self._poi_enabled = [True] * len(wpts)

        # Route zeichnen
        if self.track_points:
            # Track vereinfachen für Performance (max ~2000 Punkte)
            step = max(1, len(self.track_points) // 2000)
            path_coords = [(p["lat"], p["lon"])
                           for p in self.track_points[::step]]
            if path_coords:
                self._map_path = self._map_widget.set_path(
                    path_coords, color=STRAVA_ORANGE, width=3)

        # POI-Marker setzen
        for idx, wp in poi_wpts:
            poi_type = wp.get("type", "unknown")
            emoji, color = POI_MARKER_STYLE.get(poi_type, ("📍", STRAVA_MUTED))
            type_info = TYPE_INFO.get(poi_type, ("POI", "", ""))
            label = f"{emoji} {wp['name'][:30]}" if wp.get("name") else f"{emoji} {type_info[0]}"
            marker = self._map_widget.set_marker(
                wp["lat"], wp["lon"], text=label,
                marker_color_circle=color,
                marker_color_outside=STRAVA_DARK)
            self._map_markers.append((marker, idx))

        # Karte auf Route zentrieren
        if self.track_points:
            lats = [p["lat"] for p in self.track_points]
            lons = [p["lon"] for p in self.track_points]
            center_lat = (min(lats) + max(lats)) / 2
            center_lon = (min(lons) + max(lons)) / 2
            self._map_widget.set_position(center_lat, center_lon)
            # Zoom berechnen
            lat_range = max(lats) - min(lats)
            lon_range = max(lons) - min(lons)
            span = max(lat_range, lon_range)
            if span > 5:
                zoom = 6
            elif span > 2:
                zoom = 7
            elif span > 1:
                zoom = 8
            elif span > 0.5:
                zoom = 9
            elif span > 0.2:
                zoom = 10
            elif span > 0.1:
                zoom = 11
            else:
                zoom = 12
            self._map_widget.set_zoom(zoom)

        # Filter-Liste aufbauen
        self._build_poi_filter_list(poi_wpts)

        n_poi = len(poi_wpts)
        self._map_status.configure(text=f"{n_poi} POIs auf der Karte")
        self._update_filter_count()

    def _clear_map(self):
        """Entfernt alle Marker und den Pfad von der Karte."""
        for marker, _ in self._map_markers:
            marker.delete()
        self._map_markers.clear()
        if self._map_path is not None:
            self._map_path.delete()
            self._map_path = None

    def _build_poi_filter_list(self, poi_wpts):
        """Baut die Checkbox-Liste für POI-Filterung auf."""
        # Alte Widgets entfernen
        for w in self._poi_list_frame.winfo_children():
            w.destroy()
        self._poi_cb_vars.clear()
        self._poi_cb_widgets.clear()

        if not poi_wpts:
            ctk.CTkLabel(self._poi_list_frame, text="Keine POIs gefunden.",
                         font=("Helvetica", 12), text_color=STRAVA_MUTED
                         ).pack(pady=30)
            return

        # Nach Kategorie sortieren (Reihenfolge wie POI_GROUPS)
        group_order = {}
        for gi, (_, grp_keys) in enumerate(POI_GROUPS):
            for k in grp_keys:
                group_order[k] = gi
        poi_wpts_sorted = sorted(poi_wpts,
                                  key=lambda x: (group_order.get(x[1].get("type", ""), 99),
                                                 x[1].get("name", "")))

        # Nach Kategorie gruppiert
        current_group = None
        for idx, wp in poi_wpts_sorted:
            poi_type = wp.get("type", "unknown")
            # Gruppenheader
            group = None
            for grp_label, grp_keys in POI_GROUPS:
                if poi_type in grp_keys:
                    group = grp_label
                    break
            if group and group != current_group:
                current_group = group
                lbl = ctk.CTkLabel(self._poi_list_frame, text=group,
                                    font=("Helvetica", 10, "bold"),
                                    text_color=STRAVA_MUTED)
                lbl.pack(anchor="w", padx=6, pady=(8, 2))

            emoji, color = POI_MARKER_STYLE.get(poi_type, ("📍", STRAVA_MUTED))
            type_info = TYPE_INFO.get(poi_type, ("POI", "", ""))
            name = wp.get("name", type_info[0]) or type_info[0]
            display = f"{emoji} {name[:35]}"

            enabled_val = True
            if idx < len(self._poi_enabled):
                enabled_val = self._poi_enabled[idx]
            var = tk.BooleanVar(value=enabled_val)
            cb = ctk.CTkCheckBox(
                self._poi_list_frame, text=display,
                variable=var,
                fg_color=color, hover_color=STRAVA_HOVER,
                checkmark_color="#FFF",
                border_color=STRAVA_BORDER,
                text_color=STRAVA_TEXT,
                font=("Helvetica", 11),
                command=lambda i=idx, v=var: self._on_poi_toggle(i, v))
            cb.pack(anchor="w", padx=4, pady=1)
            self._poi_cb_vars.append((idx, var))
            self._poi_cb_widgets.append((idx, cb))

    def _on_poi_toggle(self, wpt_idx, var):
        """Callback wenn ein POI an/abgewählt wird."""
        self._poi_enabled[wpt_idx] = var.get()
        self._refresh_map_markers()
        self._update_filter_count()

    def _set_all_pois_enabled(self, enabled):
        """Alle POIs aktivieren oder deaktivieren."""
        for idx, var in self._poi_cb_vars:
            var.set(enabled)
            self._poi_enabled[idx] = enabled
        self._refresh_map_markers()
        self._update_filter_count()

    def _toggle_category(self, keys):
        """Toggle alle POIs einer Kategorie (an→aus oder aus→an)."""
        relevant = [(idx, var) for idx, var in self._poi_cb_vars
                    if idx < len(self.found_wpts)
                    and self.found_wpts[idx].get("type", "") in keys]
        all_on = all(var.get() for _, var in relevant) if relevant else False
        new_val = not all_on
        for idx, var in relevant:
            var.set(new_val)
            self._poi_enabled[idx] = new_val
        self._refresh_map_markers()
        self._update_filter_count()

    def _refresh_map_markers(self):
        """Löscht alle Marker und zeichnet nur die aktivierten POIs neu."""
        for marker, _ in self._map_markers:
            marker.delete()
        self._map_markers.clear()

        for i, wp in enumerate(self.found_wpts):
            if wp["type"].endswith("_warn"):
                continue
            if not self._poi_enabled[i]:
                continue
            poi_type = wp.get("type", "unknown")
            emoji, color = POI_MARKER_STYLE.get(poi_type, ("📍", STRAVA_MUTED))
            type_info = TYPE_INFO.get(poi_type, ("POI", "", ""))
            label = f"{emoji} {wp['name'][:30]}" if wp.get("name") else f"{emoji} {type_info[0]}"
            marker = self._map_widget.set_marker(
                wp["lat"], wp["lon"], text=label,
                marker_color_circle=color,
                marker_color_outside=STRAVA_DARK)
            self._map_markers.append((marker, i))

    def _update_filter_count(self):
        """Aktualisiert die Anzeige wie viele POIs aktiv sind."""
        total = len(self._poi_cb_vars)
        active = sum(1 for _, var in self._poi_cb_vars if var.get())
        self._filter_count_lbl.configure(text=f"{active} / {total}")

    def _on_map_right_click(self, event):
        """Rechtsklick auf der Karte: nächstgelegenen POI löschen."""
        self._close_delete_popup()
        if not self._map_markers or not self.found_wpts:
            return "break"
        try:
            coords = self._map_widget.convert_canvas_coords_to_decimal_coords(
                event.x, event.y)
        except Exception:
            return "break"
        if not coords:
            return "break"
        lat, lon = coords
        nearest = None
        best_d = float("inf")
        for _, idx in self._map_markers:
            if idx >= len(self.found_wpts):
                continue
            wp = self.found_wpts[idx]
            d = haversine(lat, lon, wp["lat"], wp["lon"])
            if d < best_d:
                best_d = d
                nearest = idx
        if nearest is None or best_d > self._map_right_click_tol_m:
            return "break"
        self._show_delete_popup(event, nearest)
        return "break"

    def _on_map_left_click(self, event):
        """Linksklick: Lösch-Popup schließen (falls offen)."""
        if self._delete_popup is not None:
            self._close_delete_popup()

    def _on_map_motion(self, event):
        """Hover-Hinweis: Cursor ändern, wenn ein POI unter dem Mauszeiger ist."""
        if not self._map_markers or not self.found_wpts:
            if self._hover_poi_idx is not None:
                self._hover_poi_idx = None
                try:
                    self._map_widget.canvas.configure(cursor="")
                except Exception:
                    pass
            return
        try:
            coords = self._map_widget.convert_canvas_coords_to_decimal_coords(
                event.x, event.y)
        except Exception:
            return
        if not coords:
            return
        lat, lon = coords
        nearest = None
        best_d = float("inf")
        for _, idx in self._map_markers:
            if idx >= len(self.found_wpts):
                continue
            wp = self.found_wpts[idx]
            d = haversine(lat, lon, wp["lat"], wp["lon"])
            if d < best_d:
                best_d = d
                nearest = idx
        if nearest is not None and best_d <= self._map_hover_tol_m:
            if self._hover_poi_idx != nearest:
                self._hover_poi_idx = nearest
                try:
                    self._map_widget.canvas.configure(cursor="hand2")
                except Exception:
                    pass
        else:
            if self._hover_poi_idx is not None:
                self._hover_poi_idx = None
                try:
                    self._map_widget.canvas.configure(cursor="")
                except Exception:
                    pass

    def _on_map_leave(self, event):
        if self._hover_poi_idx is not None:
            self._hover_poi_idx = None
            try:
                self._map_widget.canvas.configure(cursor="")
            except Exception:
                pass

    def _show_delete_popup(self, event, wpt_idx):
        """Zeigt ein kleines Popup am Klickpunkt mit Löschen-Button."""
        if wpt_idx < 0 or wpt_idx >= len(self.found_wpts):
            return

        wp = self.found_wpts[wpt_idx]
        if wp.get("type", "").endswith("_warn"):
            return

        name = wp.get("name", "POI")

        self._close_delete_popup()
        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        # Position später nach Widget-Größe zentrieren
        popup.geometry("+0+0")

        frame = ctk.CTkFrame(popup, fg_color=STRAVA_CARD2, corner_radius=8,
                             border_width=1, border_color=STRAVA_BORDER)
        frame.pack(padx=1, pady=1)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(header, text=name[:30],
                     font=("Helvetica", 11, "bold"),
                     text_color=STRAVA_TEXT).pack(side="left", padx=(2, 6))
        ctk.CTkButton(header, text="X", width=22, height=22,
                      fg_color=STRAVA_CARD, hover_color=STRAVA_BORDER,
                      text_color=STRAVA_TEXT, font=("Helvetica", 10, "bold"),
                      command=self._close_delete_popup
                      ).pack(side="right")
        ctk.CTkButton(frame, text="Löschen", width=90, height=28,
                      fg_color="#E74C3C", hover_color="#C0392B",
                      text_color="#FFF", font=("Helvetica", 11, "bold"),
                      command=lambda: self._confirm_delete_poi(wpt_idx)
                      ).pack(padx=10, pady=(6, 8))

        # Popup über dem Marker zentrieren
        try:
            cx, cy = self._map_widget.convert_decimal_coords_to_canvas_coords(
                wp["lat"], wp["lon"])
            map_x = self._map_widget.winfo_rootx()
            map_y = self._map_widget.winfo_rooty()
            popup.update_idletasks()
            pw = popup.winfo_width()
            ph = popup.winfo_height()
            px = int(map_x + cx - pw / 2)
            py = int(map_y + cy - ph - 8)
            popup.geometry(f"+{px}+{py}")
        except Exception:
            # Fallback: nahe Mauszeiger platzieren
            x = getattr(event, "x_root", None)
            y = getattr(event, "y_root", None)
            if x is None or y is None:
                x, y = self.winfo_pointerx(), self.winfo_pointery()
            popup.geometry(f"+{x+8}+{y+8}")

        self._delete_popup = popup
        self._delete_popup_idx = wpt_idx

    def _close_delete_popup(self):
        if self._delete_popup is not None:
            try:
                self._delete_popup.destroy()
            except Exception:
                pass
        self._delete_popup = None
        self._delete_popup_idx = None

    def _confirm_delete_poi(self, wpt_idx):
        self._delete_poi_by_index(wpt_idx)
        self._close_delete_popup()

    def _delete_poi_by_index(self, wpt_idx):
        """Löscht einen POI (und passende Warnpunkte) aus der Liste."""
        if wpt_idx < 0 or wpt_idx >= len(self.found_wpts):
            return
        wp = self.found_wpts[wpt_idx]
        if wp.get("type", "").endswith("_warn"):
            return

        base_type = wp.get("type", "")
        base_name = (wp.get("name") or "").strip()
        warn_type = f"{base_type}_warn"

        to_remove = {wpt_idx}
        for i, w in enumerate(self.found_wpts):
            if i == wpt_idx:
                continue
            if w.get("type") != warn_type:
                continue
            if base_name:
                hay = " ".join([w.get("name", ""), w.get("cmt", ""), w.get("desc", "")])
                if base_name in hay:
                    to_remove.add(i)
            else:
                # Fallback: Warnpunkt in der Nähe des POI löschen
                try:
                    d = haversine(wp["lat"], wp["lon"], w["lat"], w["lon"])
                    if d <= max(200, self.warn_var.get() * 2):
                        to_remove.add(i)
                except Exception:
                    pass

        old_enabled = self._poi_enabled[:] if self._poi_enabled else []
        enabled_by_id = {}
        for i, w in enumerate(self.found_wpts):
            val = old_enabled[i] if i < len(old_enabled) else True
            enabled_by_id[id(w)] = val

        self.found_wpts = [w for i, w in enumerate(self.found_wpts)
                           if i not in to_remove]
        self._poi_enabled = [enabled_by_id.get(id(w), True) for w in self.found_wpts]

        poi_wpts = [(i, w) for i, w in enumerate(self.found_wpts)
                    if not w.get("type", "").endswith("_warn")]
        self._build_poi_filter_list(poi_wpts)
        self._refresh_map_markers()
        self._update_filter_count()
        self._map_status.configure(text=f"{len(poi_wpts)} POIs auf der Karte")

    def _get_enabled_waypoints(self):
        """Gibt nur die aktivierten Waypoints zurück (inkl. Warn-Punkte für aktive POIs)."""
        if not self._poi_enabled or len(self._poi_enabled) != len(self.found_wpts):
            return self.found_wpts  # Fallback: alle

        enabled = []
        # Sammle die Typen der aktivierten POIs (für Warn-Punkte)
        enabled_types = set()
        for i, wp in enumerate(self.found_wpts):
            if wp["type"].endswith("_warn"):
                continue
            if self._poi_enabled[i]:
                enabled.append(wp)
                enabled_types.add(wp["type"])

        # Warn-Punkte: nur für aktivierte POI-Typen UND nahe einem aktivierten POI
        for i, wp in enumerate(self.found_wpts):
            if not wp["type"].endswith("_warn"):
                continue
            base_type = wp["type"].replace("_warn", "")
            if base_type in enabled_types and self._poi_enabled[i]:
                enabled.append(wp)

        return enabled

    # ── POI-Suche ────────────────────────────

    def _start_poi_search(self):
        if not self.track_points:
            messagebox.showwarning("Hinweis", "Bitte zuerst eine GPX-Datei laden.")
            self._set_step(0); return

        active = [(key, q) for lbl, key, q, _ in POI_ITEMS
                  if self.poi_vars.get(key, tk.BooleanVar(value=False)).get()]
        if not active:
            messagebox.showwarning("Hinweis", "Bitte mindestens einen POI-Typ auswählen.")
            self._set_step(1); return

        self._update_summary()
        self._cancel_ev.clear()
        self.search_btn.configure(state="disabled", text="⏳  Suche läuft …")
        self.cancel_btn.configure(state="normal")
        self.poi_progress.set(0)
        self.poi_status.configure(text="Starte Overpass-Abfrage …", text_color=STRAVA_MUTED)
        self.result_lbl.configure(text="Suche läuft …", text_color=STRAVA_MUTED)
        self._log("\n🔍 POI-SUCHE gestartet")

        queries   = [q for _, q in active]
        keys_used = [k for k, _ in active]

        def run():
            try:
                self._run_poi_search(queries, keys_used)
            except Exception as e:
                import traceback
                self._log(f"❌ {e}\n{traceback.format_exc()}")
                self.after(0, lambda: self.poi_status.configure(
                    text=f"Fehler: {e}", text_color="#E74C3C"))
            finally:
                self.after(0, lambda: self.search_btn.configure(
                    state="normal", text="🔍  POIs suchen & Dateien erstellen"))
                self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

        threading.Thread(target=run, daemon=True).start()

    def _cancel_search(self):
        self._cancel_ev.set()
        self.cancel_btn.configure(state="disabled")
        self.poi_status.configure(text="⛔ Wird abgebrochen …", text_color=STRAVA_WARN)
        self._log("  ⛔ Abbruch angefordert …")

    def _run_poi_search(self, queries, keys_used):
        radius_m  = self.radius_var.get()
        warn_dist = self.warn_var.get()

        if self.sample_mode.get() == "auto":
            step_m = adaptive_sample_step(radius_m)
        else:
            step_m = self.sample_var.get()
        sampled = sample_track(self.track_points, step_m=step_m)
        centers = [(p["lat"], p["lon"]) for p in sampled]
        self._log(f"  Radius: {radius_m} m | Schrittweite: {step_m} m | "
                  f"{len(keys_used)} Typen | {len(centers)} Stützpunkte")

        def prog_cb(done, total):
            self.after(0, lambda: self.poi_progress.set(0.1 + 0.75*(done/total)))
            self.after(0, lambda: self.poi_status.configure(
                text=f"Lade Chunk {done}/{total} …"))

        self.after(0, lambda: self.poi_progress.set(0.05))
        nodes = query_overpass_cancelable(
            centers, radius_m, queries, self._cancel_ev,
            progress_cb=prog_cb, log_fn=self._log
        )

        if nodes is None:
            self.after(0, lambda: self.poi_progress.set(0))
            self.after(0, lambda: self.poi_status.configure(
                text="Abgebrochen.", text_color=STRAVA_MUTED))
            self.after(0, lambda: self.result_lbl.configure(
                text="Suche abgebrochen.", text_color=STRAVA_MUTED))
            return

        wpts = deduplicate(nodes_to_waypoints(nodes, self.track_points, warn_dist_m=warn_dist))
        self.found_wpts = wpts
        poi_only = [w for w in wpts if not w["type"].endswith("_warn")]
        warn_pts = [w for w in wpts if w["type"].endswith("_warn")]
        self._log(f"  ✅ {len(poi_only)} POIs + {len(warn_pts)} Vorwarnpunkte")

        self.after(0, lambda: self.poi_progress.set(0.88))

        if not poi_only:
            self.after(0, lambda: self.poi_status.configure(
                text="Keine POIs gefunden.", text_color=STRAVA_MUTED))
            self.after(0, lambda: self.result_lbl.configure(
                text="Keine passenden POIs in der Nähe der Route.",
                text_color=STRAVA_MUTED))
            self.after(0, lambda: self.poi_progress.set(0))
            return

        out  = self.out_dir.get()
        base = os.path.splitext(os.path.basename(self.gpx_path.get()))[0]
        saved = []

        if self.var_gpx.get():
            p = os.path.join(out, f"{base}_pois.gpx")
            # Vorwarn-Punkte (_warn) nur in FIT – in GPX nur echte POIs
            gpx_wpts = [w for w in wpts if not w["type"].endswith("_warn")]
            write_gpx_with_waypoints(
                self.gpx_path.get(),
                gpx_wpts,
                p,
                overwrite_existing=self.var_overwrite_wpt.get(),
            )
            self._log(f"  💾 GPX ({len(gpx_wpts)} POIs) → {p}"); saved.append(p)

        self.after(0, lambda: self.poi_progress.set(0.94))

        if self.var_fit.get():
            try:
                p = os.path.join(out, f"{base}_pois.fit")
                cname = (self.course_name_var.get().strip() or self.route_name or base)[:16]
                write_fit_course(cname,
                                 self.track_points, self.cum_dists, wpts, p)
                self._log(f"  💾 FIT → {p}"); saved.append(p)
            except Exception as e:
                self._log(f"  ⚠️  FIT-Fehler: {e}")

        res_msg = (f"✅  {len(poi_only)} POIs"
                   + (f"  +  {len(warn_pts)} Vorwarnpunkte" if warn_pts else "")
                   + f"\n{len(saved)} Datei(en) gespeichert.")
        self.after(0, lambda: self.poi_progress.set(1.0))
        self.after(0, lambda: self.poi_status.configure(
            text=f"✅ {len(poi_only)} POIs gespeichert", text_color=STRAVA_GREEN))
        self.after(0, lambda: self.result_lbl.configure(
            text=res_msg, text_color=STRAVA_GREEN))
        self.after(0, lambda: self.finish_info.configure(
            text=f"{len(poi_only)} POIs · {len(saved)} Dateien gespeichert"))
        self._log(f"\n✅ Fertig! {len(poi_only)} POIs | {len(saved)} Dateien")
        # Karte mit Route + POIs befüllen
        self.after(0, self._populate_map)

    # ── Tour-Split ────────────────────────────

    def _compute_splits(self, log=True):
        if self.split_mode.get() == "auto":
            return split_tour_auto(self.track_points, self.cum_dists,
                                   int(self.days_var.get()),
                                   log_fn=self._log if log else None,
                                   poi_wpts=self.found_wpts or None)
        raw = self.manual_entry.get().strip()
        if not raw:
            raise ValueError("Bitte Split-Punkte eingeben.")
        tokens = re.split(r'[,\s–\-]+', raw)
        km_list = []
        total_km = self.cum_dists[-1] / 1000.0
        for t in tokens:
            t = t.strip()
            if not t or t.lower() in ("ende", "end", "finish", "ziel"):
                continue
            try:
                val = float(t)
                km_list.append(val)
            except ValueError:
                pass
        if not km_list:
            raise ValueError("Keine gültigen km-Werte gefunden.")
        # Vorab-Warnung wenn Werte außerhalb der Strecke
        bad = [k for k in km_list if k <= 0 or k >= total_km]
        if bad:
            self._log(f"  ⚠️  Folgende Werte liegen außerhalb der Route ({total_km:.1f} km) "
                      f"und werden ignoriert: {bad}")
        result = split_tour_manual(self.track_points, self.cum_dists, km_list)
        if not result:
            raise ValueError(f"Keine gültigen Split-Punkte innerhalb der Route "
                             f"(0–{total_km:.1f} km).")
        return result

    def _preview_split(self):
        if not self.track_points:
            messagebox.showwarning("Hinweis", "Bitte zuerst eine GPX-Datei laden.")
            return
        for w in self.preview_inner.winfo_children():
            w.destroy()
        try:
            splits = self._compute_splits(log=False)
        except Exception as e:
            ctk.CTkLabel(self.preview_inner, text=f"Fehler: {e}",
                         text_color="#E74C3C").pack(); return

        indices = [0] + splits + [len(self.track_points) - 1]
        COLORS  = [STRAVA_ORANGE, STRAVA_BLUE, STRAVA_GREEN,
                   "#E74C3C","#9B59B6","#F39C12","#1ABC9C","#E67E22"]
        total_d = self.cum_dists[-1]

        # Tabellen-Header
        hdr = ctk.CTkFrame(self.preview_inner, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 2))
        for txt, w in [("Etappe",64),("Distanz",90),("Hm ↑",74),
                        ("Von km",80),("Bis km",80),("Übernacht",110)]:
            ctk.CTkLabel(hdr, text=txt, font=("Helvetica", 10, "bold"),
                         text_color=STRAVA_MUTED, width=w, anchor="w").pack(side="left")
        ctk.CTkFrame(self.preview_inner, fg_color=STRAVA_BORDER,
                     height=1).pack(fill="x", pady=3)

        for i in range(len(indices)-1):
            si, ei = indices[i], indices[i+1]
            seg     = self.track_points[si:ei+1]
            seg_km  = (self.cum_dists[ei] - self.cum_dists[si]) / 1000
            gain    = compute_elevation_gain(seg)
            end_ele = self.track_points[ei]["ele"]
            color   = COLORS[i % len(COLORS)]
            row = ctk.CTkFrame(self.preview_inner, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkFrame(row, fg_color=color, width=6, height=22,
                         corner_radius=3).pack(side="left", padx=(0,6))
            for txt, w in [(f"Tag {i+1}",58),(f"{seg_km:.1f} km",90),
                            (f"{gain:.0f} m",74),
                            (f"{self.cum_dists[si]/1000:.1f}",80),
                            (f"{self.cum_dists[ei]/1000:.1f}",80),
                            (f"{end_ele:.0f} m ü.NN",110)]:
                ctk.CTkLabel(row, text=txt, font=("Helvetica", 11),
                             text_color=STRAVA_TEXT, width=w, anchor="w").pack(side="left")

        # Balken
        ctk.CTkFrame(self.preview_inner, fg_color=STRAVA_BORDER, height=1).pack(fill="x", pady=6)
        ctk.CTkLabel(self.preview_inner, text="Distanzverteilung:",
                     font=("Helvetica", 9), text_color=STRAVA_MUTED).pack(anchor="w")
        bar = ctk.CTkFrame(self.preview_inner, fg_color=STRAVA_CARD2,
                            height=16, corner_radius=4)
        bar.pack(fill="x", pady=3)
        bar.update_idletasks()
        bw = bar.winfo_width() or 560
        for i in range(len(indices)-1):
            si, ei = indices[i], indices[i+1]
            frac   = (self.cum_dists[ei] - self.cum_dists[si]) / total_d
            color  = COLORS[i % len(COLORS)]
            seg_bar = ctk.CTkFrame(bar, fg_color=color, height=16, corner_radius=0)
            seg_bar.configure(width=max(2, int(frac*bw)))
            seg_bar.pack(side="left", fill="y")

    def _start_split(self):
        if not self.track_points:
            messagebox.showwarning("Hinweis", "Bitte zuerst eine GPX-Datei laden.")
            return
        self.split_btn.configure(state="disabled", text="⏳ Aufteilen …")
        self.split_progress.set(0)
        self.split_status.configure(text="Berechne …", text_color=STRAVA_MUTED)

        def run():
            try:
                self._run_split()
            except Exception as e:
                import traceback
                self._log(f"❌ {e}\n{traceback.format_exc()}")
                self.after(0, lambda: self.split_status.configure(
                    text=f"Fehler: {e}", text_color="#E74C3C"))
            finally:
                self.after(0, lambda: self.split_btn.configure(
                    state="normal", text="✂  Tour aufteilen & Dateien erstellen"))

        threading.Thread(target=run, daemon=True).start()

    def _run_split(self):
        self._log("\n✂  TOUR-SPLITTER")
        try:
            splits = self._compute_splits(log=True)
        except Exception as e:
            self._log(f"❌ {e}")
            self.after(0, lambda: self.split_status.configure(
                text=f"Fehler: {e}", text_color="#E74C3C"))
            return

        indices = [0] + splits + [len(self.track_points) - 1]
        n    = len(indices) - 1
        out  = self.out_dir.get()
        base = os.path.splitext(os.path.basename(self.gpx_path.get()))[0]
        cname = (self.course_name_var.get().strip() or self.route_name or base)[:16]
        created = []
        enabled_wpts = self._get_enabled_waypoints()

        # Vorberechnung: nächsten Track-Index für jeden POI (einmalig O(W*N) statt O(E*W*N))
        wpt_track_idx = []
        for wp in enabled_wpts:
            idx, _ = _find_nearest_track_idx(self.track_points, wp["lat"], wp["lon"])
            wpt_track_idx.append(idx)

        for i in range(n):
            si, ei = indices[i], indices[i+1]
            seg_pts, seg_dists = extract_segment(self.track_points, self.cum_dists, si, ei)
            seg_name = f"{cname} – Etappe {i+1}"
            seg_km   = seg_dists[-1] / 1000
            gain     = compute_elevation_gain(seg_pts)
            self._log(f"  Etappe {i+1}: {seg_km:.1f} km | {gain:.0f} m Hm | "
                      f"Übernacht: {seg_pts[-1]['ele']:.0f} m")

            # POIs dieser Etappe: nur echte POIs (keine _warn) im Segment
            seg_wpts = [wp for wp, ti in zip(enabled_wpts, wpt_track_idx)
                        if not wp["type"].endswith("_warn") and si <= ti <= ei]

            if self.var_split_gpx.get():
                p = os.path.join(out, f"{base}_etappe{i+1:02d}.gpx")
                if seg_wpts:
                    write_segment_gpx(seg_pts, seg_name, p)
                    with open(p, "r", encoding="utf-8") as f:
                        seg_content = f.read()
                    wpt_lines = []
                    for wp in seg_wpts:
                        cmt_line = f'\n    <cmt>{_esc(wp.get("cmt",""))}</cmt>' if wp.get("cmt") else ""
                        wpt_lines.append(
                            f'  <wpt lat="{wp["lat"]:.7f}" lon="{wp["lon"]:.7f}">\n'
                            f'    <name>{_esc(wp["name"])}</name>{cmt_line}\n'
                            f'    <desc>{_esc(wp.get("desc",""))}</desc>\n'
                            f'    <sym>{_esc(wp.get("sym","Waypoint"))}</sym>\n'
                            f'    <type>{_esc(wp.get("ctype","GENERIC"))}</type>\n'
                            f'  </wpt>'
                        )
                    wpt_str = "\n" + "\n".join(wpt_lines) + "\n"
                    match = re.search(r'<(?:trk|rte)>|<(?:trk|rte)\s', seg_content)
                    pos   = match.start() if match else max(seg_content.rfind("</gpx>"), 0)
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(seg_content[:pos] + wpt_str + seg_content[pos:])
                else:
                    write_segment_gpx(seg_pts, seg_name, p)
                self._log(f"    GPX → {p}  ({len(seg_wpts)} POIs)"); created.append(p)

            if self.var_split_fit.get():
                p = os.path.join(out, f"{base}_etappe{i+1:02d}.fit")
                # Etappen-FIT: echte POIs + Warn-Punkte im Segment
                seg_wpts_fit = seg_wpts[:]
                seg_wpts_fit += [wp for wp, ti in zip(enabled_wpts, wpt_track_idx)
                                 if wp["type"].endswith("_warn") and si <= ti <= ei]

                # FIT Course Name: max 16 Zeichen, z.B. "Mallnitz Bu E01"
                suffix = f" E{i+1:02d}" if n >= 10 else f" E{i+1}"
                fit_seg_name = f"{cname[:16-len(suffix)]}{suffix}"
                r = write_segment_fit(seg_pts, seg_dists, fit_seg_name, seg_wpts_fit, p)
                if r is True:
                    self._log(f"    FIT → {p}  ({len(seg_wpts)} POIs + Vorwarnpunkte)"); created.append(p)
                else:
                    self._log(f"    ⚠️  FIT-Fehler: {r}")

            self.after(0, lambda p=(i+1)/n: self.split_progress.set(p))

        self._log(f"\n✅ {len(created)} Etappen-Dateien erstellt")
        self.after(0, lambda: self.split_status.configure(
            text=f"✅ {n} Etappen erstellt!", text_color=STRAVA_GREEN))
        self.after(0, lambda: self.finish_info.configure(
            text=f"{n} Etappen · {len(created)} Dateien → {out}"))

    # ── Abschließen ───────────────────────────

    def _open_output_folder(self):
        folder = self.out_dir.get()
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception as e:
            messagebox.showerror("Fehler", f"{e}")

    def _restart(self):
        self.gpx_path.set("")
        self.track_points = []; self.cum_dists = []
        self.route_name = ""; self.course_name_var.set(""); self.found_wpts = []
        for lbl, val in [(self.stat_dist,"– km"),(self.stat_elev,"– m ↑"),
                          (self.stat_pts,"–"),(self.stat_name,"–")]:
            lbl.configure(text=val)
        self.poi_progress.set(0); self.split_progress.set(0)
        self.poi_status.configure(text="Bereit.", text_color=STRAVA_MUTED)
        self.split_status.configure(text="Bereit.", text_color=STRAVA_MUTED)
        self.result_lbl.configure(text="Noch keine Suche durchgeführt.",
                                   text_color=STRAVA_MUTED)
        # Karte zurücksetzen
        self._clear_map()
        self._poi_enabled.clear()
        self._poi_cb_vars.clear()
        self._poi_cb_widgets.clear()
        for w in self._poi_list_frame.winfo_children():
            w.destroy()
        self._poi_list_placeholder = ctk.CTkLabel(
            self._poi_list_frame, text="Zuerst POIs suchen\n(Tab 3)",
            font=("Helvetica", 12), text_color=STRAVA_MUTED)
        self._poi_list_placeholder.pack(pady=30)
        self._map_status.configure(text="Keine POIs geladen")
        self._filter_count_lbl.configure(text="0 / 0")
        self._map_widget.set_position(47.5, 13.0)
        self._map_widget.set_zoom(6)
        self._set_step(0)

    # ── Log ───────────────────────────────────

    def _log(self, msg):
        self.log_queue.put(msg)

    def _poll_log(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            # Entfernt Zeichen, die die Windows-Konsole (cp1252) nicht kann
            safe = msg.encode("cp1252", errors="ignore").decode("cp1252")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {safe}")
        self.after(120, self._poll_log)


# ══════════════════════════════════════════════
if __name__ == "__main__":
    app = GPXPOIApp()
    app.mainloop()
