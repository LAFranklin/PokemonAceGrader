import time
from playwright.sync_api import sync_playwright
import pyodbc
from datetime import datetime, timezone

SEARCH_QUERY = "Ace Graded"

SQL_SERVER = "database-1.cdgee08us4is.eu-west-2.rds.amazonaws.com,1433"
SQL_DATABASE = "Pokemon"
SQL_USER = "admin"
SQL_PASSWORD = "dzz<[kqP~jnBbGI)9e:2xr1e7|rI"  # change this


# -----------------------------
# DB CONNECTION
# -----------------------------

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
# LOAD NEWEST KNOWN RECORD FROM DB
# -----------------------------

def load_latest_record_from_db():
    print("Loading newest known ACE sale from database…")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 1
                title,
                sold_date,
                price,
                best_offer_accepted
            FROM ace_ebay_sales
            ORDER BY database_created_at DESC
            """
        )
        row = cursor.fetchone()
        if not row:
            print("No existing ACE sales in DB — no stopping condition.")
            return None

        record = {
            "title": row[0].strip() if row[0] else "",
            "sold_date": row[1].strip() if row[1] else "",
            "price": row[2].strip() if row[2] else "",
            "best_offer_accepted": row[3].strip() if row[3] else "",
        }

        print("Newest known record in DB:")
        print(record)

        if not (record["title"] and record["price"] and record["sold_date"]):
            print("Record missing required fields — stopping logic disabled.")
            return None

        return record
    finally:
        conn.close()


# -----------------------------
# FILTER FUNCTIONS
# -----------------------------

def apply_sold_filter(page):
    print("Applying SOLD filter…")
    try:
        page.get_by_label("Sold items").check()
    except:
        page.get_by_text("Sold items", exact=True).click()
    time.sleep(3)


def apply_completed_filter(page):
    print("Applying COMPLETED filter…")
    try:
        page.get_by_label("Completed items").check()
    except:
        page.get_by_text("Completed items", exact=True).click()
    time.sleep(3)


def apply_graded_yes(page):
    print("Applying GRADED = YES filter…")
    try:
        page.get_by_text("Graded").click()
        time.sleep(1)
        page.get_by_text("Yes").click()
    except:
        print("Could not click graded filter.")
    time.sleep(3)


def apply_ace_grading(page):
    print("Applying PROFESSIONAL GRADER = ACE GRADING filter…")
    try:
        page.get_by_text("Professional Grader").click()
        time.sleep(1)
        page.get_by_text("Ace Grading (Ace)").click()
    except:
        print("Could not click professional grader filter.")
    time.sleep(3)


# -----------------------------
# SCROLLING
# -----------------------------

def scroll_until_count(page, target_count=200, delay=1.2):
    print(f"Scrolling until at least {target_count} items are loaded…")

    last_count = 0
    same_count_repeats = 0

    while True:
        cards = page.locator(".srp-results li.s-card")
        count = cards.count()

        print(f"Loaded {count} items…")

        if count >= target_count:
            print("Target reached.")
            break

        if count == last_count:
            same_count_repeats += 1
            if same_count_repeats >= 5:
                print("No more items loading — reached end.")
                break
        else:
            same_count_repeats = 0

        last_count = count

        page.mouse.wheel(0, 3000)
        time.sleep(delay)

        page.mouse.wheel(0, 5000)
        time.sleep(delay)

        page.mouse.wheel(0, 8000)
        time.sleep(delay)

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(delay)

    print("Scrolling complete.")


# -----------------------------
# MATCHING LOGIC
# -----------------------------

def rows_match(scraped_row, known_record):
    if known_record is None:
        return False

    return (
        scraped_row.get("title", "").strip() == known_record["title"]
        and scraped_row.get("price", "").strip() == known_record["price"]
        and scraped_row.get("sold_date", "").strip() == known_record["sold_date"]
    )


# -----------------------------
# EXTRACTION
# -----------------------------

def extract_cards(page, known_record=None):
    print("Extracting card data from DOM…")

    cards = page.locator(".srp-results li.s-card")
    count = cards.count()
    print(f"Found {count} cards.")

    rows = []
    stop_reached = False

    for i in range(count):
        card = cards.nth(i)

        try:
            sold_date = card.locator(".s-card__caption .default").inner_text().strip()
        except:
            sold_date = ""

        try:
            title = card.locator(".s-card__title .primary").inner_text().strip()
        except:
            title = ""

        try:
            price_el = card.locator(".s-card__price")
            price = price_el.inner_text().strip()
            price_classes = price_el.get_attribute("class") or ""
            best_offer_accepted = "Yes" if "strikethrough" in price_classes else "No"
        except:
            price = ""
            best_offer_accepted = "No"

        row = {
            "title": title,
            "sold_date": sold_date,
            "price": price,
            "best_offer_accepted": best_offer_accepted,
        }

        if rows_match(row, known_record):
            print("\n*** Newest known record reached — stopping scraper. ***")
            stop_reached = True
            break

        rows.append(row)

    return rows, stop_reached


# -----------------------------
# DB INSERT
# -----------------------------

def insert_rows_to_db(rows):
    if not rows:
        print("No new rows to insert into DB.")
        return

    print(f"Inserting {len(rows)} new rows into ace_ebay_sales…")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        for r in rows:
            cursor.execute(
                """
                INSERT INTO ace_ebay_sales (
                    title,
                    sold_date,
                    price,
                    best_offer_accepted,
                    database_created_at,
                    database_updated_at
                )
                VALUES (?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                """,
                r["title"],
                r["sold_date"],
                r["price"],
                r["best_offer_accepted"],
            )
        conn.commit()
    finally:
        conn.close()

    print("Insert complete.")


# -----------------------------
# PAGE LOOP
# -----------------------------

def scrape_all_pages(page, known_record):
    all_rows = []
    buffer = []  # rows waiting to be written
    page_number = 1

    while True:
        print(f"\n=== Extracting Page {page_number} ===")

        scroll_until_count(page, target_count=60)

        rows, stop_reached = extract_cards(page, known_record=known_record)

        # Add to buffer
        buffer.extend(rows)
        all_rows.extend(rows)

        print(f"Total collected so far: {len(all_rows)}")
        print(f"Buffer size: {len(buffer)}")

        # ⭐ CHECKPOINT EVERY 60 ROWS
        if len(buffer) >= 60:
            print("\n*** CHECKPOINT: Writing 60 rows to DB ***")
            insert_rows_to_db(buffer)
            buffer = []  # clear buffer

        if stop_reached:
            print("Stopping because newest known record was found.")
            break

        next_button = page.locator("a.pagination__next")
        if next_button.count() == 0:
            print("No more pages available.")
            break

        print("Going to next page…")
        next_button.first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        page_number += 1

    # ⭐ FINAL FLUSH (write remaining rows)
    if buffer:
        print(f"\n*** FINAL CHECKPOINT: Writing {len(buffer)} rows to DB ***")
        insert_rows_to_db(buffer)

    return all_rows



# -----------------------------
# EBAY OPEN + SEARCH
# -----------------------------

def open_ebay_and_search(p, query):
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    print("Opening eBay UK…")
    page.goto("https://www.ebay.co.uk/")
    page.wait_for_load_state("domcontentloaded")

    try:
        page.get_by_role("button", name="Accept all").click(timeout=3000)
    except:
        pass

    print("Searching…")
    page.fill("input[aria-label='Search for anything']", query)
    page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    return browser, page


def close_browser(browser):
    time.sleep(5)
    browser.close()


# -----------------------------
# MAIN RUN
# -----------------------------

def run():
    known_record = load_latest_record_from_db()

    with sync_playwright() as p:
        browser, page = open_ebay_and_search(p, SEARCH_QUERY)

        apply_sold_filter(page)
        apply_completed_filter(page)
        apply_graded_yes(page)
        apply_ace_grading(page)

        new_rows = scrape_all_pages(page, known_record)

        close_browser(browser)

    insert_rows_to_db(new_rows)


if __name__ == "__main__":
    run()
