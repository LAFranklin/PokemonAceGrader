# PokémonAceGrader

This repository contains scripts for collecting ACE-graded Pokémon sale data from eBay, syncing Pokémon card metadata from TCGdex, and updating SQL Server tables used for pricing/matching workflows.

## Current scripts

### `ace_playwright_scraper_delta.py`
Incremental ACE eBay scraper (Playwright + SQL Server).

- Opens eBay UK and searches for `Ace Graded`
- Applies filters: Sold items, Completed items, Graded = Yes, Professional Grader = Ace Grading
- Loads the newest known row from `ace_ebay_sales` and stops when that row is seen again
- Scrapes title, sold_date, price, best_offer_accepted, url, listing_id
- Inserts new rows into `ace_ebay_sales` in checkpoints (every 60 rows + final flush)
- Pulls DB credentials from AWS Secrets Manager

### `tcgdex_downloader_full.py`
Full TCGdex ingestion script for card metadata + pricing snapshots.

- Paginates through `https://api.tcgdex.net/v2/en/cards`
- Fetches full card detail per card ID
- Upserts metadata into `pokemon_cards` (SQL MERGE)
- Inserts pricing snapshots into:
  - `cardmarket_pricing`
  - `tcgplayer_pricing`

### `match_pokemon_to_price.py`
Database refresh + stored-procedure runner (despite the filename, it does not do Python-side fuzzy matching).

- Downloads set list from `https://api.tcgdex.net/v2/en/sets`
- Rebuilds `tcgdex_sets` (truncate + insert)
- Executes stored procedure `usp_UpdateAceEbaySalesGrading`
- Pulls DB credentials from AWS Secrets Manager

### `run_pricing_pipeline.py`
Simple sequential runner.

It currently attempts to run these entries in order:
1. `ace_playwright_scraper_delta.py`
2. `match_pokemon_to_price.py`
3. `update_latest_sets` (no `.py` extension in the script)

Current repository status for step 3:
- No `update_latest_sets` file exists in this repository, so this third step will fail unless that executable/script is added or the pipeline list is corrected.

## Legacy/alternate scripts

### `ace_playwright_scraper_full.py`
Older full eBay scrape variant that writes CSV output.

### `ebay_coldcomps_scrapper.py`
Another CSV-based eBay scrape script.

## Runtime dependencies

Main Python dependencies used by these scripts:
- `playwright`
- `pyodbc`
- `requests`
- `botocore`
- `aws-secretsmanager-caching`

Also required:
- ODBC Driver 18 for SQL Server
- Network access to SQL Server and AWS Secrets Manager
- Playwright browser install (`playwright install`)

## Notes

- Most current pipeline behavior is database-first (not CSV), except the legacy scripts listed above.
- SQL credentials are intentionally not hardcoded and are expected from Secrets Manager in scripts that use AWS.
