import time
import random
import logging
import sqlite3
import os
import json
import requests
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types

load_dotenv()
MONITORED_URLS = [
    "https://www.otomoto.pl/motocykle-i-quady/sportowy--typ-naked?search%5Bfilter_float_engine_capacity%3Afrom%5D=125&search%5Border%5D=created_at_first%3Adesc"
]

WEBHOOK_URL = "https://discord.com/api/webhooks/1475461755332333630/9RRZ-W7PpKptSdz401FwEnvKI4Y193BDk_fXg_E7BrUFx8c-u-F2WhXdUZqrWZpSo6Og"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
GEMINI_MODEL = "gemini-2.0-flash"

INTERWAL_SPRAWDZANIA_MIN = 3
INTERWAL_SPRAWDZANIA_MAX = 7

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def init_db(clean_start=False):
    conn = sqlite3.connect('otomoto_listings.db')
    cursor = conn.cursor()
    if clean_start:
        cursor.execute('DROP TABLE IF EXISTS listings')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

def is_listing_new(listing_id):
    conn = sqlite3.connect('otomoto_listings.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM listings WHERE id = ?', (listing_id,))
    result = cursor.fetchone()
    conn.close()
    return result is None

def save_listing(listing_id):
    conn = sqlite3.connect('otomoto_listings.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO listings (id) VALUES (?)', (listing_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

def extract_from_otomoto(page):
    listings = []
    try:
        page.wait_for_selector('article[data-testid="listing-ad"], article[data-id]', timeout=15000)
    except KeyboardInterrupt:
        raise
    except Exception:
        logging.warning("Nie znaleziono ogłoszeń Otomoto w zadanym czasie. Możliwa kontrola antybotowa.")
        return listings
        
    articles = page.locator('article[data-testid="listing-ad"], article[data-id]').all()
    for article in articles:
        try:
            listing_id = article.get_attribute('data-id') or article.get_attribute('id')
            if not listing_id: continue
            
            is_today = False
            lines = article.inner_text().lower().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith("dzisiaj") or "minut temu" in line or "godzin temu" in line or "sekund temu" in line:
                    is_today = True
                    break
                
            title_elem = article.locator('h1 a, h2 a, h6 a, h2').first
            title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Nieznany pojazd (Otomoto)"
            
            url_elem = article.locator('a').first
            url = url_elem.get_attribute('href') if url_elem.count() > 0 else ""
                
            price_text = "Nieznana cena"
            for loc in [
                article.locator("h3:has-text('PLN')").first,
                article.locator("h3:has-text('EUR')").first,
                article.locator("span:has-text('PLN')").first,
                article.locator("h3").first, 
            ]:
                if loc.count() > 0:
                    p = loc.inner_text().strip()
                    if p:
                        price_text = p
                        break
            
            year = "Nieznany rocznik"
            labels_elem = article.locator('[data-testid="ad-labels"], [data-id="ad-labels"], .ad-labels').first
            if labels_elem.count() > 0:
                labels_text = labels_elem.inner_text().strip()
                match = re.search(r'\b(19\d{2}|20[0-4]\d)\b', labels_text)
                if match:
                    year = match.group(1)
            
            image_url = ""
            img_elem = article.locator('img').first
            if img_elem.count() > 0:
                image_url = img_elem.get_attribute('src') or img_elem.get_attribute('data-src') or ""

            listings.append({
                'id': listing_id, 'title': title, 'price': price_text, 
                'url': url, 'image_url': image_url, 'is_today': is_today,
                'year': year
            })
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logging.debug(f"Błąd parsowania elementu Otomoto: {e}")
    return listings

def extract_listing_details(context, url):
    details = {"description": "", "parameters": "", "highlights": ""}
    if not url or not str(url).startswith('http'):
        return details
        
    page = None
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2) 
        
        # --- 1. Opis ---
        desc_locators = [
            'div[data-cy="ad_description"]',
            'div[data-testid="content-description-section"]',
            '.offer-description__description'
        ]
        for loc in desc_locators:
            elem = page.locator(loc).first
            if elem.count() > 0:
                details['description'] = elem.inner_text().strip()
                break
        
        # --- 2. Highlights ---
        highlight_params = []
        highlight_selectors = [
            '[data-testid="content-highlight-details-section"]',
            '[data-testid="highlight-details-section"]',
        ]
        for sel in highlight_selectors:
            highlight_section = page.locator(sel).first
            if highlight_section.count() > 0:
                highlight_text = highlight_section.inner_text().strip()
                if highlight_text:
                    highlight_params.append(highlight_text)
                break 
        
        if highlight_params:
            details['highlights'] = "\n".join(highlight_params)
        
        # --- 3. Main Details ---
        technical_params = []
        try:
            page.wait_for_selector('[data-testid="main-details-section"]', timeout=5000)
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
            
        detail_section = page.locator('[data-testid="main-details-section"]').first
        if detail_section.count() > 0:
            details_list = detail_section.locator('[data-testid="detail"]').all()
            for d in details_list:
                label = d.get_attribute('aria-label')
                if label:
                    technical_params.append(label)
                else:
                    txt = d.inner_text().strip()
                    if txt and len(txt) < 200:
                        technical_params.append(txt)
        
        # --- 4. Extra params ---
        extra_params = []
        extra_selectors = [
            'div[data-testid="content-details-section"]',
            'div[data-testid="content-details-section-wide"]',
        ]
        for sel in extra_selectors:
            extra_section = page.locator(sel).first
            if extra_section.count() > 0:
                extra_text = extra_section.inner_text().strip()
                if extra_text:
                    extra_params.append(extra_text)
                break

        # --- 5. Combined details and equipment ---
        combined_selectors = [
            '[data-testid="combined-details-and-equipment-section"]',
            '#combined-details-and-equipment-section',
            '.combined-details-and-equipment-section'
        ]
        for sel in combined_selectors:
            combined_section = page.locator(sel).first
            if combined_section.count() > 0:
                combined_text = combined_section.inner_text().strip()
                if combined_text:
                    extra_params.append("--- SZCZEGÓŁY I WYPOSAŻENIE ---")
                    extra_params.append(combined_text)
                break
        
        # --- 6. Fallback (keywords) ---
        if not technical_params and not highlight_params:
            param_candidates = page.locator(
                '[class*="ooa-1y1j4sq"], [class*="e1kkw2jt0"], '
                '.offer-params__item, '
                'ul[data-testid="accordion-details-list"] li'
            ).all()
            for item in param_candidates:
                try:
                    text = item.inner_text().strip()
                    if not text or len(text) > 150:
                        continue
                    if any(text in p for p in technical_params) or any(p in text for p in technical_params):
                        continue
                    keywords = [
                        "Rok produkcji", "Przebieg", "Pojemność", "Moc",
                        "Skrzynia", "Typ silnika", "Uszkodzony", "Bezwypadkowy",
                        "Stan", "Model", "Marka"
                    ]
                    if ":" in text or any(kw in text for kw in keywords):
                        technical_params.append(text)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    continue

        all_params = []
        if technical_params:
            all_params.extend(technical_params)
        if extra_params:
            all_params.extend(extra_params)
            
        if all_params:
            details['parameters'] = "\n".join(all_params)
        else:
            param_locators = [
                'ul[data-testid="accordion-details-list"]',
                '.offer-params'
            ]
            for loc in param_locators:
                elem = page.locator(loc).first
                if elem.count() > 0:
                    details['parameters'] = elem.inner_text().strip()
                    break
        
        logging.info(f"Pobrano szczegóły - Opis: {len(details['description'])} zn., "
                     f"Highlights: {len(details['highlights'])} zn., "
                     f"Parametry: {len(details['parameters'])} zn.")
                
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logging.error(f"Błąd podczas pobierania detali ogłoszenia {url}: {e}")
    finally:
        if page and not page.is_closed():
            try:
                page.close()
            except:
                pass
            
    return details

def check_bargain_gemini(title, price, year, url, details):
    if not client:
        return "NORMAL DEAL", "Brak klucza GEMINI_API_KEY."

    if "Nieznany pojazd" in title:
        return "NORMAL DEAL", "Nie można przeanalizować - brak tytułu z serwisu."

    desc_cropped = details['description'][:2500] if details['description'] else "Brak opisu"
    params_cropped = details['parameters'][:2500] if details['parameters'] else "Brak parametrów"
    highlights_cropped = details.get('highlights', '')[:1000] if details.get('highlights') else "Brak wyróżnionych parametrów"

    prompt = f"""
    Jesteś wybitnym ekspertem polskiego rynku motocyklowego (Otomoto/OLX) oraz doświadczonym handlarzem (flipperem).
    Twoim zadaniem jest ocena opłacalności zakupu tego motocykla w celu dalszej odsprzedaży z zyskiem.

    DANE OGŁOSZENIA:
    Tytuł: {title}
    Rocznik pojazdu: {year}
    Cena: {price}
    Link: {url}

    NAJWAŻNIEJSZE PARAMETRY (HIGHLIGHT):
    {highlights_cropped}

    SZCZEGÓŁOWE PARAMETRY I WYPOSAŻENIE MOTOCYKLA:
    {params_cropped}

    OPIS SPRZEDAJĄCEGO:
    {desc_cropped}

    Instrukcje analizy:
    1. Oceń REALNĄ WARTOŚĆ RYNKOWĄ tego modelu. Jako priorytet traktuj DANE Z PARAMETRÓW, SZCZEGÓLNIE PRZEKAZANY ROCZNIK:
       - ROK PRODUKCJI: {year}
       - PRZEBIEG (ile km przejechał)
       - POJEMNOŚĆ SILNIKA (cm³)
       - MOC (KM/kW)
       - MODEL motocykla (marka i model)
       - CZY JEST USZKODZONY (uszkodzony/bezwypadkowy/stan)
    2. Zwróć szczególną uwagę na mankamenty (np. uszkodzony silnik, rysa, brak dokumentów, sprowadzony do opłat).
    3. Kategorie oceny:
       - BARGAIN: Prawdziwa perełka. Cena drastycznie zaniżona (co najmniej 30% poniżej rynku). Potężny potencjał zysku.
       - GREAT DEAL: Bardzo dobra oferta. Cena ok. 15-20% poniżej rynku, łatwe do upłynnienia.
       - NORMAL DEAL: Cena rynkowa. Niewielki potencjał zarobku.
       - BAD DEAL: Motocykl za drogi lub koszty napraw przewyższają sens zakupu.

    Odpowiedz w formacie JSON z polami "deal_type" oraz "analysis".
    """

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
            text = response.text.strip()
            data = json.loads(text)

            deal_type = data.get("deal_type", "NORMAL DEAL").upper()
            if deal_type not in ["BAD DEAL", "NORMAL DEAL", "GREAT DEAL", "BARGAIN"]:
                deal_type = "NORMAL DEAL"

            return deal_type, data.get("analysis", "Brak dokładnej analizy.")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Resource" in error_str:
                wait = 30 * (attempt + 1)
                logging.warning(f"Limit Gemini API! Oczekiwanie {wait}s... (próba {attempt+1}/3)")
                time.sleep(wait)
            else:
                logging.error(f"Błąd Gemini API (próba {attempt+1}/3): {e}")
                time.sleep(5)

    return "NORMAL DEAL", "Nie udało się zweryfikować przez AI."

def send_discord_notification(title, price, year, url, image_url, deal_type="NORMAL DEAL", analysis=""):
    if not WEBHOOK_URL or WEBHOOK_URL == "TWÓJ_WEBHOOK_DISCORD":
        return

    colors = {
        "GREAT DEAL": 0x2ECC71, 
        "BARGAIN": 0xF1C40F     
    }
    
    display_title = f"[{deal_type}] {title} ({year})"[:256]
    
    embed = {
        "title": display_title,
        "color": colors.get(deal_type, 0x2ECC71),
        "description": f"**Cena:** {price}\n**Rocznik:** {year}\n\n**Analiza pod profit:**\n{analysis}"[:4096]
    }
    
    if url and str(url).startswith('http'):
        embed["url"] = url
    if image_url and str(image_url).startswith('http'):
        embed["thumbnail"] = {"url": image_url}
        
    data = {
        "username": "Monitor AI - OKAZJE",
        "embeds": [embed]
    }
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        logging.error(f"Błąd Discord: {e}")

def main():
    init_db(clean_start=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        first_run = True
        while True:
            page = None
            try:
                page = context.new_page()
                
                for target_url in MONITORED_URLS:
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                        time.sleep(2) 
                        
                        listings = extract_from_otomoto(page)
                            
                        for listing in reversed(listings):
                            if is_listing_new(listing['id']):
                                
                                if first_run:
                                    save_listing(listing['id'])
                                    continue
                                
                                if not listing['is_today']:
                                    logging.info(f"Pominięto starą ofertę: {listing['title']}")
                                    save_listing(listing['id'])
                                    continue

                                logging.info(f"Pobieranie szczegółów nowej oferty: {listing['title']} (Rocznik: {listing['year']})")
                                details = extract_listing_details(context, listing['url'])
                                
                                deal_type, analysis = check_bargain_gemini(
                                    listing['title'], listing['price'], listing['year'], listing['url'], details
                                )
                                
                                if deal_type in ["GREAT DEAL", "BARGAIN"]:
                                    logging.info(f"ZNALEZIONO OKAZJĘ! Wysyłam na Discord: {listing['title']} [{deal_type}] - {listing['price']}")
                                    send_discord_notification(
                                        title=listing['title'], price=listing['price'], year=listing['year'],
                                        url=listing['url'], image_url=listing['image_url'], 
                                        deal_type=deal_type, analysis=analysis
                                    )
                                else:
                                    logging.info(f"Pominięto słabą ofertę: {listing['title']} [{deal_type}] - {listing['price']}")
                                
                                save_listing(listing['id'])
                                time.sleep(5) 
                                
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        logging.error(f"Problem z pobraniem strony Otomoto: {e}")
                
                if first_run:
                    logging.info("Skan początkowy gotowy. Zignorowano obecne oferty. Od teraz skrypt analizuje NOWE wrzutki...")
                    first_run = False
                
                wait_seconds = random.randint(INTERWAL_SPRAWDZANIA_MIN * 60, INTERWAL_SPRAWDZANIA_MAX * 60)
                logging.info(f"Oczekiwanie {wait_seconds // 60} minut i {wait_seconds % 60} sekund do kolejnego sprawdzenia...")
                time.sleep(wait_seconds)
                
            except KeyboardInterrupt:
                logging.info("Otrzymano wciśnięcie (Ctrl+C). Kończenie pracy programu.")
                break
            except Exception as e:
                logging.error(f"Niespodziewany błąd pętli głównej: {e}")
                time.sleep(60)
            finally:
                if page and not page.is_closed():
                    try:
                        page.close()
                    except:
                        pass

if __name__ == "__main__":
    main()