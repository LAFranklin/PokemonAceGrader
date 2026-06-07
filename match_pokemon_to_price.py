import csv
import re
import requests
from difflib import SequenceMatcher

# -----------------------------
# CONFIG
# -----------------------------

SETS_API_URL = "https://api.tcgdex.net/v2/en/sets"

ACE_KEYWORDS = ["ace"]
EXCLUDE_KEYWORDS = ["psa", "bundle", "bundles", "lot", "lots"]

SET_MATCH_THRESHOLD = 0.65  # fuzzy match threshold for set names

# -----------------------------
# HELPERS
# -----------------------------

def normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', s.lower()).strip()

def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

# -----------------------------
# TITLE PARSING / FILTERS
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
    """
    Extracts the first part of patterns like:
    - 077/094
    - 291/217
    - GG43/GG70
    Returns '077', '291', 'GG43', etc.
    """
    m = re.search(r'([A-Za-z0-9]+)\/([A-Za-z0-9]+)', title)
    if m:
        return m.group(1)
    return None

def extract_set_phrase_from_title(title: str):
    """
    Extracts the phrase after the collector pattern.
    Example:
      '... 077/094 Phantasmal Flames 2025'
      -> 'Phantasmal Flames'
    """
    m = re.search(r'[A-Za-z0-9]+\/[A-Za-z0-9]+\s+(.+)', title)
    if not m:
        return None

    tail = m.group(1)

    # Remove trailing years like 2025, 2026 etc.
    tail = re.sub(r'\b20\d{2}\b', '', tail).strip()

    # Take first few words as set phrase
    words = tail.split()
    if not words:
        return None

    return " ".join(words[:4])  # up to 4 words

# -----------------------------
# LOAD SETS FROM TCGDEX
# -----------------------------

def load_sets_from_api():
    """
    Loads all sets from tcgdex API.
    Returns a list of dicts: {id, name}
    """
    print("Fetching sets from tcgdex API...")
    resp = requests.get(SETS_API_URL)
    resp.raise_for_status()
    data = resp.json()

    sets = []
    for s in data:
        sets.append({
            "id": s.get("id"),
            "name": s.get("name", "")
        })
    print(f"Loaded {len(sets)} sets from API.")
    return sets

def find_best_set_match(set_phrase: str, sets):
    """
    Fuzzy match the phrase from the ACE title to tcgdex set names.
    Returns (best_set_dict, score) or (None, 0).
    """
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
# LOAD POKEMON CARDS
# -----------------------------

def load_pokemon_cards(path: str):
    """
    Loads pokemon_cards_full.csv and indexes by (set_id, localId).
    """
    cards_by_key = {}

    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            set_id = row.get("set_id")
            local_id = row.get("localId")

            if not set_id or not local_id:
                continue

            key = (set_id, local_id)
            cards_by_key[key] = row

    print(f"Loaded {len(cards_by_key)} cards from {path}")
    return cards_by_key

def find_card_for_sale(set_id: str, collector_token: str, cards_by_key):
    """
    Try multiple variants of the collector token to match localId:
    - raw token (e.g. '077', 'GG43')
    - stripped leading zeros (e.g. '77')
    - zero-padded to 3 digits (e.g. '077')
    """
    candidates = set()

    # Alphanumeric like GG43: keep as is
    if re.search(r'[A-Za-z]', collector_token):
        candidates.add(collector_token)
    else:
        # Numeric: try several forms
        stripped = collector_token.lstrip("0")
        if stripped == "":
            stripped = "0"
        padded3 = stripped.zfill(3)

        candidates.add(collector_token)
        candidates.add(stripped)
        candidates.add(padded3)

    for local_id in candidates:
        key = (set_id, local_id)
        if key in cards_by_key:
            return cards_by_key[key], local_id

    return None, None

# -----------------------------
# PROCESS ACE SALES
# -----------------------------

def process_ace_sales(ace_path: str, cards_by_key, sets, output_path: str):
    output_rows = []

    with open(ace_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            title = row["title"]
            best_offer = row["best_offer_accepted"].strip().lower()

            # Skip best offer accepted
            if best_offer == "yes":
                continue

            # Title filters
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

            # Match set via API data
            best_set, set_score = find_best_set_match(set_phrase, sets)
            if not best_set:
                continue

            set_id = best_set["id"]

            # Find card in pokemon_cards_full by (set_id, localId variants)
            card, matched_local_id = find_card_for_sale(set_id, collector_token, cards_by_key)
            if not card:
                continue

            output_rows.append({
                "id": card["id"],
                "set_id": set_id,
                "localId": matched_local_id,
                "name": card["name"],
                "set_name": card["set_name"],
                "grade": grade,
                "price": row["price"],
                "sold_date": row["sold_date"],
                "title": title,
                "set_phrase_from_title": set_phrase,
                "set_match_name": best_set["name"],
                "set_match_score": round(set_score, 3)
            })

    # Write output CSV
    with open(output_path, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "set_id", "localId", "name", "set_name",
            "grade", "price", "sold_date", "title",
            "set_phrase_from_title", "set_match_name", "set_match_score"
        ])
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Done! Wrote {len(output_rows)} rows to {output_path}")

# -----------------------------
# MAIN
# -----------------------------

def main():
    pokemon_cards_path = "pokemon_cards_full.csv"
    ace_sales_path = "ace_sold_results.csv"
    output_path = "pokemon_ace_mapped_prices.csv"

    sets = load_sets_from_api()
    cards_by_key = load_pokemon_cards(pokemon_cards_path)
    process_ace_sales(ace_sales_path, cards_by_key, sets, output_path)

if __name__ == "__main__":
    main()
