# 📘 Pokémon ACE Pricing Pipeline  
### Automated ACE Pricing + Pokémon Metadata Gathering  
### **Full ETL Pipeline + AWS Architecture Documentation**

---

## 🧱 Overview

This repository contains a fully automated data pipeline for:

- Scraping **ACE‑graded Pokémon card sales** from eBay  
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
| **Purpose** | Runs the **ACE eBay scraper** and **ACE → Pokémon matching pipeline** |

### **Role**
This instance performs:

- Web scraping using Playwright  
- ACE sales extraction  
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

## 1. `ace_playwright_scraper_delta.py`  
### **Purpose:** Scrape ACE‑graded Pokémon card sales from eBay and write them to the database.

### Extracts:
- Title  
- Price  
- Grade (ACE 8/9/10)  
- Sold date  
- Listing URL  
- Raw title for NLP matching  

### Features:
- Delta mode (only new sales)  
- Automatic scrolling + pagination  
- Writes all scraped rows directly into the database  
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
- Writes matched rows into the **ace_mapped_prices** table  

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
1. Scrape ACE sales  
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
