import time
import csv
import os
from playwright.sync_api import sync_playwright

SEARCH_QUERY = "Ace Graded"
KNOWN_CSV = "ace_sold_results.csv"   # newest known sales
ARCHIVE_FOLDER = "archive"           # folder to store run snapshots


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
# LOAD FIRST (NEWEST) RECORD
# -----------------------------

def load_first_record(csv_path):
    print(f"Loading first (newest) record from {csv_path}…")

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first_row = next(reader, None)

        if first_row is None:
            print("CSV is empty — no stopping condition.")
            return None

        record = {
            "title": first_row.get("title", "").strip(),
            "price": first_row.get("price", "").strip(),
            "sold_date": first_row.get("sold_date", "").strip(),
        }

        print("Newest known record:")
        print(record)

        if not (record["title"] and record["price"] and record["sold_date"]):
            print("Record missing required fields — stopping logic disabled.")
            return None

        return record

    except FileNotFoundError:
        print(f"{csv_path} not found — no stopping condition.")
        return None


# -----------------------------
# MATCHING LOGIC
# -----------------------------

def rows_match(scraped_row, known_record):
    if known_record is None:
        return False

    return (
        scraped_row.get("title", "").strip() == known_record["title"] and
        scraped_row.get("price", "").strip() == known_record["price"] and
        scraped_row.get("sold_date", "").strip() == known_record["sold_date"]
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
            "best_offer_accepted": best_offer_accepted
        }

        if rows_match(row, known_record):
            print("\n*** Newest known record reached — stopping scraper. ***")
            stop_reached = True
            break

        rows.append(row)

    return rows, stop_reached


# -----------------------------
# CSV APPEND
# -----------------------------

def append_rows_to_csv(rows, filename):
    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["title", "sold_date", "price", "best_offer_accepted"]
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(rows)

    print(f"Appended {len(rows)} rows to {filename}")


# -----------------------------
# PREPEND NEW ROWS TO ace_sold_results.csv
# -----------------------------

def prepend_to_known_csv(new_rows):
    if not new_rows:
        print("No new rows to prepend.")
        return

    print("Prepending new rows to ace_sold_results.csv…")

    with open(KNOWN_CSV, "r", encoding="utf-8") as f:
        existing = list(csv.DictReader(f))

    fieldnames = ["title", "sold_date", "price", "best_offer_accepted"]

    with open(KNOWN_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # NEW rows first
        writer.writerows(new_rows)

        # Then old rows
        writer.writerows(existing)

    print("ace_sold_results.csv updated with newest rows at the top.")


# -----------------------------
# ARCHIVE SNAPSHOT
# -----------------------------

def archive_file(path):
    os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
    base = os.path.basename(path)
    archive_path = os.path.join(ARCHIVE_FOLDER, base)
    os.rename(path, archive_path)
    print(f"Archived run to {archive_path}")

# -----------------------------
# REMOVE DUPLICATES - incases something sells and moves the data into the next page. 
# -----------------------------

def remove_duplicates_from_known_csv():
    print("\nChecking for duplicates in ace_sold_results.csv…")

    fieldnames = ["title", "sold_date", "price", "best_offer_accepted"]

    try:
        with open(KNOWN_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print("No ace_sold_results.csv found — skipping duplicate removal.")
        return

    seen = set()
    unique_rows = []
    duplicates = []

    for row in rows:
        key = (
            row["title"].strip(),
            row["sold_date"].strip(),
            row["price"].strip(),
            row["best_offer_accepted"].strip()
        )

        if key in seen:
            duplicates.append(row)
        else:
            seen.add(key)
            unique_rows.append(row)

    # Write cleaned file back
    with open(KNOWN_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_rows)

    # Write duplicates to archive
    if duplicates:
        timestamp = time.strftime("%Y%m%d_%H%M")
        dup_filename = f"duplicates_found_{timestamp}.csv"
        dup_path = os.path.join(ARCHIVE_FOLDER, dup_filename)

        os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

        with open(dup_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(duplicates)

        print(f"Removed {len(duplicates)} duplicates.")
        print(f"Duplicates archived at: {dup_path}")
        print("Note: duplicates occur because eBay sells items extremely fast,")
        print("and the scraper may capture the same sale twice if it appears in two runs.")
    else:
        print("No duplicates found.")


# -----------------------------
# PAGE LOOP
# -----------------------------

def scrape_all_pages(page, filename, known_record):
    all_rows = []
    page_number = 1

    while True:
        print(f"\n=== Extracting Page {page_number} ===")

        scroll_until_count(page, target_count=60)

        rows, stop_reached = extract_cards(page, known_record=known_record)
        all_rows.extend(rows)

        append_rows_to_csv(rows, filename)

        print(f"Total collected so far: {len(all_rows)}")

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
    known_record = load_first_record(KNOWN_CSV)

    timestamp = time.strftime("%Y%m%d_%H%M")
    filename = f"ace_sold_results_{timestamp}_{SEARCH_QUERY}.csv"

    with sync_playwright() as p:
        browser, page = open_ebay_and_search(p, SEARCH_QUERY)

        apply_sold_filter(page)
        apply_completed_filter(page)
        apply_graded_yes(page)
        apply_ace_grading(page)

        new_rows = scrape_all_pages(page, filename, known_record)

        close_browser(browser)

    # PREPEND new rows to main CSV
    prepend_to_known_csv(new_rows)

    # ARCHIVE the run file
    archive_file(filename)

    # REMOVE DUPLICATES
    remove_duplicates_from_known_csv()

if __name__ == "__main__":
    run()
