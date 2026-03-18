````markdown
# 🏍️ Motorcycle Deal Finder

> 🤖 AI-powered bot that finds **underpriced motorcycle listings** and sends the best deals to Discord.

---

## ⚡ What Is This?

Automated system that:
- Monitors **Otomoto** listings
- Extracts data (price, year, details)
- Uses AI to evaluate profitability
- Sends only **valuable deals** to Discord

---

## 🛠️ Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=microsoft&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)
![Discord](https://img.shields.io/badge/Discord_Webhook-5865F2?style=for-the-badge&logo=discord&logoColor=white)

---

## 🧠 AI Model

- Model: `gemini-2.5-flash`
- Evaluates:
  - market value
  - condition
  - profit potential

**Output:**
- `BARGAIN`
- `GREAT DEAL`
- `NORMAL DEAL`
- `BAD DEAL`

---

## 💾 Database

- SQLite (`otomoto_listings.db`)
- Stores listing IDs
- Prevents duplicate processing

---

## 📩 Notifications

- Discord Webhook
- Sends only:
  - `GREAT DEAL`
  - `BARGAIN`

Includes:
- title
- price
- year
- AI analysis
- image + link

---

## ⚙️ How To Use

```bash
git clone https://github.com/Anti0I/Motorcycle-deal-finder.git
cd Motorcycle-deal-finder

pip install -r requirements.txt
playwright install
````

Create `.env`:

```env
WEBHOOK_URL=your_discord_webhook
GEMINI_API_KEY=your_gemini_api_key
```

Run:

```bash
python main.py
```

---

## 🔄 System Flow

```
Scrape → Filter new → Extract details → AI analysis → Send to Discord → Save to DB → Repeat
```

```
```
