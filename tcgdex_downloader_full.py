import requests
import csv
import time
import os
import json
from datetime import datetime
from urllib.parse import quote

# ===================================
# CONFIG
# ===================================

BASE_API_URL = "https://api.tcgdex.net/v2/en/cards"
OUTPUT_FILE = "pokemon_cards_full.csv"
CHECKPOINT_FILE = "checkpoint_cards_full.txt"
REQUEST_DELAY = 0.15
ITEMS_PER_PAGE = 100

# ===================================
# CSV HEADERS (UPDATED)
# ===================================

HEADERS = [
    "id", "name", "localId", "category", "rarity",
    "set_id", "set_name", "set_series",
    "artist", "illustrator", "hp",
    "types", "stage",
    "attack_count", "attacks_json",
    "weaknesses_json", "resistances_json",
    "retreat",
    "regulation_mark",
    "image_small", "image_high",
    "variants_json",

    # NEW FIELD
    "card_updated_at",

    # CARDMARKET
    "cardmarket_url",
    "cardmarket_updated_at",
    "cardmarket_avg1",
    "cardmarket_avg7",
    "cardmarket_avg30",
    "cardmarket_low",
    "cardmarket_trend",
    "cardmarket_reverse_holo_sell",
    "cardmarket_reverse_holo_low",
    "cardmarket_reverse_holo_trend",

    # TCGPLAYER
    "tcgplayer_updated_at",
    "tcgplayer_prices_json",

    # DUPLICATES REMOVED
    "cm_avg",
    "cm_low",
    "cm_trend",
    "cm_avg1_dup",
    "cm_avg7_dup",
    "cm_avg30_dup",
    "cm_avg_holo",
    "cm_low_holo",
    "cm_trend_holo",

    "normal_market",
    "reverse_market",
    "holo_market",

    "raw_estimate",
    "ace8_estimate",
    "ace9_estimate",
    "ace10_estimate"
]

# ===================================
# TIMESTAMP PARSER
# ===================================

def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return None

# ===================================
# LOAD EXISTING CSV INTO MEMORY
# ===================================

existing_rows = {}

if os.path.exists(OUTPUT_FILE):
    print("Loading existing CSV...")
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_rows[row["id"]] = row
    print(f"Loaded {len(existing_rows)} existing rows")

# ===================================
# MAIN SCRAPING LOOP
# ===================================

session = requests.Session()
updated_rows = {}  # final output

page = 1
while True:
    print(f"\nFetching card list page {page}")

    list_url = (
        f"{BASE_API_URL}"
        f"?pagination:page={page}"
        f"&pagination:itemsPerPage={ITEMS_PER_PAGE}"
    )

    try:
        response = session.get(list_url, timeout=60)
        if response.status_code != 200:
            print(f"List API failed: {response.status_code}")
            time.sleep(10)
            continue
        cards = response.json()
    except Exception as e:
        print(f"LIST ERROR: {e}")
        time.sleep(10)
        continue

    if not cards:
        print("No more cards found")
        break

    for card_stub in cards:
        card_id = card_stub.get("id", "")
        if not card_id:
            continue

        encoded_card_id = quote(card_id, safe="")
        details_url = f"{BASE_API_URL}/{encoded_card_id}"

        try:
            details_response = session.get(details_url, timeout=60)
            if details_response.status_code != 200:
                print(f"Detail failed {card_id}: {details_response.status_code}")
                continue
            card = details_response.json()
        except Exception as e:
            print(f"DETAIL ERROR {card_id}: {e}")
            continue

        # ===================================
        # TIMESTAMPS
        # ===================================

        api_card_updated = card.get("updated", "")

        pricing = card.get("pricing", {}) or {}
        cardmarket = pricing.get("cardmarket", {}) or {}
        tcgplayer = pricing.get("tcgplayer", {}) or {}

        api_cm_updated = cardmarket.get("updated", "")
        api_tcg_updated = tcgplayer.get("updated", "")

        existing = existing_rows.get(card_id)

        update_metadata = False
        update_pricing = False

        if existing:
            old_card_updated = existing.get("card_updated_at", "")
            old_cm_updated = existing.get("cardmarket_updated_at", "")
            old_tcg_updated = existing.get("tcgplayer_updated_at", "")

            # Compare metadata timestamps
            if parse_ts(api_card_updated) and parse_ts(old_card_updated):
                if parse_ts(api_card_updated) > parse_ts(old_card_updated):
                    update_metadata = True

            # Compare pricing timestamps
            if parse_ts(api_cm_updated) and parse_ts(old_cm_updated):
                if parse_ts(api_cm_updated) > parse_ts(old_cm_updated):
                    update_pricing = True

            if parse_ts(api_tcg_updated) and parse_ts(old_tcg_updated):
                if parse_ts(api_tcg_updated) > parse_ts(old_tcg_updated):
                    update_pricing = True

            # Skip if nothing changed
            if not update_metadata and not update_pricing:
                updated_rows[card_id] = existing  # keep old row
                continue

            print(f"Updating {card_id} (metadata={update_metadata}, pricing={update_pricing})")

        else:
            print(f"New card: {card_id}")
            update_metadata = True
            update_pricing = True

        # ===================================
        # BUILD NEW ROW
        # ===================================

        name = card.get("name", "")
        local_id = card.get("localId", "")
        category = card.get("category", "")
        rarity = card.get("rarity", "")

        set_data = card.get("set", {}) or {}
        set_id = set_data.get("id", "")
        set_name = set_data.get("name", "")
        serie = set_data.get("serie", {}) or {}
        set_series = serie.get("name", "")

        artist = card.get("artist", "")
        illustrator = card.get("illustrator", "")
        hp = card.get("hp", "")

        types = card.get("types", [])
        types = ", ".join(types) if isinstance(types, list) else ""

        stage = card.get("stage", "")

        attacks = card.get("attacks", []) or []
        attack_count = len(attacks)
        attacks_json = json.dumps(attacks)

        weaknesses = card.get("weaknesses", []) or []
        weaknesses_json = json.dumps(weaknesses)

        resistances = card.get("resistances", []) or []
        resistances_json = json.dumps(resistances)

        retreat = card.get("retreat", 0)
        regulation_mark = card.get("regulationMark", "")

        image_base = card.get("image", "")
        image_small = f"{image_base}/low.png" if image_base else ""
        image_high = f"{image_base}/high.png" if image_base else ""

        variants = card.get("variants", {}) or {}
        variants_json = json.dumps(variants)

        # Pricing
        cm_avg = cardmarket.get("avg")
        cm_low = cardmarket.get("low")
        cm_trend = cardmarket.get("trend")
        cm_avg1 = cardmarket.get("avg1")
        cm_avg7 = cardmarket.get("avg7")
        cm_avg30 = cardmarket.get("avg30")
        cm_avg_holo = cardmarket.get("avg-holo")
        cm_low_holo = cardmarket.get("low-holo")
        cm_trend_holo = cardmarket.get("trend-holo")

        normal = tcgplayer.get("normal", {}) or {}
        reverse = tcgplayer.get("reverse", {}) or {}
        holofoil = tcgplayer.get("holofoil", {}) or {}

        normal_market = normal.get("marketPrice")
        reverse_market = reverse.get("marketPrice")
        holo_market = holofoil.get("marketPrice")

        tcgplayer_prices_json = json.dumps(tcgplayer)

        raw_estimate = cm_avg30

        ace8_estimate = None
        ace9_estimate = None
        ace10_estimate = None

        row = [
            card_id, name, local_id, category, rarity,
            set_id, set_name, set_series,
            artist, illustrator, hp,
            types, stage,
            attack_count, attacks_json,
            weaknesses_json, resistances_json,
            retreat,
            regulation_mark,
            image_small, image_high,
            variants_json,

            api_card_updated,

            cardmarket.get("url", ""),
            api_cm_updated,
            cm_avg1,
            cm_avg7,
            cm_avg30,
            cm_low,
            cm_trend,
            cardmarket.get("reverseHoloSell", ""),
            cardmarket.get("reverseHoloLow", ""),
            cardmarket.get("reverseHoloTrend", ""),

            api_tcg_updated,
            tcgplayer_prices_json,

            cm_avg,
            cm_low,
            cm_trend,
            cm_avg1,
            cm_avg7,
            cm_avg30,
            cm_avg_holo,
            cm_low_holo,
            cm_trend_holo,

            normal_market,
            reverse_market,
            holo_market,

            raw_estimate,
            ace8_estimate,
            ace9_estimate,
            ace10_estimate
        ]

        updated_rows[card_id] = dict(zip(HEADERS, row))

        time.sleep(REQUEST_DELAY)

    page += 1

# ===================================
# WRITE FINAL CSV
# ===================================

print("\nWriting final CSV...")

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out:
    writer = csv.DictWriter(out, fieldnames=HEADERS)
    writer.writeheader()
    for row in updated_rows.values():
        writer.writerow(row)

print("\nDONE — CSV updated with new and changed cards.")
