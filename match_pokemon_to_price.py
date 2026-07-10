import requests
import pyodbc
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
    client = botocore.session.get_session().create_client(
        'secretsmanager',
        region_name='eu-west-2'
    )
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
# LOAD SETS FROM API
# -----------------------------

SETS_API_URL = "https://api.tcgdex.net/v2/en/sets"

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
# CALL STORED PROCEDURE
# -----------------------------

def update_ace_sales_grading():
    print("Calling usp_UpdateAceEbaySalesGrading…")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("EXEC usp_UpdateAceEbaySalesGrading")

    conn.commit()
    conn.close()
    print("Stored procedure completed.")


# -----------------------------
# MAIN
# -----------------------------

def main():
    get_secret()

    # Refresh sets table
    sets = load_sets_from_api()
    save_sets_to_db(sets)

    # NEW: Stored procedure handles all matching now
    update_ace_sales_grading()


if __name__ == "__main__":
    main()
