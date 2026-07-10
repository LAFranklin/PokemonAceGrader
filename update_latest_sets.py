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
# MAIN
# -----------------------------

def main():
    get_secret()

    save_sets_to_db(sets)

if __name__ == "__main__":
    main()
