import pyodbc

SQL_SERVER = "database-1.cdgee08us4is.eu-west-2.rds.amazonaws.com,1433"
SQL_DATABASE = "Pokemon"
SQL_USER = "admin"
SQL_PASSWORD = "dzz<[kqP~jnBbGI)9e:2xr1e7|rI"  # change this

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

def cleanup_duplicates():
    conn = get_connection()
    cursor = conn.cursor()

    print("Removing duplicate ACE sales…")

    cursor.execute("""
        ;WITH Duplicates AS (
            SELECT
                id,
                title,
                sold_date,
                price,
                best_offer_accepted,
                ROW_NUMBER() OVER (
                    PARTITION BY title, sold_date, price, best_offer_accepted
                    ORDER BY id DESC
                ) AS rn
            FROM ace_ebay_sales
        )
        DELETE FROM Duplicates
        WHERE rn > 1;
    """)

    conn.commit()
    conn.close()

    print("Duplicate cleanup complete.")

if __name__ == "__main__":
    cleanup_duplicates()
