import requests
import csv
import time
import os
import json

from urllib.parse import quote

# ===================================
# CONFIG
# ===================================

BASE_API_URL = "https://api.tcgdex.net/v2/en/cards"
OUTPUT_FILE = "pokemon_cards_full.csv"
CHECKPOINT_FILE = "checkpoint_cards_full.txt"
REQUEST_DELAY = 0.15
SAVE_EVERY = 20
ITEMS_PER_PAGE = 100

# ===================================
# CSV HEADERS
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
    "cardmarket_url",
    "cardmarket_updated_at",
    "cardmarket_avg1",
    "cardmarket_avg7",
    "cardmarket_avg30",
    "cardmarket_low_price",
    "cardmarket_trend",
    "cardmarket_reverse_holo_sell",
    "cardmarket_reverse_holo_low",
    "cardmarket_reverse_holo_trend",
    "tcgplayer_updated_at",
    "tcgplayer_prices_json",
    "cardmarket_updated_at",
    "cardmarket_avg",
    "cardmarket_low",
    "cardmarket_trend",
    "cardmarket_avg1",
    "cardmarket_avg7",
    "cardmarket_avg30",
    "cardmarket_avg_holo",
    "cardmarket_low_holo",
    "cardmarket_trend_holo",
    "normal_market",
    "reverse_market",
    "holo_market",
    "raw_estimate",
    "ace8_estimate",
    "ace9_estimate",
    "ace10_estimate"
]

# ===================================
# LOAD CHECKPOINT
# ===================================

start_page = 1

if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r") as f:
        try:
            start_page = int(f.read().strip())
            print(f"Resuming from page {start_page}")
        except:
            start_page = 1

# ===================================
# LOAD EXISTING IDS
# ===================================

written_ids = set()
file_exists = os.path.exists(OUTPUT_FILE)

if file_exists:
    print("Loading existing IDs...")
    with open(OUTPUT_FILE, "r", encoding="utf-8") as existing:
        reader = csv.reader(existing)
        next(reader, None)
        for row in reader:
            if row:
                written_ids.add(row[0])
    print(f"Loaded {len(written_ids)} existing IDs")

# ===================================
# OPEN CSV
# ===================================

csv_file = open(OUTPUT_FILE, "a", newline="", encoding="utf-8")
writer = csv.writer(csv_file)

if not file_exists:
    writer.writerow(HEADERS)

# ===================================
# SESSION
# ===================================

session = requests.Session()

# ===================================
# MAIN LOOP
# ===================================

page = start_page

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

    rows_written = 0

    # ===================================
    # LOOP CARDS
    # ===================================

    for card_stub in cards:
        card_id = card_stub.get("id", "")

        if not card_id:
            continue

        if card_id in written_ids:
            continue

        print(f"Fetching details for {card_id}")

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

        written_ids.add(card_id)

        # ===================================
        # BASIC INFO
        # ===================================

        name = card.get("name", "")
        local_id = card.get("localId", "")
        category = card.get("category", "")
        rarity = card.get("rarity", "")

        # ===================================
        # SET
        # ===================================

        set_data = card.get("set")

        if isinstance(set_data, dict):
            set_id = set_data.get("id", "")
            set_name = set_data.get("name", "")
            serie = set_data.get("serie")

            if isinstance(serie, dict):
                set_series = serie.get("name", "")
            else:
                set_series = ""
        else:
            set_id = ""
            set_name = ""
            set_series = ""

        # ===================================
        # DETAILS
        # ===================================

        artist = card.get("artist", "")
        illustrator = card.get("illustrator", "")
        hp = card.get("hp", "")

        # ===================================
        # TYPES
        # ===================================

        types = card.get("types")
        if isinstance(types, list):
            types = ", ".join(types)
        else:
            types = ""

        # ===================================
        # STAGE
        # ===================================

        stage = card.get("stage", "")

        # ===================================
        # ATTACKS
        # ===================================

        attacks = card.get("attacks")
        if not isinstance(attacks, list):
            attacks = []

        attack_count = len(attacks)
        attacks_json = json.dumps(attacks)

        # ===================================
        # WEAKNESSES
        # ===================================

        weaknesses = card.get("weaknesses")
        if not isinstance(weaknesses, list):
            weaknesses = []

        weaknesses_json = json.dumps(weaknesses)

        # ===================================
        # RESISTANCES
        # ===================================

        resistances = card.get("resistances")
        if not isinstance(resistances, list):
            resistances = []

        resistances_json = json.dumps(resistances)

        # ===================================
        # RETREAT
        # ===================================

        retreat = card.get("retreat", 0)

        # ===================================
        # REGULATION MARK
        # ===================================

        regulation_mark = card.get("regulationMark", "")

        # ===================================
        # IMAGES (PNG ONLY, REUSING EXISTING FIELDS)
        # ===================================

        image_base = card.get("image", "")

        if image_base:
            image_small = f"{image_base}/low.png"
            image_high = f"{image_base}/high.png"
        else:
            image_small = ""
            image_high = ""

        # ===================================
        # VARIANTS
        # ===================================

        variants = card.get("variants")
        if not isinstance(variants, dict):
            variants = {}

        variants_json = json.dumps(variants)

        # ===================================
        # PRICING
        # ===================================

        pricing = card.get("pricing", {})
        if not isinstance(pricing, dict):
            pricing = {}

        # CARDMARKET
        cardmarket = pricing.get("cardmarket", {})
        if not isinstance(cardmarket, dict):
            cardmarket = {}

        cardmarket_url = cardmarket.get("url", "")
        cardmarket_updated_at = cardmarket.get("updated", "")

        cm_avg = cardmarket.get("avg")
        cm_low = cardmarket.get("low")
        cm_trend = cardmarket.get("trend")

        cm_avg1 = cardmarket.get("avg1")
        cm_avg7 = cardmarket.get("avg7")
        cm_avg30 = cardmarket.get("avg30")

        cm_avg_holo = cardmarket.get("avg-holo")
        cm_low_holo = cardmarket.get("low-holo")
        cm_trend_holo = cardmarket.get("trend-holo")

        # TCGPLAYER
        tcgplayer = pricing.get("tcgplayer", {})
        if not isinstance(tcgplayer, dict):
            tcgplayer = {}

        tcgplayer_updated_at = tcgplayer.get("updated", "")

        normal = tcgplayer.get("normal", {})
        reverse = tcgplayer.get("reverse", {})
        holofoil = tcgplayer.get("holofoil", {})

        normal_market = normal.get("marketPrice")
        reverse_market = reverse.get("marketPrice")
        holo_market = holofoil.get("marketPrice")

        tcgplayer_prices_json = json.dumps(tcgplayer)

        # ===================================
        # RAW ESTIMATE
        # ===================================

        raw_estimate = cm_avg30

        # ===================================
        # BUILD ROW
        # ===================================

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
            cardmarket_url,
            cardmarket_updated_at,
            cm_avg1,
            cm_avg7,
            cm_avg30,
            cm_low,
            cm_trend,
            cardmarket.get("reverseHoloSell", ""),
            cardmarket.get("reverseHoloLow", ""),
            cardmarket.get("reverseHoloTrend", ""),
            tcgplayer_updated_at,
            tcgplayer_prices_json,
            cardmarket_updated_at,
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

        # ===================================
        # WRITE ROW
        # ===================================

        writer.writerow(row)
        rows_written += 1

        if rows_written % SAVE_EVERY == 0:
            csv_file.flush()
            os.fsync(csv_file.fileno())

            with open(CHECKPOINT_FILE, "w") as checkpoint:
                checkpoint.write(str(page))

            print(f"Flushed {rows_written} rows to disk")

        time.sleep(REQUEST_DELAY)

    # ===================================
    # PAGE COMPLETE
    # ===================================

    csv_file.flush()
    os.fsync(csv_file.fileno())

    with open(CHECKPOINT_FILE, "w") as checkpoint:
        checkpoint.write(str(page + 1))

    print(f"Saved {rows_written} cards from page {page}")

    page += 1

# ===================================
# FINISH
# ===================================

csv_file.close()
print("\nDONE")
