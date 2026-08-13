import sys
import time
import json
import os
from datetime import datetime, date, timezone

import requests
import pyodbc
import botocore.session
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig


# ============================================================
# OUTPUT
# ============================================================

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ============================================================
# CONFIGURATION
# ============================================================

SEARCH_QUERY = "Ace Graded"

SOLDCOMPS_API_URL = "https://api.sold-comps.com/v1/scrape"
SOLDCOMPS_API_KEY = "sc_HpDsIASZYuxsbNOInAfOcgWlZmuZYeSZfUdfMcGdMrdBLbIDxcFMypGpylSyZVTQ"

EBAY_SITE = "ebay.co.uk"

COUNT_PER_PAGE = 240
DEFAULT_DAYS_TO_SCRAPE = 20
SAFETY_BUFFER_DAYS = 1

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

SQL_SERVER = "database-1.cdgee08us4is.eu-west-2.rds.amazonaws.com,1433"
SQL_DATABASE = "Pokemon"
SQL_USER = ""
SQL_PASSWORD = ""

AWS_REGION = "eu-west-2"
AWS_SECRET_NAME = "rds!db-74390ece-2c7e-4537-8547-47f190ac8c2d"


# ============================================================
# SAFE PRINT
# ============================================================

def safe_print(value):
    print(str(value).encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# GET DATABASE CREDENTIALS
# ============================================================

def get_secret():
    global SQL_USER
    global SQL_PASSWORD

    safe_print("Loading database credentials from AWS Secrets Manager...")

    client = botocore.session.get_session().create_client(
        "secretsmanager",
        region_name=AWS_REGION
    )

    cache_config = SecretCacheConfig()
    cache = SecretCache(config=cache_config, client=client)

    secret = cache.get_secret_string(AWS_SECRET_NAME)
    secret_json = json.loads(secret)

    SQL_USER = secret_json["username"]
    SQL_PASSWORD = secret_json["password"]

    safe_print("Database credentials loaded.")


# ============================================================
# DATABASE CONNECTION
# ============================================================

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


# ============================================================
# PARSE SOLD DATE
# ============================================================

def parse_sold_date(value):
    if not value:
        return None

    value = str(value).strip()

    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ============================================================
# LOAD NEWEST DATABASE RECORD
# ============================================================

def load_latest_record_from_db():
    safe_print("Loading newest known ACE sale from database...")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1
                id,
                title,
                sold_date,
                price,
                best_offer_accepted,
                url,
                listing_id
            FROM dbo.ace_ebay_sales
            ORDER BY
                CASE
                    WHEN TRY_CONVERT(date, sold_date) IS NOT NULL THEN
                        TRY_CONVERT(date, sold_date)

                    WHEN TRY_CONVERT(date, REPLACE(sold_date, 'Sold ', '')) IS NOT NULL THEN
                        TRY_CONVERT(date, REPLACE(sold_date, 'Sold ', ''))

                    WHEN TRY_CONVERT(date, REPLACE(sold_date, 'Ended ', '')) IS NOT NULL THEN
                        TRY_CONVERT(date, REPLACE(sold_date, 'Ended ', ''))

                    ELSE NULL
                END DESC,
                id DESC
            """
        )


        row = cursor.fetchone()
        if not row:
            safe_print("No existing ACE sales found.")
            return None

        record = {
            "id": row[0],
            "title": row[1].strip() if row[1] else "",
            "sold_date": str(row[2]) if row[2] else "",
            "price": row[3].strip() if row[3] else "",
            "best_offer_accepted": row[4].strip() if row[4] else "",
            "url": row[5].strip() if row[5] else "",
            "listing_id": str(row[6]).strip() if row[6] else ""
        }

        safe_print("Newest known database record:")
        safe_print(record)

        return record

    finally:
        conn.close()


# ============================================================
# CALCULATE API DATE WINDOW
# ============================================================

def calculate_days_to_scrape(last_sold_date):
    today = date.today()

    if not last_sold_date:
        safe_print(f"No usable previous sale date. Using default {DEFAULT_DAYS_TO_SCRAPE} days.")
        return DEFAULT_DAYS_TO_SCRAPE

    days_since_last_sale = (today - last_sold_date).days
    days_to_scrape = max(2, days_since_last_sale + SAFETY_BUFFER_DAYS + 1)
    days_to_scrape = min(days_to_scrape, 365)

    safe_print(f"Latest DB sale date: {last_sold_date}")
    safe_print(f"Today: {today}")
    safe_print(f"Days since latest sale: {days_since_last_sale}")
    safe_print(f"Safety buffer: {SAFETY_BUFFER_DAYS} day")
    safe_print(f"SoldComps daysToScrape: {days_to_scrape}")

    return days_to_scrape


# ============================================================
# CREATE API RUN
# ============================================================

def create_api_run(known_record, days_to_scrape):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dbo.ace_ebay_api_runs
            (status, search_query, ebay_site, days_to_scrape,
             last_known_listing_id, last_known_sold_date)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            "Running",
            SEARCH_QUERY,
            EBAY_SITE,
            days_to_scrape,
            known_record["listing_id"] if known_record else None,
            known_record["sold_date"] if known_record else None
        )

        run_id = cursor.fetchone()[0]
        conn.commit()

        safe_print(f"Created API run #{run_id}")
        return run_id

    finally:
        conn.close()


# ============================================================
# UPDATE API RUN
# ============================================================

def update_api_run(
    run_id,
    status=None,
    pages_requested=None,
    api_requests=None,
    listings_returned=None,
    new_listings_found=None,
    listings_inserted=None,
    duplicates_skipped=None,
    last_known_record_found=None,
    error_message=None,
    completed=False
):

    fields = []
    values = []

    if status is not None:
        fields.append("status = ?")
        values.append(status)

    if pages_requested is not None:
        fields.append("pages_requested = ?")
        values.append(pages_requested)

    if api_requests is not None:
        fields.append("api_requests = ?")
        values.append(api_requests)

    if listings_returned is not None:
        fields.append("listings_returned = ?")
        values.append(listings_returned)

    if new_listings_found is not None:
        fields.append("new_listings_found = ?")
        values.append(new_listings_found)

    if listings_inserted is not None:
        fields.append("listings_inserted = ?")
        values.append(listings_inserted)

    if duplicates_skipped is not None:
        fields.append("duplicates_skipped = ?")
        values.append(duplicates_skipped)

    if last_known_record_found is not None:
        fields.append("last_known_record_found = ?")
        values.append(last_known_record_found)

    if error_message is not None:
        fields.append("error_message = ?")
        values.append(error_message)

    if completed:
        fields.append("completed_at = SYSUTCDATETIME()")
        fields.append(
            """
            duration_seconds =
                DATEDIFF_BIG(MILLISECOND, started_at, SYSUTCDATETIME()) / 1000.0
            """
        )

    if not fields:
        return

    values.append(run_id)

    sql = f"""
        UPDATE dbo.ace_ebay_api_runs
        SET {", ".join(fields)}
        WHERE id = ?
    """

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, *values)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# NORMALISE PRICE
# ============================================================

def normalise_price(value):
    if value is None:
        return ""

    value = str(value).strip()
    value = value.replace("£", "").replace("$", "").replace("€", "").replace(",", "").strip()

    try:
        return f"{float(value):.2f}"
    except Exception:
        return value.lower()


# ============================================================
# CHECK WHETHER LISTING IS LAST KNOWN RECORD
# ============================================================

def rows_match(scraped_row, known_record):
    if not known_record:
        return False

    scraped_listing_id = scraped_row.get("listing_id", "").strip()
    known_listing_id = known_record.get("listing_id", "").strip()

    if scraped_listing_id and known_listing_id and scraped_listing_id == known_listing_id:
        return True

    title_match = scraped_row.get("title", "").strip().lower() == known_record.get("title", "").strip().lower()
    price_match = normalise_price(scraped_row.get("price", "")) == normalise_price(known_record.get("price", ""))

    scraped_date = parse_sold_date(scraped_row.get("sold_date", ""))
    known_date = parse_sold_date(known_record.get("sold_date", ""))

    date_match = scraped_date is not None and known_date is not None and scraped_date == known_date

    return title_match and price_match and date_match


# ============================================================
# CALL SOLDCOMPS
# ============================================================

def get_sold_listings(page_number, days_to_scrape):
    if not SOLDCOMPS_API_KEY:
        raise RuntimeError("SOLDCOMPS_API_KEY environment variable has not been configured.")

    params = {
        "keyword": SEARCH_QUERY,
        "page": page_number,
        "count": COUNT_PER_PAGE,
        "daysToScrape": days_to_scrape,
        "ebaySite": EBAY_SITE,
        "sortOrder": "endedRecently"
    }

    headers = {
        "Authorization": f"Bearer {SOLDCOMPS_API_KEY}",
        "Accept": "application/json"
    }

    safe_print(f"Calling SoldComps page {page_number}...")

    response = requests.get(SOLDCOMPS_API_URL, params=params, headers=headers, timeout=60)

    safe_print(f"SoldComps HTTP status: {response.status_code}")

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "10")
        try:
            wait_seconds = int(retry_after)
        except Exception:
            wait_seconds = 10

        safe_print(f"Rate limited. Waiting {wait_seconds} seconds...")
        time.sleep(wait_seconds)
        return get_sold_listings(page_number, days_to_scrape)

    if response.status_code == 401:
        raise RuntimeError("SoldComps API key is invalid.")

    if response.status_code == 403:
        raise RuntimeError("SoldComps API quota has been exhausted.")

    if response.status_code != 200:
        raise RuntimeError(f"SoldComps API error {response.status_code}: {response.text}")

    return response.json()


# ============================================================
# CONVERT SOLDCOMPS LISTING
# ============================================================

def convert_listing(item):
    sold_price = item.get("soldPrice")
    sold_currency = item.get("soldCurrency")

    if sold_price:
        if sold_currency == "GBP":
            price = f"£{sold_price}"
        else:
            price = f"{sold_price} {sold_currency or ''}".strip()
    else:
        price = ""

    return {
        "title": (item.get("title") or "").strip(),
        "sold_date": (item.get("endedAt") or "").strip(),
        "price": price,
        "best_offer_accepted": "Yes" if item.get("bestOfferAccepted") is True else "No",
        "url": (item.get("url") or "").strip(),
        "listing_id": str(item.get("itemId") or "").strip(),

        "thumbnail_url": item.get("thumbnailUrl"),
        "full_res_thumbnail_url": item.get("fullResThumbnailUrl"),
        "epid": item.get("epid"),
        "condition": item.get("condition"),
        "condition_id": item.get("conditionId"),
        "seller_type": item.get("sellerType"),
        "buying_format": item.get("buyingFormat"),
        "bid_count": item.get("bidCount"),
        "category_id": str(item.get("categoryId")) if item.get("categoryId") is not None else None,
        "listing_type": item.get("listingType"),

        "ended_at": item.get("endedAt"),
        "sold_price": float(sold_price) if sold_price else None,
        "sold_currency": sold_currency,

        "shipping_price": float(item.get("shippingPrice")) if item.get("shippingPrice") else None,
        "shipping_currency": item.get("shippingCurrency"),
        "shipping_type": item.get("shippingType"),
        "total_price": float(item.get("totalPrice")) if item.get("totalPrice") else None,

        "seller_username": item.get("sellerUsername"),
        "seller_positive_percent": float(item.get("sellerPositivePercent")) if item.get("sellerPositivePercent") is not None else None,
        "seller_feedback_score": item.get("sellerFeedbackScore"),
        "item_location": item.get("itemLocation"),
        "scraped_at": item.get("scrapedAt")
    }


# ============================================================
# INSERT LISTINGS
# ============================================================

def insert_rows_to_db(rows):
    if not rows:
        safe_print("No new rows to insert.")
        return 0, 0

    conn = get_connection()
    inserted = 0
    duplicates = 0

    try:
        cursor = conn.cursor()

        for r in rows:
            try:
                cursor.execute(
                    """
                    INSERT INTO dbo.ace_ebay_sales
                    (
                        title, sold_date, price, best_offer_accepted,
                        database_created_at, database_updated_at,
                        url, listing_id,
                        thumbnail_url, full_res_thumbnail_url, epid,
                        condition, condition_id, seller_type, buying_format,
                        bid_count, category_id, listing_type,
                        ended_at, sold_price, sold_currency,
                        shipping_price, shipping_currency, shipping_type,
                        total_price, seller_username, seller_positive_percent,
                        seller_feedback_score, item_location, scraped_at
                    )
                    VALUES
                    (
                        ?, ?, ?, ?,
                        SYSUTCDATETIME(), SYSUTCDATETIME(),
                        ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    r["title"], r["sold_date"], r["price"], r["best_offer_accepted"],
                    r["url"], r["listing_id"],
                    r["thumbnail_url"], r["full_res_thumbnail_url"], r["epid"],
                    r["condition"], r["condition_id"], r["seller_type"], r["buying_format"],
                    r["bid_count"], r["category_id"], r["listing_type"],
                    r["ended_at"], r["sold_price"], r["sold_currency"],
                    r["shipping_price"], r["shipping_currency"], r["shipping_type"],
                    r["total_price"], r["seller_username"], r["seller_positive_percent"],
                    r["seller_feedback_score"], r["item_location"], r["scraped_at"]
                )
                inserted += 1

            except pyodbc.IntegrityError:
                duplicates += 1

        conn.commit()

    finally:
        conn.close()

    return inserted, duplicates


# ============================================================
# SCRAPE ALL SOLDCOMPS PAGES
# ============================================================

def scrape_all_pages(run_id, known_record, days_to_scrape):
    new_listings_found = 0
    total_inserted = 0
    total_duplicates = 0

    page_number = 1
    pages_requested = 0
    api_requests = 0
    listings_returned = 0

    while True:
        safe_print("\n========================================")
        safe_print(f"SoldComps page {page_number}")
        safe_print("========================================")

        pages_requested += 1
        api_requests += 1

        update_api_run(run_id, pages_requested=pages_requested, api_requests=api_requests)

        data = get_sold_listings(page_number, days_to_scrape)

        if isinstance(data, list):
            items = data
            has_next_page = len(items) == COUNT_PER_PAGE
        else:
            items = data.get("items", [])
            has_next_page = data.get("hasNextPage", False)

        listings_returned += len(items)
        update_api_run(run_id, listings_returned=listings_returned)

        safe_print(f"Received {len(items)} listings.")

        if not items:
            safe_print("No listings returned.")
            break

        stop_reached = False
        page_rows = []

        for item in items:
            row = convert_listing(item)

            if rows_match(row, known_record):
                safe_print("\n*** LAST KNOWN RECORD REACHED ***")
                safe_print("Stopping SoldComps pagination.")
                stop_reached = True
                break

            page_rows.append(row)

        # Insert page rows immediately
        inserted, duplicates = insert_rows_to_db(page_rows)

        safe_print(f"Inserted {inserted} rows, {duplicates} duplicates on page {page_number}")

        new_listings_found += inserted
        total_inserted += inserted
        total_duplicates += duplicates

        update_api_run(
            run_id,
            new_listings_found=new_listings_found,
            listings_inserted=total_inserted,
            duplicates_skipped=total_duplicates
        )

        if stop_reached:
            update_api_run(run_id, last_known_record_found=True)
            break

        if not has_next_page:
            safe_print("No more SoldComps pages.")
            break

        page_number += 1
        time.sleep(1)

    return (
        new_listings_found,
        pages_requested,
        api_requests,
        listings_returned,
        total_inserted,
        total_duplicates
    )


# ============================================================
# MAIN
# ============================================================

def run():
    safe_print("\n========================================")
    safe_print("ACE EBAY SALES - SOLDCOMPS")
    safe_print("========================================\n")

    if not SOLDCOMPS_API_KEY:
        raise RuntimeError(
            "SOLDCOMPS_API_KEY environment variable has not been configured."
        )

    # --------------------------------------------------------
    # DATABASE CREDENTIALS
    # --------------------------------------------------------

    get_secret()

    # --------------------------------------------------------
    # LOAD LAST KNOWN SALE
    # --------------------------------------------------------

    known_record = load_latest_record_from_db()

    # --------------------------------------------------------
    # CALCULATE DATE WINDOW
    # --------------------------------------------------------

    if known_record:
        last_sold_date = parse_sold_date(known_record["sold_date"])
    else:
        last_sold_date = None

    days_to_scrape = calculate_days_to_scrape(last_sold_date)

    # --------------------------------------------------------
    # CREATE RUN RECORD
    # --------------------------------------------------------

    run_id = create_api_run(known_record, days_to_scrape)

    try:
        # ----------------------------------------------------
        # CALL SOLDCOMPS
        # ----------------------------------------------------

        (
            new_listings_found,
            pages_requested,
            api_requests,
            listings_returned,
            total_inserted,
            total_duplicates
        ) = scrape_all_pages(run_id, known_record, days_to_scrape)

        # ----------------------------------------------------
        # MARK RUN COMPLETE
        # ----------------------------------------------------

        update_api_run(
            run_id,
            status="Completed",
            pages_requested=pages_requested,
            api_requests=api_requests,
            listings_returned=listings_returned,
            new_listings_found=new_listings_found,
            listings_inserted=total_inserted,
            duplicates_skipped=total_duplicates,
            completed=True
        )

        safe_print("\n========================================")
        safe_print("Run completed successfully.")
        safe_print(
            f"Pages requested: {pages_requested}, "
            f"API requests: {api_requests}, "
            f"Listings returned: {listings_returned}, "
            f"New listings found: {new_listings_found}, "
            f"Inserted: {total_inserted}, "
            f"Duplicates: {total_duplicates}"
        )
        safe_print("========================================\n")

    except Exception as exc:
        safe_print("\n========================================")
        safe_print("Run failed with an error.")
        safe_print(str(exc))
        safe_print("========================================\n")

        update_api_run(
            run_id,
            status="Failed",
            error_message=str(exc),
            completed=True
        )
        raise


if __name__ == "__main__":
    run()
