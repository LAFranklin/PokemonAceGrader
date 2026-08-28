"""AWS Lambda entry point for the TCGdex downloader.

Processes a page-bounded chunk and automatically invokes itself with the next
page until TCGdex has no more cards. The chunk size is intentionally conservative
because a full run can take much longer than Lambda's maximum single invocation.
"""

import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

import boto3
import pyodbc
import requests

BASE_API_URL = "https://api.tcgdex.net/v2/en/cards"
REQUEST_DELAY = float(os.environ.get("TCGDEX_REQUEST_DELAY", "0.15"))
ITEMS_PER_PAGE = int(os.environ.get("TCGDEX_ITEMS_PER_PAGE", "100"))
DB_SECRET_NAME = os.environ.get(
    "TCGDEX_DB_SECRET_NAME",
    "rds!db-74390ece-2c7e-4537-8547-47f190ac8c2d",
)
MAX_PAGES_PER_INVOCATION = int(os.environ.get("TCGDEX_MAX_PAGES", "30"))
AUTO_CHAIN = os.environ.get("TCGDEX_AUTO_CHAIN", "true").lower() == "true"
SQL_SERVER = "database-1.cdgee08us4is.eu-west-2.rds.amazonaws.com,1433"
SQL_DATABASE = "Pokemon"

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
    name = source.name, localId = source.localId, category = source.category,
    rarity = source.rarity, set_id = source.set_id, set_name = source.set_name,
    set_series = source.set_series, artist = source.artist, illustrator = source.illustrator,
    hp = source.hp, types = source.types, stage = source.stage,
    attack_count = source.attack_count, attacks_json = source.attacks_json,
    weaknesses_json = source.weaknesses_json, resistances_json = source.resistances_json,
    retreat = source.retreat, regulation_mark = source.regulation_mark,
    image_small = source.image_small, image_high = source.image_high,
    variants_json = source.variants_json, card_updated_at = source.card_updated_at,
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


def load_db_credentials():
    client = boto3.client("secretsmanager", region_name="eu-west-2")
    response = client.get_secret_value(SecretId=DB_SECRET_NAME)
    data = json.loads(response.get("SecretString", "{}"))
    if not data.get("username") or not data.get("password"):
        raise RuntimeError("RDS secret does not contain username/password")
    return data


def get_connection():
    db = load_db_credentials()
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={db['username']};"
        f"PWD={db['password']};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def process_card(card, cursor):
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
        card.get("id"), card.get("name", ""), card.get("localId", ""),
        card.get("category", ""), card.get("rarity", ""), set_data.get("id", ""),
        set_data.get("name", ""), serie.get("name", ""), card.get("artist", ""),
        card.get("illustrator", ""), card.get("hp", ""),
        ", ".join(card.get("types", []) or []), card.get("stage", ""), len(attacks),
        json.dumps(attacks), json.dumps(weaknesses), json.dumps(resistances),
        card.get("retreat", 0), card.get("regulationMark", ""), image_small,
        image_high, json.dumps(variants), card.get("updated", "")
    ]
    cursor.execute(MERGE_CARD_SQL, metadata_params)

    pricing = card.get("pricing", {}) or {}
    cm = pricing.get("cardmarket", {}) or {}
    tcg = pricing.get("tcgplayer", {}) or {}
    scraped_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if cm.get("updated"):
        cm_params = [
            card["id"], scraped_at, cm.get("updated"), cm.get("avg1"), cm.get("avg7"),
            cm.get("avg30"), cm.get("low"), cm.get("trend"), cm.get("reverseHoloSell"),
            cm.get("reverseHoloLow"), cm.get("reverseHoloTrend"), cm.get("avg"),
            cm.get("low"), cm.get("trend"), cm.get("avg1"), cm.get("avg7"),
            cm.get("avg30"), cm.get("avg-holo"), cm.get("low-holo"), cm.get("trend-holo"),
            tcg.get("normal", {}).get("marketPrice"),
            tcg.get("reverse", {}).get("marketPrice"),
            tcg.get("holofoil", {}).get("marketPrice"),
        ]
        cursor.execute(INSERT_CARDMARKET_SQL, cm_params)

    if tcg.get("updated"):
        cursor.execute(INSERT_TCGPLAYER_SQL, [
            card["id"], scraped_at, tcg.get("updated"), json.dumps(tcg)
        ])


def process_page(session, cursor, conn, page):
    list_url = (
        f"{BASE_API_URL}?pagination:page={page}"
        f"&pagination:itemsPerPage={ITEMS_PER_PAGE}"
    )
    print(f"Fetching page {page}")
    response = session.get(list_url, timeout=60)
    response.raise_for_status()
    cards = response.json()

    if not cards:
        return 0

    processed = 0
    for stub in cards:
        card_id = stub.get("id")
        if not card_id:
            continue

        detail_url = f"{BASE_API_URL}/{quote(card_id, safe='')}"
        try:
            detail = session.get(detail_url, timeout=60)
            detail.raise_for_status()
            card = detail.json()
            process_card(card, cursor)
            processed += 1
        except Exception as exc:
            print(f"Detail error {card_id}: {exc}")
            continue

        if REQUEST_DELAY:
            time.sleep(REQUEST_DELAY)

    conn.commit()
    print(f"Page {page} committed: {processed} cards")
    return processed


def invoke_next_page(next_page):
    if not AUTO_CHAIN:
        return

    client = boto3.client("lambda", region_name="eu-west-2")
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        raise RuntimeError("AWS_LAMBDA_FUNCTION_NAME is not available")

    payload = {
        "start_page": next_page,
        "max_pages": MAX_PAGES_PER_INVOCATION,
    }
    print(f"Chaining next invocation: start_page={next_page}")
    client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def lambda_handler(event, context):
    event = event or {}
    start_page = max(1, int(event.get("start_page", 1)))
    max_pages = max(1, int(event.get("max_pages", MAX_PAGES_PER_INVOCATION)))

    print(f"Starting TCGdex Lambda: start_page={start_page}, max_pages={max_pages}")

    session = requests.Session()
    conn = get_connection()
    cursor = conn.cursor()
    pages_processed = 0
    cards_processed = 0
    next_page = start_page
    complete = False

    try:
        for page in range(start_page, start_page + max_pages):
            # Leave two minutes of headroom for database closeout and chaining.
            if context and context.get_remaining_time_in_millis() < 120_000:
                print("Stopping with less than 2 minutes remaining")
                break

            count = process_page(session, cursor, conn, page)
            if count == 0:
                print("No more cards. Download complete.")
                next_page = None
                complete = True
                break

            pages_processed += 1
            cards_processed += count
            next_page = page + 1
    finally:
        cursor.close()
        conn.close()

    if next_page is not None:
        invoke_next_page(next_page)

    result = {
        "status": "complete" if complete else "chained" if next_page is not None else "paused",
        "start_page": start_page,
        "pages_processed": pages_processed,
        "cards_processed": cards_processed,
        "next_page": next_page,
        "auto_chain": AUTO_CHAIN,
    }
    print(json.dumps(result))
    return {"statusCode": 200, "body": json.dumps(result)}
