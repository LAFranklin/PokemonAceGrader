# Pokemon Card Pricing Database Builder

Build a complete Pokémon card database from TCGdex and enrich it with real-world ACE Grading sold prices scraped from eBay.

## Overview

This repository creates a consolidated Pokémon card dataset containing:

- Full card metadata from TCGdex
- CardMarket pricing
- TCGPlayer pricing
- ACE Grading sold listings from eBay
- Estimated ACE 8, ACE 9 and ACE 10 values

The pipeline downloads Pokémon card data, collects recent ACE Grading sales, maps those sales to specific cards, and calculates average graded values.

---

## Data Pipeline

### 1. Download Pokémon Card Data

```bash
python tcgdex_downloader_full.py
```

Downloads all cards from the TCGdex API and creates:

```text
pokemon_cards_full.csv
```

Includes:

- Card details
- Set information
- Images
- Variants
- CardMarket pricing
- TCGPlayer pricing

The downloader supports:

- Pagination
- Checkpoint recovery
- Resume after interruption
- Incremental writes to disk

---

### 2. Download Latest ACE Grading Sales

```bash
python ace_playwright_scraper_delta.py
```

Requirements:

```text
ace_sold_results.csv
```

This scraper:

- Searches eBay UK for ACE graded Pokémon cards
- Applies Sold + Completed filters
- Filters to ACE Grading listings only
- Stops when it reaches the newest previously known sale
- Prepends new sales to the master dataset
- Removes duplicate sales
- Archives run history

Output:

```text
ace_sold_results.csv
```

Archive files are stored in:

```text
archive/
```

---

### 3. Match ACE Sales to Pokémon Cards

```bash
python match_pokemon_to_price.py
```

Creates:

```text
pokemon_ace_mapped_prices.csv
```

The matching process:

- Loads Pokémon card data
- Loads all TCGdex sets
- Parses eBay titles
- Extracts collector numbers
- Extracts grades
- Fuzzy matches set names
- Maps sales to specific card IDs

Filters out:

- PSA listings
- Bundles and lots
- Non-ACE graded cards
- Best offer accepted sales

---

### 4. Calculate ACE Value Estimates

```bash
python agreegate_ace_pricing.py
```

Creates:

```text
pokemon_cards_full_updated.csv
```

This step:

- Aggregates mapped ACE sales
- Calculates average values by grade
- Updates each card with:

| Field | Description |
|---------|---------|
| ace8_estimate | Average ACE 8 sale price |
| ace9_estimate | Average ACE 9 sale price |
| ace10_estimate | Average ACE 10 sale price |

---

## Complete Workflow

Run the scripts in the following order:

```bash
python tcgdex_downloader_full.py
python ace_playwright_scraper_delta.py
python match_pokemon_to_price.py
python agreegate_ace_pricing.py
```

Final output:

```text
pokemon_cards_full_updated.csv
```

---

## Dependencies

Install required packages:

```bash
pip install requests playwright
```

Install Playwright browsers:

```bash
playwright install
```

---

## Project Structure

```text
.
├── tcgdex_downloader_full.py
├── ace_playwright_scraper_full.py
├── ace_playwright_scraper_delta.py
├── match_pokemon_to_price.py
├── agreegate_ace_pricing.py
├── pokemon_cards_full.csv
├── pokemon_ace_mapped_prices.csv
├── pokemon_cards_full_updated.csv
├── ace_sold_results.csv
├── archive/
└── README.md
```

---

## Notes

- The delta scraper is intended for day-to-day updates.
- The full scraper can be used to rebuild the entire ACE sales dataset.
- Set matching uses fuzzy matching and may occasionally require tuning if eBay listing formats change.
- TCGdex remains the source of truth for Pokémon card metadata.
