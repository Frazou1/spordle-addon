import json
import time
import re
import os
import urllib.request
import asyncio
import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
import paho.mqtt.client as mqtt
from playwright.async_api import async_playwright

with open("/data/options.json", "r") as f:
    config = json.load(f)

TEAM_ID = config.get("team_id", "000000")
MY_TEAM_NAME = config.get("team_name", "MON EQUIPE").upper()
TRACKED_PLAYER = config.get("tracked_player", "").strip().lower()

MQTT_HOST = config.get("mqtt_host", "core-mosquitto")
MQTT_PORT = config.get("mqtt_port", 1883)
MQTT_USER = config.get("mqtt_user", "")
MQTT_PASS = config.get("mqtt_password", "")
INTERVAL = config.get("update_interval_hours", 6) * 3600

LEAGUE_UUID = "c43095cf-c7e6-4562-994c-a71a9a0cbf3a"
SCHEDULE_HORS_CONCOURS = "198969"
SCHEDULE_SAISON_REGULIERE = "198221"

# Logos écrits directement dans /config/www : HA ne sert pas /local à travers un lien symbolique vers /share.
# Logos written straight into /config/www: HA won't serve /local through a symlink to /share.
WWW_LOGOS_DIR = "/config/www/spordle_logos"
if os.path.islink(WWW_LOGOS_DIR):
    os.unlink(WWW_LOGOS_DIR)
LOGOS_DIR = WWW_LOGOS_DIR if os.path.isdir("/config") else "/share/spordle_logos"
os.makedirs(LOGOS_DIR, exist_ok=True)

def publish_to_mqtt(topic, payload):
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    try:
        client.connect(MQTT_HOST, int(MQTT_PORT), keepalive=10)
        client.loop_start()
        # Attendre l'accusé de réception : une connexion refusée (ex. sans identifiants) n'est plus masquée.
        # Wait for the broker ack: a refused connection (e.g. no credentials) is no longer hidden.
        result = client.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True)
        result.wait_for_publish(timeout=5)
        client.loop_stop()
        client.disconnect()
        if not result.is_published():
            raise RuntimeError("message non confirmé par le broker (identifiants MQTT ?)")
        print(f"[MQTT SUCCESS] Publié sur: {topic}")
    except Exception as e:
        print(f"[MQTT ERROR] Échec sur {topic}: {e}")

def clean_player_name(name: str) -> str:
    name = name.strip()
    if len(name) > 1 and name[0] == name[1] and name[0].isupper():
        name = name[1:]
    return name

def parse_roster_structured(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    
    gardiens = []
    joueurs = []
    personnel = []

    staff_patterns = re.findall(r'([A-Za-zÀ-ÖØ-öø-ÿ\s\-]+?)\s*(Entraîneur-Adjoint|Entraîneur-Chef|Entraîneur|Gérant|Préposé)', text)
    for raw_name, role in staff_patterns:
        words = [w for w in raw_name.split() if w.upper() not in ["POSITION", "PERSONNEL", "DE", "L'ÉQUIPE"]]
        if words:
            clean_n = clean_player_name(" ".join(words[-2:]))
            if clean_n and not any(p["nom"] == clean_n for p in personnel):
                personnel.append({"nom": clean_n, "role": role})

    player_matches = re.findall(r'([A-Za-zÀ-ÖØ-öø-ÿ\s\-]{3,30}?)\s*(\d{1,2})\s*([FGD]|DG|AG|AD|Gardiens?|Joueurs?)\b', text)
    
    for raw_name, num, pos in player_matches:
        words = [w for w in raw_name.split() if w.upper() not in ["POSITION", "GARDIENS", "JOUEURS", "PERSONNEL", "DE", "L'ÉQUIPE"]]
        if not words:
            continue
        full_name = clean_player_name(" ".join(words))
        
        item = {"nom": full_name, "numero": num, "position": pos}
        if pos.upper() in ["G", "GARDIEN", "GARDIENS"] or "GARD" in pos.upper():
            if not any(g["nom"] == full_name for g in gardiens):
                gardiens.append(item)
        else:
            if not any(j["nom"] == full_name for j in joueurs):
                joueurs.append(item)

    if not joueurs and not gardiens:
        raw_items = re.findall(r'([A-Z][A-Z\s\-]+)(\d{1,2})([A-Z]{1,2})', text)
        for raw_name, num, pos in raw_items:
            clean_n = clean_player_name(raw_name)
            item = {"nom": clean_n, "numero": num, "position": pos}
            if pos == "G":
                gardiens.append(item)
            else:
                joueurs.append(item)

    print(f"[PARSING ROSTER] {len(gardiens)} gardien(s), {len(joueurs)} joueur(s), {len(personnel)} membre(s) du personnel trouvés.")
    return {"gardiens": gardiens, "joueurs": joueurs, "personnel": personnel}

# Fonctions communes avec l'add-on RSEQ Hockey (même plateforme Spordle).
# Shared with the RSEQ Hockey add-on (same Spordle platform).
def _slugify(name: str) -> str:
    replacements = {
        'à': 'a', 'â': 'a', 'ä': 'a', 'á': 'a', 'ã': 'a', 'å': 'a',
        'ç': 'c', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'î': 'i', 'ï': 'i', 'í': 'i', 'ì': 'i',
        'ô': 'o', 'ö': 'o', 'ó': 'o', 'ò': 'o', 'õ': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u', 'ú': 'u',
        'ÿ': 'y', 'ñ': 'n', "'": '', '’': '',
    }
    s = name.lower()
    for k, v in replacements.items():
        s = s.replace(k, v)
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


def download_logo(url: str, team_name: str) -> str:
    if not url:
        return ""
    try:
        slug = _slugify(team_name)
        ext = os.path.splitext(url.split("?")[0])[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            ext = ".png"
        filename = f"{slug}{ext}"
        filepath = os.path.join(LOGOS_DIR, filename)

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            with open(filepath, "wb") as f:
                f.write(data)
            print(f"[LOGO] Téléchargé: {team_name} → {filename} ({len(data)} octets)")

        return f"/local/spordle_logos/{filename}"
    except Exception as e:
        print(f"[LOGO ERROR] {team_name}: {e}")
        return ""


_JOURS_FR = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"]
_MOIS_FR = ["JANV", "FÉVR", "MARS", "AVR", "MAI", "JUIN",
            "JUIL", "AOÛT", "SEPT", "OCT", "NOV", "DÉC"]

_MOIS_MAP = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_JOURS_MAP = {
    "lundi": "LUN", "mardi": "MAR", "mercredi": "MER",
    "jeudi": "JEU", "vendredi": "VEN", "samedi": "SAM", "dimanche": "DIM",
}
_MOIS_ABBR = {
    1: "JANV", 2: "FÉVR", 3: "MARS", 4: "AVR", 5: "MAI", 6: "JUIN",
    7: "JUIL", 8: "AOÛT", 9: "SEPT", 10: "OCT", 11: "NOV", 12: "DÉC",
}


def _parse_date_header(h4_text: str):
    m = re.match(r'(\w+)\s+(\d{1,2})\s+(\w+)\s+(\d{4})', h4_text.strip(), re.I)
    if not m:
        return h4_text, ""
    jour, num, mois, annee = m.group(1).lower(), int(m.group(2)), m.group(3).lower(), int(m.group(4))
    j_abbr = _JOURS_MAP.get(jour, jour[:3].upper())
    m_num = _MOIS_MAP.get(mois, 1)
    date_fr = f"{j_abbr}. {num} {_MOIS_ABBR[m_num]}."
    date_iso = f"{annee:04d}-{m_num:02d}-{num:02d}"
    return date_fr, date_iso


def _iso_to_date_fr(iso):
    try:
        iso_clean = iso.strip().replace(" ", "")
        dt_utc = datetime.fromisoformat(iso_clean.replace("Z", "+00:00"))

        try:
            dt_local = dt_utc.astimezone(ZoneInfo("America/Toronto"))
        except Exception:
            year = dt_utc.year
            march = calendar.monthcalendar(year, 3)
            dst_start_day = [w[6] for w in march if w[6] != 0][1]
            dst_start = datetime(year, 3, dst_start_day, 7, 0)
            nov = calendar.monthcalendar(year, 11)
            dst_end_day = [w[6] for w in nov if w[6] != 0][0]
            dst_end = datetime(year, 11, dst_end_day, 6, 0)
            dt_naive = dt_utc.replace(tzinfo=None)
            offset_h = -4 if dst_start <= dt_naive < dst_end else -5
            dt_local = dt_utc + timedelta(hours=offset_h)

        return f"{_JOURS_FR[dt_local.weekday()]}. {dt_local.day} {_MOIS_FR[dt_local.month-1]}.", dt_local.strftime("%Hh%M")
    except Exception as e:
        print(f"[TZ WARN] {iso}: {e}")
        return "", ""


def parse_schedule_cards(html: str):
    soup = BeautifulSoup(html, "html.parser")
    matchs = []

    for section_li in soup.find_all("li", attrs={"data-date-section": True}):
        h4 = section_li.find("h4")
        section_date_fr = ""
        section_date_iso = ""
        if h4:
            section_date_fr, section_date_iso = _parse_date_header(h4.get_text(" ", strip=True))
            print(f"[SCHEDULE] Section: '{h4.get_text(strip=True)}' → {section_date_fr} ({section_date_iso})")

        articles = section_li.find_all("article", attrs={"itemtype": re.compile("SportsEvent", re.I)})
        for art in articles:
            arena = ""
            addr = art.find("address")
            if addr:
                arena = addr.get_text(" ", strip=True)

            num_match = ""
            sched_type = art.find("span", class_=re.compile("scheduleType", re.I))
            if sched_type:
                txt = sched_type.get_text(" ", strip=True)
                m = re.search(r'P-?\d+', txt)
                if m:
                    num_match = m.group(0)

            iso = ""
            date_fr = section_date_fr
            heure_fr = ""
            t = art.find("time")
            if t:
                iso = (t.get("datetime") or "").strip()
                if iso:
                    d_fr, h_fr = _iso_to_date_fr(iso)
                    if d_fr:
                        date_fr = d_fr
                        heure_fr = h_fr

            score = ""
            status = "À VENIR"
            final_el = art.find(string=re.compile(
                r'^\s*(FINAL|EN COURS|PROLONGATION|FUSILLADE)\s*$', re.I))
            if final_el:
                status = final_el.strip().upper()
                score_divs = art.find_all("div", class_=re.compile("font-brand font-size-lg", re.I))
                digits = [d.get_text(strip=True) for d in score_divs if d.get_text(strip=True).isdigit()]
                if len(digits) >= 2:
                    score = f"{digits[0]}-{digits[1]}"

            equipes = []
            equipes_details = []
            teams = art.find_all("article", attrs={"itemtype": re.compile("SportsTeam", re.I)})
            for t_art in teams:
                team_name = ""
                name_el = t_art.find(attrs={"itemprop": "name"})
                if name_el:
                    a = name_el.find("a")
                    if a:
                        team_name = a.get_text(strip=True)

                logo_url = ""
                img = t_art.find("img")
                if img:
                    logo_url = img.get("src", "")

                logo_local = ""
                if team_name and logo_url:
                    logo_local = download_logo(logo_url, team_name)

                if team_name:
                    equipes.append(team_name)
                    equipes_details.append({
                        "nom": team_name,
                        "logo_remote": logo_url,
                        "logo_local": logo_local,
                    })

            joue = bool(score)
            match = {
                "numero": num_match,
                "date": date_fr,
                "date_iso": section_date_iso,
                "heure": heure_fr,
                "iso": iso,
                "arene": arena,
                "equipes": equipes,
                "equipes_details": equipes_details,
                "score": score,
                "statut": status,
                "joue": joue,
            }
            matchs.append(match)
            print(f"   {date_fr} {heure_fr} | {arena[:55]} | {equipes} | {score or '-'} | {status}")

    return matchs


# Lecteur d'alignement de l'add-on RSEQ Hockey : lit le tableau (noms propres, numéros, stats).
# RSEQ Hockey roster reader: reads the table (clean names, numbers, stats).
def _extract_name_from_cell(td):
    """
    Extrait le nom depuis le <div title="NOM"> de Spordle.
    Le title contient 'PRÉNOM NOM' propre.
    """
    # Priorité 1 : attribut title d'un div
    for div in td.find_all("div"):
        title = div.get("title", "").strip()
        if title and len(title) > 2 and not title.isdigit():
            return title

    # Priorité 2 : balise <a> avec texte direct
    a = td.find("a")
    if a:
        txt = a.get_text(strip=True)
        if txt and len(txt) > 2 and not txt.isdigit():
            return txt

    # Priorité 3 : span avec class text-truncate (personnel)
    sp = td.find("span", class_=re.compile("text-truncate", re.I))
    if sp:
        txt = sp.get_text(strip=True)
        if txt and len(txt) > 2:
            return txt

    return ""


def _extract_number_from_cell(td_name, td_num):
    """
    Extrait le numéro. Il est dans :
    <span class='ml-2 text-muted'><span>11</span></span>
    """
    # Priorité 1 : span avec class ml-2 text-muted
    for sp in td_name.find_all("span"):
        classes = " ".join(sp.get("class", []))
        if "text-muted" in classes and "ml-2" in classes:
            num_span = sp.find("span")
            if num_span:
                txt = num_span.get_text(strip=True)
                if txt.isdigit():
                    return txt

    # Priorité 2 : chercher le dernier <span> du td qui ne contient qu'un nombre 1-2 chiffres
    all_spans = td_name.find_all("span")
    for sp in reversed(all_spans):
        txt = sp.get_text(strip=True)
        if txt.isdigit() and 1 <= int(txt) <= 99:
            return txt

    return ""


def parse_roster_table(html: str):
    try:
        with open("/share/spordle_roster_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass

    soup = BeautifulSoup(html, "html.parser")
    gardiens, joueurs, personnel = [], [], []

    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        if not headers:
            continue
        hs = set(h.lower() for h in headers)

        if "gardiens" in hs:
            print(f"\n[ROSTER] Table GARDIENS")
            for tr in table.select("tbody tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                nom = _extract_name_from_cell(tds[0])
                num = _extract_number_from_cell(tds[0], tds[1])
                if nom:
                    gardiens.append({
                        "nom": nom,
                        "numero": num,
                        "stats": dict(zip(headers, [td.get_text(strip=True) for td in tds]))
                    })
                    print(f"   → {nom} (#{num or '?'})")

        elif "joueurs" in hs:
            print(f"\n[ROSTER] Table JOUEURS")
            for tr in table.select("tbody tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                nom = _extract_name_from_cell(tds[0])
                num = _extract_number_from_cell(tds[0], tds[1])
                if nom:
                    joueurs.append({
                        "nom": nom,
                        "numero": num,
                        "stats": dict(zip(headers, [td.get_text(strip=True) for td in tds]))
                    })
                    print(f"   → {nom} (#{num or '?'})")

        elif any("personnel" in h.lower() for h in headers):
            print(f"\n[ROSTER] Table PERSONNEL")
            for tr in table.select("tbody tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                nom = ""
                sp = tds[0].find("span", class_=re.compile("text-truncate", re.I))
                if sp:
                    nom = sp.get_text(strip=True)
                else:
                    div = tds[0].find("div", attrs={"title": True})
                    if div:
                        nom = div.get("title", "").strip()
                role = tds[1].get_text(strip=True)
                if nom:
                    personnel.append({"nom": nom, "role": role})
                    print(f"   → {nom} ({role})")

    print(f"\n[PARSING ROSTER] {len(gardiens)} G, {len(joueurs)} J, {len(personnel)} P.")
    return {"gardiens": gardiens, "joueurs": joueurs, "personnel": personnel}


def parse_standings_ligue(html: str):
    """Classement de la division de l'équipe + rang dans la ligue.
    Team's division standings + rank in the whole league."""
    soup = BeautifulSoup(html, "html.parser")
    tables = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        if "Équipe" not in headers:
            continue
        rows = []
        for tr in table.select("tbody tr"):
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) < len(headers):
                continue
            row = dict(zip(headers, tds))
            img = tr.find("img")
            remote = img.get("src", "") if img else ""
            row["logo_remote"] = remote
            row["logo_local"] = download_logo(remote, row.get("Équipe", "")) if remote else ""
            rows.append(row)
        if any(MY_TEAM_NAME in r.get("Équipe", "").upper() for r in rows):
            tables.append(rows)
    if not tables:
        print("[PARSING STANDINGS] Équipe introuvable dans le classement.")
        return [], None, None, []
    tables.sort(key=len)
    division, ligue = tables[0], tables[-1]
    rang_ligue = next((r.get("#") for r in ligue if MY_TEAM_NAME in r.get("Équipe", "").upper()), None)
    print(f"[PARSING STANDINGS] Division: {len(division)} équipes, ligue: {len(ligue)} équipes.")
    # Version allégée de la ligue complète (sans logo distant) pour limiter la taille de l'attribut.
    # Lighter copy of the whole league (no remote logo) to keep the attribute small.
    def _total(r, cle):
        # LHQCA : V/D détaillées en VR/VP/VF et DR/DP/DF (V et D valent « - »)
        # LHQCA: wins/losses split into VR/VP/VF and DR/DP/DF (V and D are "-")
        if str(r.get(cle, "")).strip().isdigit():
            return r[cle]
        parts = [r.get(cle + suffixe) for suffixe in ("R", "P", "F")]
        nombres = [int(x) for x in parts if str(x or "").strip().isdigit()]
        return str(sum(nombres)) if nombres else r.get(cle)

    for r in division + ligue:
        r["V"], r["D"] = _total(r, "V"), _total(r, "D")
    ligue_courte = [{k: r.get(k) for k in ("#", "Équipe", "MJ", "V", "D", "N", "PTS", "logo_local")} for r in ligue]
    return division, rang_ligue, len(ligue), ligue_courte


def parse_schedule_structured(html: str):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    
    dates = re.findall(r'((?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+\d{1,2}\s+[a-zà-û]+\s+\d{4})', text, re.I)
    unique_dates = list(dict.fromkeys(dates))
    
    events = [{"date": d, "description": "Match au calendrier"} for d in unique_dates]
    print(f"[PARSING SCHEDULE] {len(unique_dates)} date(s) de match trouvée(s).")
    return {"dates_trouvees": unique_dates, "prochains_matchs": events}

def parse_table_generic(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    headers = [th.get_text(strip=True) for th in table.select("thead th")]
    rows = []
    for tr in table.select("tbody tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) >= len(headers):
            rows.append(dict(zip(headers, tds)))
    return rows

def parse_standings(html: str):
    soup = BeautifulSoup(html, "html.parser")
    all_rows = []
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        for tr in table.select("tbody tr"):
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) >= len(headers):
                row = dict(zip(headers, tds))
                img = tr.find("img")
                if img and img.get("src"):
                    team_name = row.get("Équipe", "").strip()
                    row["logo_remote"] = img.get("src")
                    row["logo_url"] = download_logo(img.get("src"), team_name)
                all_rows.append(row)
    return all_rows

def download_logos(soup: BeautifulSoup):
    images = soup.find_all("img")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36'}
    for img in images:
        src = img.get("src", "")
        alt = img.get("alt", "").strip()
        if src.startswith("http") and ("team" in src or "logo" in src or len(alt) > 2):
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', alt if alt else src.split("/")[-1]).lower()
            file_path = os.path.join(LOGOS_DIR, f"{clean_name}.png")
            if not os.path.exists(file_path):
                try:
                    req = urllib.request.Request(src, headers=headers)
                    with urllib.request.urlopen(req) as response, open(file_path, 'wb') as out_file:
                        out_file.write(response.read())
                except Exception:
                    pass

async def scrape_and_publish():
    print(f"\n==================================================")
    print(f"[START] Scraping Spordle v1.7.4 (Équipe: {MY_TEAM_NAME})")
    print(f"==================================================")
    
    base_url = f"https://page.spordle.com/fr/lhqca/schedule-stats-standings/{LEAGUE_UUID}"
    
    urls_to_scrape = {
        "roster": f"https://page.spordle.com/fr/lhqca/teams/{TEAM_ID}?tab=roster",
        "schedule": f"https://page.spordle.com/fr/lhqca/teams/{TEAM_ID}?tab=schedule",
        "standings": f"https://page.spordle.com/fr/lhqca/teams/{TEAM_ID}?tab=standings",
        "standings_ligue": f"{base_url}?scheduleId={SCHEDULE_SAISON_REGULIERE}&tab=standings",
        "stats_hors_concours": f"{base_url}?scheduleId={SCHEDULE_HORS_CONCOURS}&tab=playerstats",
        "stats_saison_reguliere": f"{base_url}?scheduleId={SCHEDULE_SAISON_REGULIERE}&tab=playerstats"
    }

    scraped_html = {}
    saison_ok = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-CA",
        )
        page = await context.new_page()

        try:
            print("[SESSION] Initialisation de la session Spordle...")
            await page.goto("https://page.spordle.com/fr/lhqca", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            cookie_btn = page.locator("button:has-text('Accepter')").or_(page.locator("button:has-text('Accept')"))
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                print("[SESSION] Cookies acceptés.")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[SESSION NOTE] {e}")

        for key, url in urls_to_scrape.items():
            try:
                print(f"[SCRAPE] Chargement de '{key}'...")
                for essai in (1, 2):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        break
                    except Exception as e:
                        if essai == 2:
                            raise
                        print(f"[SCRAPE RETRY] '{key}' : {e} — nouvel essai dans 5 s")
                        await page.wait_for_timeout(5000)
                
                # Attente dynamique spécifique pour l'onglet Roster
                if key == "roster":
                    try:
                        await page.wait_for_selector("text=Position", timeout=8000)
                    except Exception:
                        print("[ROSTER RETRY] Attente du texte Position dépassée, tentative de scroll...")
                
                await page.wait_for_timeout(3500)

                # Horaire : passer du filtre « 7 prochains jours » à la saison complète
                # Schedule: switch the "next 7 days" filter to the whole season
                if key == "schedule":
                    for _ in range(20):
                        if await page.locator(".spdl-skeleton").count() == 0:
                            break
                        await page.wait_for_timeout(1000)
                    # Vue « 7 prochains jours » : contient les matchs à venir que la vue « Saison » peut omettre.
                    # "Next 7 days" view: holds upcoming games the "Season" view may leave out.
                    scraped_html["schedule_7j"] = await page.content()
                    for essai in (1, 2):
                        for etape, sel in (("filtre", "button:has-text('prochains jours'), button:has-text('prochain jour'), button:has-text('jours')"),
                                           ("saison", "li:has-text('Saison')"),
                                           ("appliquer", "button:has-text('Appliquer')")):
                            try:
                                el = page.locator(sel).first
                                await el.wait_for(state="visible", timeout=15000)
                                print(f"[SCHEDULE] Clic '{etape}': {(await el.inner_text()).strip()[:40]}")
                                await el.click(timeout=5000)
                                await page.wait_for_timeout(1500)
                            except Exception as e:
                                print(f"[SCHEDULE] Clic '{etape}' impossible: {e}")
                        await page.wait_for_timeout(2000)
                        try:
                            libelle = (await page.locator("button:has-text('Saison'), button:has-text('jours')").first.inner_text()).strip()
                        except Exception:
                            libelle = ""
                        saison_ok = "saison" in libelle.lower()
                        print(f"[SCHEDULE] Filtre après essai {essai} : '{libelle[:40]}' -> {'saison complète' if saison_ok else 'NON appliqué'}")
                        if saison_ok:
                            break
                    for _ in range(30):
                        if await page.locator(".spdl-skeleton").count() == 0 and await page.locator("article[itemtype*='SportsEvent']").count() > 0:
                            break
                        await page.wait_for_timeout(1000)
                    await page.wait_for_timeout(2000)
                    nb_matchs = await page.locator("article[itemtype*='SportsEvent']").count()
                    print(f"[SCHEDULE] {nb_matchs} match(s) affiché(s).")
                    # Capturer avant le défilement : il fait disparaître les cartes de match.
                    # Capture before scrolling: scrolling makes the game cards disappear.
                    html_content = await page.content()
                    scraped_html[key] = html_content
                    download_logos(BeautifulSoup(html_content, "html.parser"))
                    continue

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

                html_content = await page.content()
                scraped_html[key] = html_content
                download_logos(BeautifulSoup(html_content, "html.parser"))
            except Exception as e:
                print(f"[SCRAPE ERROR] Échec sur {key}: {e}")
                scraped_html[key] = ""

        await browser.close()

    print("\n[PARSING] Traitement des données extraites...")
    roster_texte = parse_roster_structured(scraped_html.get("roster", ""))
    roster_data = parse_roster_table(scraped_html.get("roster", ""))
    if not (roster_data["joueurs"] or roster_data["gardiens"]):
        print("[ROSTER] Tableau illisible : lecteur texte utilisé en repli.")
        roster_data = roster_texte
    else:
        # Ajouter la position lue par l'ancien lecteur, par numéro / add position from the text reader, by number
        pos = {p["numero"]: p.get("position") for p in roster_texte["joueurs"] + roster_texte["gardiens"]}
        for p in roster_data["gardiens"]:
            p["position"] = "G"
        for p in roster_data["joueurs"]:
            if pos.get(p.get("numero")):
                p["position"] = pos[p["numero"]]
        if not roster_data["personnel"]:
            roster_data["personnel"] = roster_texte["personnel"]
    schedule_data = parse_schedule_structured(scraped_html.get("schedule", ""))
    matchs = []
    for vue in ("schedule", "schedule_7j"):
        for m in parse_schedule_cards(scraped_html.get(vue, "")):
            cle = (m.get("numero") or "", m.get("date_iso"), tuple(m.get("equipes", [])))
            if not any((x.get("numero") or "", x.get("date_iso"), tuple(x.get("equipes", []))) == cle for x in matchs):
                matchs.append(m)
    joues = sorted([m for m in matchs if m["joue"]], key=lambda m: m.get("date_iso", ""))
    a_venir = sorted([m for m in matchs if not m["joue"]], key=lambda m: m.get("date_iso", ""))
    last_match = joues[-1] if joues else None
    next_match = a_venir[0] if a_venir else None
    print(f"[SCHEDULE] {len(joues)} joué(s), {len(a_venir)} à venir.")
    player_stats_hc = parse_table_generic(scraped_html.get("stats_hors_concours", ""))
    player_stats_sr = parse_table_generic(scraped_html.get("stats_saison_reguliere", ""))
    standings_list = parse_standings(scraped_html.get("standings", ""))
    division, rang_ligue, nb_ligue, ligue = parse_standings_ligue(scraped_html.get("standings_ligue", ""))

    for r in standings_list:
        for cle in ("V", "D"):
            if not str(r.get(cle, "")).strip().isdigit():
                nombres = [int(r[cle + x]) for x in ("R", "P", "F") if str(r.get(cle + x, "")).strip().isdigit()]
                if nombres:
                    r[cle] = str(sum(nombres))
    my_team_info = next((t for t in standings_list if MY_TEAM_NAME in t.get("Équipe", "").upper()), None)
    player_info_hc = next((p for p in player_stats_hc if TRACKED_PLAYER in p.get("Nom", "").lower()), None) if TRACKED_PLAYER else None
    player_info_sr = next((p for p in player_stats_sr if TRACKED_PLAYER in p.get("Nom", "").lower()), None) if TRACKED_PLAYER else None

    # Une page en échec (réseau, blocage) ne doit pas effacer les données déjà publiées (messages retenus).
    # A failed page (network, blocking) must not wipe data already published (retained messages).
    ok = {k: bool(scraped_html.get(k)) for k in urls_to_scrape}
    echecs = [k for k, v in ok.items() if not v]
    if echecs:
        print(f"[PUBLICATION] Pages en échec, capteurs conservés : {', '.join(echecs)}")
    if ok["schedule"] and not joues and not saison_ok:
        print("[PUBLICATION] Filtre « Saison » non appliqué : dernier match conservé.")

    print("\n[MQTT] Début de la publication sur le broker...")

    total_joueurs = len(roster_data["joueurs"]) + len(roster_data["gardiens"])
    # Page bloquée ou vide : garder l'alignement déjà publié (message MQTT retenu) au lieu de l'effacer.
    # Blocked or empty page: keep the roster already published (retained MQTT message) instead of wiping it.
    if total_joueurs == 0:
        print("[ROSTER] Aucun joueur lu : alignement précédent conservé.")
    publish_to_mqtt(f"homeassistant/sensor/spordle_{TEAM_ID}_roster/config", {
        "name": f"Spordle Équipe {TEAM_ID} Alignement",
        "unique_id": f"spordle_team_{TEAM_ID}_roster",
        "state_topic": f"spordle/{TEAM_ID}/roster/state",
        "json_attributes_topic": f"spordle/{TEAM_ID}/roster/attributes",
        "icon": "mdi:account-group"
    })
    if total_joueurs:
        publish_to_mqtt(f"spordle/{TEAM_ID}/roster/state", f"{total_joueurs} joueurs | {len(roster_data['personnel'])} instructeurs")
        publish_to_mqtt(f"spordle/{TEAM_ID}/roster/attributes", roster_data)

    if next_match:
        prochain_match = f"{next_match['date']} {next_match['heure']} - {next_match['arene']}".strip()
    else:
        prochain_match = "Aucun match prévu"
    schedule_data.update({"prochain_match": next_match, "matchs_a_venir": a_venir, "nb_total": len(matchs)})
    publish_to_mqtt(f"homeassistant/sensor/spordle_{TEAM_ID}_schedule/config", {
        "name": f"Spordle Équipe {TEAM_ID} Horaire",
        "unique_id": f"spordle_team_{TEAM_ID}_schedule",
        "state_topic": f"spordle/{TEAM_ID}/schedule/state",
        "json_attributes_topic": f"spordle/{TEAM_ID}/schedule/attributes",
        "icon": "mdi:calendar-clock"
    })
    if ok["schedule"]:
        publish_to_mqtt(f"spordle/{TEAM_ID}/schedule/state", prochain_match)
        publish_to_mqtt(f"spordle/{TEAM_ID}/schedule/attributes", schedule_data)

    if last_match:
        last_state = f"{last_match['date']} : {' '.join(last_match['equipes'])} {last_match['score']}"
    else:
        last_state = "Aucun match joué"
    publish_to_mqtt(f"homeassistant/sensor/spordle_{TEAM_ID}_last_match/config", {
        "name": f"Spordle Équipe {TEAM_ID} Dernier match",
        "unique_id": f"spordle_team_{TEAM_ID}_last_match",
        "state_topic": f"spordle/{TEAM_ID}/last_match/state",
        "json_attributes_topic": f"spordle/{TEAM_ID}/last_match/attributes",
        "icon": "mdi:scoreboard"
    })
    if ok["schedule"] and (joues or saison_ok):
        publish_to_mqtt(f"spordle/{TEAM_ID}/last_match/state", last_state)
        publish_to_mqtt(f"spordle/{TEAM_ID}/last_match/attributes", {"match": last_match, "tous_les_matchs_joues": joues})

    publish_to_mqtt(f"homeassistant/sensor/spordle_{TEAM_ID}_standings/config", {
        "name": f"Spordle Classement {MY_TEAM_NAME.capitalize()}",
        "unique_id": f"spordle_team_{TEAM_ID}_standings",
        "state_topic": f"spordle/{TEAM_ID}/standings/state",
        "json_attributes_topic": f"spordle/{TEAM_ID}/standings/attributes",
        "icon": "mdi:trophy"
    })
    if ok["standings"]:
        publish_to_mqtt(f"spordle/{TEAM_ID}/standings/state", f"{my_team_info.get('#', 'N/A')}e rang" if my_team_info else "Saison en cours")
        publish_to_mqtt(f"spordle/{TEAM_ID}/standings/attributes", {
            "mon_equipe": my_team_info,
            "classement_complet": standings_list,
            "classement_division": division,
            "rang_ligue": rang_ligue,
            "nb_equipes_ligue": nb_ligue,
            "classement_ligue": ligue,
        })

    if TRACKED_PLAYER and (ok["stats_hors_concours"] or ok["stats_saison_reguliere"]):
        player_slug = re.sub(r'[^a-zA-Z0-9]', '_', TRACKED_PLAYER)
        pts_hc = player_info_hc.get("PTS", "0") if player_info_hc else "0"
        pts_sr = player_info_sr.get("PTS", "0") if player_info_sr else "0"
        
        publish_to_mqtt(f"homeassistant/sensor/spordle_player_{player_slug}/config", {
            "name": f"Spordle Joueur {TRACKED_PLAYER.capitalize()}",
            "unique_id": f"spordle_player_{player_slug}",
            "state_topic": f"spordle/player/{player_slug}/state",
            "json_attributes_topic": f"spordle/player/{player_slug}/attributes",
            "icon": "mdi:account-star"
        })
        publish_to_mqtt(f"spordle/player/{player_slug}/state", f"SR: {pts_sr} pts | HC: {pts_hc} pts")
        publish_to_mqtt(f"spordle/player/{player_slug}/attributes", {"stats_saison_reguliere": player_info_sr, "stats_hors_concours": player_info_hc})

    for key, data_list in [("stats_hors_concours", player_stats_hc), ("stats_saison_reguliere", player_stats_sr)]:
        publish_to_mqtt(f"homeassistant/sensor/spordle_{TEAM_ID}_{key}/config", {
            "name": f"Spordle Équipe {TEAM_ID} {key.replace('_', ' ').capitalize()}",
            "unique_id": f"spordle_team_{TEAM_ID}_{key}",
            "state_topic": f"spordle/{TEAM_ID}/{key}/state",
            "json_attributes_topic": f"spordle/{TEAM_ID}/{key}/attributes",
            "icon": "mdi:hockey-sticks"
        })
        if ok[key]:
            publish_to_mqtt(f"spordle/{TEAM_ID}/{key}/state", f"{len(data_list)} joueurs")
            publish_to_mqtt(f"spordle/{TEAM_ID}/{key}/attributes", {"joueurs": data_list})

    print("\n[FIN] Cycle terminé" + (f" ({len(echecs)} page(s) en échec)." if echecs else " avec succès."))

if __name__ == "__main__":
    while True:
        asyncio.run(scrape_and_publish())
        print(f"\n[ATTENTE] Prochaine mise à jour dans {INTERVAL / 3600} heures...")
        time.sleep(INTERVAL)
