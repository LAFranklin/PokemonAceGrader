import re
import requests
import pyodbc
from difflib import SequenceMatcher
import botocore  
import botocore.session  
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
import json

# -----------------------------
# DB CONFIG
# -----------------------------

SQL_SERVER = "database-1.cdgee08us4is.eu-west-2.rds.amazonaws.com,1433"
SQL_DATABASE = "Pokemon"
SQL_USER = ""
SQL_PASSWORD = ""

# -----------------------------
# GET DATABASE CREDS
# -----------------------------

def get_secret():
    global SQL_USER, SQL_PASSWORD
    client = botocore.session.get_session().create_client('secretsmanager', region_name='eu-west-2')
    cache_config = SecretCacheConfig()
    cache = SecretCache(config=cache_config, client=client)

    secret = cache.get_secret_string('rds!db-74390ece-2c7e-4537-8547-47f190ac8c2d')
    secret_json = json.loads(secret)

    SQL_USER = secret_json["username"]
    SQL_PASSWORD = secret_json["password"]


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


# -----------------------------
# MATCHING CONFIG
# -----------------------------

SETS_API_URL = "https://api.tcgdex.net/v2/en/sets"

ACE_KEYWORDS = ["ace"]
EXCLUDE_KEYWORDS = ["psa", "bundle", "bundles", "lot", "lots"]

SET_MATCH_THRESHOLD = 0.65


# -----------------------------
# HELPERS
# -----------------------------

def normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', s.lower()).strip()

def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# -----------------------------
# TITLE PARSING
# -----------------------------

def is_valid_ace_title(title: str) -> bool:
    t = title.lower()
    if not any(k in t for k in ACE_KEYWORDS):
        return False
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return False
    return True

def extract_grade(title: str):
    m = re.search(r'ace\s*(8|9|10)', title.lower())
    if m:
        return f"ACE {m.group(1)}"
    return None

def extract_collector_token(title: str):
    m = re.search(r'([A-Za-z0-9]+)\/([A-Za-z0-9]+)', title)
    if m:
        return m.group(1)
    return None

def extract_set_phrase_from_title(title: str):
    m = re.search(r'[A-Za-z0-9]+\/[A-Za-z0-9]+\s+(.+)', title)
    if not m:
        return None

    tail = m.group(1)
    tail = re.sub(r'\b20\d{2}\b', '', tail).strip()
    words = tail.split()
    if not words:
        return None

    return " ".join(words[:4])


# -----------------------------
# LOAD SETS FROM API
# -----------------------------

def load_sets_from_api():
    print("Fetching sets from tcgdex API…")
    resp = requests.get(SETS_API_URL)
    resp.raise_for_status()
    data = resp.json()

    sets = []
    for s in data:
        sets.append({
            "id": s.get("id"),
            "name": s.get("name", ""),
            "logo": s.get("logo"),
            "symbol": s.get("symbol"),
            "total_cards": s.get("cardCount", {}).get("total"),
            "official_cards": s.get("cardCount", {}).get("official")
        })

    print(f"Loaded {len(sets)} sets.")
    return sets


# -----------------------------
# SET MATCHING (RESTORED)
# -----------------------------

def find_best_set_match(set_phrase: str, sets):
    best = None
    best_score = 0.0

    for s in sets:
        score = fuzzy_ratio(set_phrase, s["name"])
        if score > best_score:
            best_score = score
            best = s

    if best and best_score >= SET_MATCH_THRESHOLD:
        return best, best_score

    return None, 0.0


# -----------------------------
# SAVE SETS TO DB
# -----------------------------

def save_sets_to_db(sets):
    print("Saving sets to DB…")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("TRUNCATE TABLE tcgdex_sets")

    for s in sets:
        cursor.execute("""
            INSERT INTO tcgdex_sets (id, name, logo, symbol, total_cards, official_cards)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            s["id"],
            s["name"],
            s["logo"],
            s["symbol"],
            s["total_cards"],
            s["official_cards"]
        ))

    conn.commit()
    conn.close()
    print("Sets saved successfully.")


# -----------------------------
# LOAD POKEMON CARDS FROM DB
# -----------------------------

def load_pokemon_cards_from_db():
    print("Loading Pokémon cards from DB…")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, set_id, localId, name
        FROM pokemon_cards
    """)

    cards_by_key = {}

    for row in cursor.fetchall():
        set_id = row.set_id
        local_id = row.localId

        if not set_id or not local_id:
            continue

        key = (set_id, local_id)
        cards_by_key[key] = {
            "id": row.id,
            "name": row.name,
            "set_id": set_id,
            "localId": local_id
        }

    conn.close()
    print(f"Loaded {len(cards_by_key)} Pokémon cards.")
    return cards_by_key


def find_card_for_sale(set_id: str, collector_token: str, cards_by_key):
    candidates = set()

    if re.search(r'[A-Za-z]', collector_token):
        candidates.add(collector_token)
    else:
        stripped = collector_token.lstrip("0") or "0"
        padded3 = stripped.zfill(3)

        candidates.update([collector_token, stripped, padded3])

    for local_id in candidates:
        key = (set_id, local_id)
        if key in cards_by_key:
            return cards_by_key[key]

    return None


# -----------------------------
# PROCESS ACE SALES
# -----------------------------

def process_ace_sales():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, price, sold_date, best_offer_accepted
        FROM ace_ebay_sales
        WHERE pokemon_card_id IS NULL
    """)

    rows = cursor.fetchall()
    print(f"Found {len(rows)} unmatched ACE sales.")

    sets = load_sets_from_api()
    cards_by_key = load_pokemon_cards_from_db()

    matched_count = 0

    for sale in rows:
        title = sale.title
        best_offer = sale.best_offer_accepted.lower()

        if best_offer == "yes":
            continue
        if not is_valid_ace_title(title):
            continue

        grade = extract_grade(title)
        if not grade:
            continue

        collector_token = extract_collector_token(title)
        if not collector_token:
            continue

        set_phrase = extract_set_phrase_from_title(title)
        if not set_phrase:
            continue

        best_set, score = find_best_set_match(set_phrase, sets)
        if not best_set:
            continue

        set_id = best_set["id"]

        card = find_card_for_sale(set_id, collector_token, cards_by_key)
        if not card:
            continue

        cursor.execute("""
            UPDATE ace_ebay_sales
            SET pokemon_card_id = ?,
                grade = ?,
                collector_token = ?,
                set_phrase = ?,
                set_match_score = ?,
                database_updated_at = SYSUTCDATETIME()
            WHERE id = ?
        """, 
        card["id"],
        grade,
        collector_token,
        set_phrase,
        float(score),
        sale.id)

        matched_count += 1

    conn.commit()
    conn.close()

    print(f"Done! Matched {matched_count} ACE sales to Pokémon cards.")


# -----------------------------
# MAIN
# -----------------------------

def main():
    get_secret()

    # NEW: refresh sets table
    sets = load_sets_from_api()
    save_sets_to_db(sets)

    # Existing ACE matching pipeline
    process_ace_sales()


if __name__ == "__main__":
    main()
