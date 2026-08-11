# 📘 Pokémon ACE Pricing Pipeline  
### Automated ACE Pricing + Pokémon Metadata Gathering  
### **Full ETL Pipeline + AWS Architecture Documentation**

---

## 🔗 Related Projects & Dependencies

This repository is part of a larger ecosystem of projects that work together:

| Project | Role | Links |
|---------|------|-------|
| **PokemonAceGrader** *(this repo)* | Data collection — scrapes eBay ACE sales, matches to Pokémon card metadata, writes to database | [GitHub](https://github.com/LAFranklin/PokemonAceGrader) |
| **Pokemon-card-grading** | Frontend website hosted on Vercel — displays the graded card pricing data collected by this pipeline | [GitHub](https://github.com/LAFranklin/Pokemon-card-grading) · [Live site](https://pokemon-card-grading.vercel.app/) |
| **PokemonCardsAPI** | Backend API repository — provides the frontend's database access layer for pricing and card data | [GitHub](https://github.com/LAFranklin/PokemonCardsAPI) |
| **Vercel** | Hosting platform for the `Pokemon-card-grading` frontend deployment | [Vercel](https://vercel.com/) |
| **sold-comps.com** | External eBay data API — used by `ebay_coldcomps_scrapper.py` to fetch sold eBay listings | [Dashboard](https://sold-comps.com/dashboard/usage) · [API docs](https://api.sold-comps.com) |

### How they fit together

```
sold-comps.com API
       │
       ▼
ebay_coldcomps_scrapper.py  ──►  Database (ace_ebay_sales)
                                      │
tcgdex_downloader_full.py   ──►  Database (pokemon_cards)
                                      │
                              match_pokemon_to_price.py
                                      │
                                      ▼
                              Database (matched sales)
                                      │
                                      ▼
                             PokemonCardsAPI
                                      │
                                      ▼
                    Pokemon-card-grading (frontend on Vercel)
                    https://pokemon-card-grading.vercel.app/
```

- **This repo** (`PokemonAceGrader`) is responsible for all data ingestion and processing.
- **PokemonCardsAPI** is the API layer that reads from the database and serves the frontend.
- The **Pokemon-card-grading** frontend is hosted on **Vercel** and consumes **PokemonCardsAPI** to display prices on the website.
- **sold-comps.com** provides the eBay sold-listing data used as the raw input for ACE sales.

---

## 🧱 Overview

This repository contains a fully automated data pipeline for:

- Scraping **ACE‑graded Pokémon card sales** via the **sold-comps.com API**  
- Matching ACE sales to real Pokémon cards  
- Downloading **Pokémon card metadata** from TCGdex (on a separate instance)  
- Writing all processed data directly into the **database**  
- Running everything automatically on AWS using **EC2 + SSM Automation + EventBridge**

⚠️ **Important:**  
This system **no longer outputs CSV files**.  
All scripts write directly to the **database**, which is the single source of truth.

---

# 🖥️ AWS Architecture

## 1. EC2 Instances

---

## **1.1 ACE Price Gathering Instance**

| Property | Value |
|---------|-------|
| **Name** | Ace Price Gathering |
| **Instance ID** | `i-0bd1c0888cae1d21d` |
| **Purpose** | Calls the **sold-comps.com API** to fetch ACE eBay sales data and runs the **ACE → Pokémon matching pipeline** |

### **Role**
This instance performs:

- Fetches ACE‑graded sold listings via the **sold-comps.com API** (no direct eBay scraping)  
- ACE sales extraction and processing  
- ACE → Pokémon card matching  
- Writes all results directly into the database  

### **Schedule**
Runs every **4 hours** via EventBridge → SSM Automation.

---

## **1.2 Pokémon Detail Gathering Instance**

| Property | Value |
|---------|-------|
| **Name** | Pokemon Detail Gathering |
| **Instance ID** | `i-0a38d52d59f4ec1d1` |
| **Purpose** | Downloads full Pokémon card metadata from TCGdex |

### **Role**
This instance performs:

- Full TCGdex database download  
- Set + card + variant extraction  
- Writes all metadata directly into the database  

### **Schedule**
Runs **daily at 02:00** via EventBridge → SSM Automation.

---

# 🛠️ Automation Architecture

### **Systems Manager Automation**
Each EC2 instance is controlled by its own SSM Automation document:

1. **Start the instance**
2. **Run the Python pipeline script**
3. **Stop the instance**

This ensures:

- Zero idle cost  
- Fully automated execution  
- No manual RDP or SSH required  

### **EventBridge Scheduling**
EventBridge triggers the SSM Automation:

| Pipeline | Schedule |
|----------|----------|
| **ACE Price Gathering** | Every **4 hours** |
| **Pokémon Detail Gathering** | **Daily at 02:00** |

---

# 🧬 Pipeline Components

The pipeline consists of **three main scripts**, but they run on **two separate EC2 instances**.

---

## 1. `ebay_coldcomps_scrapper.py`  
### **Purpose:** Fetch ACE‑graded Pokémon card sales via the sold-comps.com API and write them to the database.

### Extracts:
- Title  
- Price  
- Grade (ACE 8/9/10)  
- Sold date  

### Features:
- Calls the **sold-comps.com REST API** — no direct eBay browser scraping  
- Delta mode (only new sales since last run)  
- Writes all fetched rows directly into the database  
- No CSV output  

---

## 2. `match_pokemon_to_price.py`  
### **Purpose:** Match ACE sales to real Pokémon cards and store the results in the database.

### Inputs:
- ACE sales table (from database)
- Pokémon card metadata table (from database)

### What it does:
- Cleans ACE titles  
- Extracts set names + card numbers  
- Fuzzy matches to TCGdex metadata  
- Writes matched rows into the **ace_ebay_sales** table  

### Output:
- **Database rows only**  
- No CSV files  

---

## 3. `tcgdex_downloader_full.py`  
### **Purpose:** Download and maintain a full Pokémon card database.  
### **Runs on a separate EC2 instance.**

### What it does:
- Calls TCGdex API  
- Downloads all sets + cards + variants  
- Normalises the data  
- Writes everything into the **pokemon_cards** table  

### Output:
- **Database rows only**  
- No CSV files  

---

## 4. `run_pipeline.py`  
### **Purpose:** Orchestrates the ACE pipeline only.

### ⚠️ Important  
`run_pipeline.py` **does NOT**:

- Update TCGdex  

Those responsibilities are handled elsewhere.

### What it does:
1. Fetch ACE sales via sold-comps.com API  
2. Match ACE sales to Pokémon cards  
3. Write results to the database  

### Output:
- All results written to the database  
- No CSVs generated  

---


# 🧪 Running the Pipeline

### **Run ACE pipeline**
```bash
python run_pipeline.py
