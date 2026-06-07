import time
from playwright.sync_api import sync_playwright

SEARCH_QUERY = "Ace Graded"


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


def scroll_until_count(page, target_count=200, delay=1.2):
    print(f"Scrolling until at least {target_count} items are loaded…")

    last_count = 0
    same_count_repeats = 0

    while True:
        cards = page.locator(".srp-results li.s-card")
        count = cards.count()

        print(f"Loaded {count} items…")

        # Stop when target reached
        if count >= target_count:
            print("Target reached.")
            break

        # If no new items after several scrolls → stop
        if count == last_count:
            same_count_repeats += 1
            if same_count_repeats >= 5:
                print("No more items loading — reached end.")
                break
        else:
            same_count_repeats = 0

        last_count = count

        # Deep scrolling pattern
        page.mouse.wheel(0, 3000)
        time.sleep(delay)

        page.mouse.wheel(0, 5000)
        time.sleep(delay)

        page.mouse.wheel(0, 8000)
        time.sleep(delay)

        # Safety: scroll to bottom explicitly
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(delay)

    print("Scrolling complete.")

import json
import csv

def extract_cards(page):
    print("Extracting card data from DOM…")

    cards = page.locator(".srp-results li.s-card")
    count = cards.count()
    print(f"Found {count} cards.")

    rows = []

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

        rows.append({
            "title": title,
            "sold_date": sold_date,
            "price": price,
            "best_offer_accepted": best_offer_accepted
        })

    return rows

def scrape_all_pages(page, filename):
        all_rows = []
        page_number = 1

        while True:
                print(f"\n=== Extracting Page {page_number} ===")

                scroll_until_count(page, target_count=60)

                rows = extract_cards(page)
                all_rows.extend(rows)

                # Append this page's rows immediately
                append_rows_to_csv(rows, filename)

                print(f"Total collected so far: {len(all_rows)}")

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

def save_results_to_csv(all_rows):
        # Build timestamped filename: YYYYMMDD_HHMM.csv
        timestamp = time.strftime("%Y%m%d_%H%M")
        filename = f"ace_sold_results_{timestamp}.csv"

        print(f"\nSaving {len(all_rows)} items to {filename}…")

        with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                        f,
                        fieldnames=["title", "sold_date", "price", "best_offer_accepted"]
                )
                writer.writeheader()
                writer.writerows(all_rows)

        print("CSV saved successfully.")
        return filename


def open_ebay_and_search(p, query):
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("Opening eBay UK…")
        page.goto("https://www.ebay.co.uk/")
        page.wait_for_load_state("domcontentloaded")

        # Accept cookies if present
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

def append_rows_to_csv(rows, filename):
        file_exists = False
        try:
                with open(filename, "r", encoding="utf-8") as f:
                        file_exists = True
        except FileNotFoundError:
                pass

        with open(filename, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                        f,
                        fieldnames=["title", "sold_date", "price", "best_offer_accepted"]
                )

                # Write header only once
                if not file_exists:
                        writer.writeheader()

                writer.writerows(rows)

        print(f"Appended {len(rows)} rows to {filename}")

def run():
        with sync_playwright() as p:
                browser, page = open_ebay_and_search(p, SEARCH_QUERY)

                apply_sold_filter(page)
                apply_completed_filter(page)
                apply_graded_yes(page)
                apply_ace_grading(page)

                timestamp = time.strftime("%Y%m%d_%H%M")
                filename = f"ace_sold_results_{timestamp}_{SEARCH_QUERY}.csv"

                all_rows = scrape_all_pages(page, filename)

                close_browser(browser)


if __name__ == "__main__":
    run()
