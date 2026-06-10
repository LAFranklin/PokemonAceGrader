import requests
import time
import json
from datetime import datetime
import pyodbc
from urllib.parse import quote

# ===================================
# CONFIG
# ===================================

BASE_API_URL = "https://api.tcgdex.net/v2/en/cards"
REQUEST_DELAY = 0.15
ITEMS_PER_PAGE = 100

#ENTER CONNECTION DETAILS 
SQL_SERVER = "" # replace or load from Secrets Manager
SQL_DATABASE = "" # replace or load from Secrets Manager
SQL_USER = "" # replace or load from Secrets Manager
SQL_PASSWORD = "" # replace or load from Secrets Manager
#ENTER CONNECTION DETAILS 


def get_connection():
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USER};"
        f"PWD={SQL_PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


# ===================================
# SQL STATEMENTS
# ===================================

MERGE_CARD_SQL = """
MERGE pokemon_cards AS target
USING (VALUES (
    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
)) AS source (
    id,name,localId,category,rarity,set_id,set_name,set_series,
    artist,illustrator,hp,types,stage,attack_count,attacks_json,
    weaknesses_json,resistances_json,retreat,regulation_mark,
    image_small,image_high,variants_json,card_updated_at
)
ON target.id = source.id

WHEN MATCHED AND (
    (target.card_updated_at IS NULL AND source.card_updated_at IS NOT NULL)
    OR (target.card_updated_at IS NOT NULL AND source.card_updated_at > target.card_updated_at)
)
THEN UPDATE SET
    name = source.name,
    localId = source.localId,
    category = source.category,
    rarity = source.rarity,
    set_id = source.set_id,
    set_name = source.set_name,
    set_series = source.set_series,
    artist = source.artist,
    illustrator = source.illustrator,
    hp = source.hp,
    types = source.types,
    stage = source.stage,
    attack_count = source.attack_count,
    attacks_json = source.attacks_json,
    weaknesses_json = source.weaknesses_json,
    resistances_json = source.resistances_json,
    retreat = source.retreat,
    regulation_mark = source.regulation_mark,
    image_small = source.image_small,
    image_high = source.image_high,
    variants_json = source.variants_json,
    card_updated_at = source.card_updated_at,
    database_updated_at = SYSUTCDATETIME()

WHEN NOT MATCHED THEN
INSERT (
    id,name,localId,category,rarity,set_id,set_name,set_series,
    artist,illustrator,hp,types,stage,attack_count,attacks_json,
    weaknesses_json,resistances_json,retreat,regulation_mark,
    image_small,image_high,variants_json,card_updated_at,
    database_created_at,database_updated_at
)
VALUES (
    source.id,source.name,source.localId,source.category,source.rarity,
    source.set_id,source.set_name,source.set_series,source.artist,
    source.illustrator,source.hp,source.types,source.stage,
    source.attack_count,source.attacks_json,source.weaknesses_json,
    source.resistances_json,source.retreat,source.regulation_mark,
    source.image_small,source.image_high,source.variants_json,
    source.card_updated_at,SYSUTCDATETIME(),SYSUTCDATETIME()
);
"""

INSERT_CARDMARKET_SQL = """
INSERT INTO cardmarket_pricing (
    card_id, scraped_at, cardmarket_updated_at,
    cardmarket_avg1, cardmarket_avg7, cardmarket_avg30,
    cardmarket_low, cardmarket_trend,
    cardmarket_reverse_holo_sell, cardmarket_reverse_holo_low, cardmarket_reverse_holo_trend,
    cm_avg, cm_low, cm_trend,
    cm_avg1_dup, cm_avg7_dup, cm_avg30_dup,
    cm_avg_holo, cm_low_holo, cm_trend_holo,
    normal_market, reverse_market, holo_market
)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
"""

INSERT_TCGPLAYER_SQL = """
INSERT INTO tcgplayer_pricing (
    card_id, scraped_at, tcgplayer_updated_at, tcgplayer_prices_json
)
VALUES (?,?,?,?);
"""


# ===================================
# HELPERS
# ===================================

def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return None


# ===================================
# MAIN SCRAPER
# ===================================

def process_card(card, cursor):
    """Insert metadata + pricing for a single card."""

    # -------------------------
    # METADATA
    # -------------------------
    set_data = card.get("set", {}) or {}
    serie = set_data.get("serie", {}) or {}

    attacks = card.get("attacks", []) or []
    weaknesses = card.get("weaknesses", []) or []
    resistances = card.get("resistances", []) or []
    variants = card.get("variants", {}) or {}

    image_base = card.get("image", "")
    image_small = f"{image_base}/low.png" if image_base else ""
    image_high = f"{image_base}/high.png" if image_base else ""

    metadata_params = [
        card.get("id"),
        card.get("name", ""),
        card.get("localId", ""),
        card.get("category", ""),
        card.get("rarity", ""),
        set_data.get("id", ""),
        set_data.get("name", ""),
        serie.get("name", ""),
        card.get("artist", ""),
        card.get("illustrator", ""),
        card.get("hp", ""),
        ", ".join(card.get("types", []) or []),
        card.get("stage", ""),
        len(attacks),
        json.dumps(attacks),
        json.dumps(weaknesses),
        json.dumps(resistances),
        card.get("retreat", 0),
        card.get("regulationMark", ""),
        image_small,
        image_high,
        json.dumps(variants),
        card.get("updated", "")
    ]

    cursor.execute(MERGE_CARD_SQL, metadata_params)

    # -------------------------
    # PRICING
    # -------------------------
    pricing = card.get("pricing", {}) or {}
    cm = pricing.get("cardmarket", {}) or {}
    tcg = pricing.get("tcgplayer", {}) or {}

    scraped_at = datetime.utcnow()

    # CARDMARKET
    if cm.get("updated"):
        cm_params = [
            card["id"],
            scraped_at,
            cm.get("updated"),
            cm.get("avg1"),
            cm.get("avg7"),
            cm.get("avg30"),
            cm.get("low"),
            cm.get("trend"),
            cm.get("reverseHoloSell"),
            cm.get("reverseHoloLow"),
            cm.get("reverseHoloTrend"),
            cm.get("avg"),
            cm.get("low"),
            cm.get("trend"),
            cm.get("avg1"),
            cm.get("avg7"),
            cm.get("avg30"),
            cm.get("avg-holo"),
            cm.get("low-holo"),
            cm.get("trend-holo"),
            tcg.get("normal", {}).get("marketPrice"),
            tcg.get("reverse", {}).get("marketPrice"),
            tcg.get("holofoil", {}).get("marketPrice"),
        ]
        cursor.execute(INSERT_CARDMARKET_SQL, cm_params)

    # TCGPLAYER
    if tcg.get("updated"):
        tcg_params = [
            card["id"],
            scraped_at,
            tcg.get("updated"),
            json.dumps(tcg)
        ]
        cursor.execute(INSERT_TCGPLAYER_SQL, tcg_params)


def main():
    session = requests.Session()
    conn = get_connection()
    cursor = conn.cursor()

    page = 1

    while True:
        print(f"\nFetching page {page}")

        list_url = (
            f"{BASE_API_URL}"
            f"?pagination:page={page}"
            f"&pagination:itemsPerPage={ITEMS_PER_PAGE}"
        )

        try:
            resp = session.get(list_url, timeout=60)
            resp.raise_for_status()
            cards = resp.json()
        except Exception as e:
            print(f"List error: {e}")
            time.sleep(5)
            continue

        if not cards:
            print("No more cards.")
            break

        for stub in cards:
            card_id = stub.get("id")
            if not card_id:
                continue

            encoded = quote(card_id, safe="")
            detail_url = f"{BASE_API_URL}/{encoded}"

            try:
                d = session.get(detail_url, timeout=60)
                d.raise_for_status()
                card = d.json()
            except Exception as e:
                print(f"Detail error {card_id}: {e}")
                continue

            print(f"Processing {card_id}")
            process_card(card, cursor)
            conn.commit()

            time.sleep(REQUEST_DELAY)

        page += 1

    conn.close()
    print("\nDONE — Database fully updated.")


if __name__ == "__main__":
    main()
