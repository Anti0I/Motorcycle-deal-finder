# Motorcycle Deal Finder

> AI-powered bot that finds underpriced motorcycle listings and sends the best deals to Discord.

---

## Overview

Automated system that monitors **Otomoto** listings, extracts key data (price, year, details), uses AI to evaluate profitability, and sends only valuable deals to Discord.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=microsoft&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Discord](https://img.shields.io/badge/Discord_Webhook-5865F2?style=for-the-badge&logo=discord&logoColor=white)

---

## AI Evaluation

**Model:** `gemini-2.5-flash`

Evaluates market value, condition, and profit potential.

| Rating | Description |
|--------|-------------|
| **BARGAIN** | Significantly underpriced |
| **GREAT DEAL** | Good value opportunity |
| **NORMAL DEAL** | Fair market price |
| **BAD DEAL** | Overpriced or poor condition |

Only **BARGAIN** and **GREAT DEAL** listings are sent to Discord.

---

## Database

* **Engine:** SQLite (`otomoto_listings.db`)
* **Purpose:** Stores listing IDs to prevent duplicate processing

---

## Notifications

Discord webhook notifications include:
* Listing title
* Price & year
* AI analysis summary
* Image preview
* Direct link to listing

---

## Installation

```bash
git clone [https://github.com/Anti0I/Motorcycle-deal-finder.git](https://github.com/Anti0I/Motorcycle-deal-finder.git)
cd Motorcycle-deal-finder

pip install -r requirements.txt
playwright install
```

## Create .env
```bash
WEBHOOK_URL=your_discord_webhook
GEMINI_API_KEY=your_gemini_api_key
```

## Run
```bash
python main.py
```

## System Flow
```bash
Scrape → Filter New → Extract Details → AI Analysis → Send to Discord → Save to DB → Repeat
```

