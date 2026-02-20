import time
import random
import logging
import sqlite3
import requests
import json
from google import genai
from playwright.sync_api import sync_playwright
MONITORED_URLS = [
    ""
]

WEBHOOK_URL = "" 
GEMINI_API_KEY = ""

INTERWAL_SPRAWDZANIA_MIN = 3
INTERWAL_SPRAWDZANIA_MAX = 3

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
    except Exception:
        logging.warning("Nie znaleziono ogłoszeń Otomoto w zadanym czasie. Możliwa kontrola antybotowa.")
        return listings
        
    articles = page.locator('article[data-testid="listing-ad"], article[data-id]').all()
    for article in articles:
        try:
            listing_id = article.get_attribute('data-id') or article.get_attribute('id')
            if not listing_id: continue
            
            # Weryfikacja czy oferta jest z dzisiaj
            is_today = False
            date_text = article.inner_text().lower()
            if any(kw in date_text for kw in ["dzisiaj", "godzin", "minut", "sekund"]) and "wczoraj" not in date_text:
                is_today = True
                
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
            
            image_url = ""
            img_elem = article.locator('img').first
            if img_elem.count() > 0:
                image_url = img_elem.get_attribute('src') or img_elem.get_attribute('data-src') or ""

            listings.append({
                'id': listing_id, 'title': title, 'price': price_text, 
                'url': url, 'image_url': image_url, 'is_today': is_today
            })
        except Exception as e:
            logging.debug(f"Błąd parsowania elementu Otomoto: {e}")
    return listings

def extract_listing_details(context, url):
    details = {"description": "", "parameters": ""}
    if not url or not str(url).startswith('http'):
        return details
        
    page = None
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1) # Poczekaj na załadowanie skryptów (np. "pokaż więcej")
        
        # Pobieranie opisu
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
                
        # Pobieranie parametrów (rocznik, przebieg, bezwypadkowość itp.)
        param_locators = [
            'div[data-testid="content-details-section"]',
            'ul[data-testid="accordion-details-list"]',
            '.offer-params'
        ]
        for loc in param_locators:
            elem = page.locator(loc).first
            if elem.count() > 0:
                details['parameters'] = elem.inner_text().strip()
                break
                
    except Exception as e:
        logging.error(f"Błąd podczas pobierania detali ogłoszenia {url}: {e}")
    finally:
        if page:
            try:
                page.close()
            except:
                pass
            
    return details

def check_bargain_gemini(title, price, url, details):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "TWÓJ_KLUCZ_GEMINI":
        return "NORMAL DEAL", "Brak klucza Gemini API."
        
    if "Nieznany pojazd" in title:
        return "NORMAL DEAL", "Nie można przeanalizować - brak tytułu z serwisu."
        
    desc_cropped = details['description'][:2500] if details['description'] else "Brak opisu"
    params_cropped = details['parameters'][:1500] if details['parameters'] else "Brak parametrów"
        
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jesteś wybitnym ekspertem polskiego rynku motocyklowego (Otomoto/OLX) oraz doświadczonym handlarzem (flipperem). 
        Twoim zadaniem jest ocena opłacalności zakupu tego motocykla w celu dalszej odsprzedaży z zyskiem.
        
        DANE OGŁOSZENIA:
        Tytuł: {title}
        Cena: {price}
        Link: {url}
        
        PARAMETRY MOTOCYKLA (rocznik, przebieg, stan itp.):
        {params_cropped}
        
        OPIS SPRZEDAJĄCEGO:
        {desc_cropped}
        
        Instrukcje analizy:
        1. Oceń REALNĄ WARTOŚĆ RYNKOWĄ tego modelu w tym roczniku, z tym przebiegiem, wyposażeniem dodatkowym i w opisywanym stanie.
        2. Zwróć szczególną uwagę na mankamenty (np. uszkodzony silnik, rysa, brak dokumentów, sprowadzony do opłat) o których wspomina sprzedający w opisie i odejmij szacunkowy koszt napraw/rejestracji od potencjalnego zysku.
        3. Kategorie oceny:
           - BARGAIN: Prawdziwa perełka. Cena po uwzględnieniu stanu/kosztów jest drastycznie zaniżona (co najmniej 30% poniżej realnej ceny rynkowej). Potężny potencjał na szybki i duży zysk dla handlarza.
           - GREAT DEAL: Bardzo dobra oferta. Cena jest atrakcyjna i pozwala na pewny, niezły zarobek przy odsprzedaży (ok. 15-20% poniżej rynku, łatwe do upłynnienia).
           - NORMAL DEAL: Cena rynkowa, standardowa. Niewielki potencjał na zarobek, raczej wymiana gotówki z niewielką marżą.
           - BAD DEAL: Motocykl wyceniony za wysoko, ulep, skarbonka bez dna lub koszty napraw / wady znacząco przewyższają jakikolwiek sens zarobku. 

        Odpowiedź wygeneruj TYLKO w czystym formacie JSON bez żadnych dopisków u góry ani na dole. 
        Klucz 'analysis' to Twoja krótka, zwięzła i KONKRETNA analiza biznesowa (max 3-4 zdania). 
        Przykład adnotacji: "Rynkowa cena dla '08 to ok. 25-27k. Przewrotka to koszt rzędu 2k (owiewka, set). Czysty zysk szacunkowo ok. 4-5k minimum."
        
        Oczekiwany JSON:
        {{
            "deal_type": "BAD DEAL | NORMAL DEAL | GREAT DEAL | BARGAIN",
            "analysis": "Twoja analiza tutaj..."
        }}
        """
        
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                text = response.text.replace('```json', '').replace('```', '').strip()
                data = json.loads(text)
                
                deal_type = data.get("deal_type", "NORMAL DEAL").upper()
                if deal_type not in ["BAD DEAL", "NORMAL DEAL", "GREAT DEAL", "BARGAIN"]:
                    deal_type = "NORMAL DEAL"
                    
                return deal_type, data.get("analysis", "Brak dokładnej analizy.")
            except Exception as api_err:
                if '429' in str(api_err):
                    logging.warning("Limit AI Gemini! Oczekiwanie 60 sekund...")
                    time.sleep(60)
                else:
                    raise api_err
        return "NORMAL DEAL", "Nie udało się zweryfikować przez limity API."
    except Exception as e:
        return "NORMAL DEAL", f"Błąd API Gemini: {e}"

def send_discord_notification(title, price, url, image_url, deal_type="NORMAL DEAL", analysis=""):
    if not WEBHOOK_URL or WEBHOOK_URL == "TWÓJ_WEBHOOK_DISCORD":
        return

    colors = {
        "GREAT DEAL": 0x2ECC71, # Zielony
        "BARGAIN": 0xF1C40F     # Złoty
    }
    
    embed = {
        "title": f"[{deal_type}] {title}"[:256],
        "color": colors.get(deal_type, 0x2ECC71),
        "description": f"**Cena:** {price}\n\n**Analiza pod profit:**\n{analysis}"[:4096]
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
            try:
                page = context.new_page()
                
                for target_url in MONITORED_URLS:
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                        time.sleep(2) 
                        
                        listings = extract_from_otomoto(page)
                            
                        for listing in reversed(listings):
                            if is_listing_new(listing['id']):
                                
                                # Podczas pierwszego uruchomienia wrzucamy WSZYSTKO co jest na stronie do bazy i ignorujemy
                                if first_run:
                                    save_listing(listing['id'])
                                    continue
                                
                                # Dodatkowe zabezpieczenie: ignorujemy odświeżone stare oferty z wczoraj
                                if not listing['is_today']:
                                    logging.info(f"Pominięto starą ofertę: {listing['title']}")
                                    save_listing(listing['id'])
                                    continue

                                # Weryfikacja tylko dla NOWYCH ofert po pierwszym skanie
                                logging.info(f"Pobieranie szczegółów nowej oferty: {listing['title']}")
                                details = extract_listing_details(context, listing['url'])
                                
                                deal_type, analysis = check_bargain_gemini(
                                    listing['title'], listing['price'], listing['url'], details
                                )
                                
                                if deal_type in ["GREAT DEAL", "BARGAIN"]:
                                    logging.info(f"ZNALEZIONO OKAZJĘ! Wysyłam na Discord: {listing['title']} [{deal_type}] - {listing['price']}")
                                    send_discord_notification(
                                        title=listing['title'], price=listing['price'], 
                                        url=listing['url'], image_url=listing['image_url'], 
                                        deal_type=deal_type, analysis=analysis
                                    )
                                else:
                                    logging.info(f"Pominięto słabą ofertę: {listing['title']} [{deal_type}] - {listing['price']}")
                                
                                save_listing(listing['id'])
                                time.sleep(5) 
                                
                    except Exception as e:
                        logging.error(f"Problem z pobraniem strony Otomoto: {e}")
                
                if first_run:
                    logging.info("Skan początkowy gotowy. Zignorowano obecne oferty. Od teraz skrypt analizuje NOWE wrzutki...")
                    first_run = False
                
                page.close()
                wait_seconds = random.randint(INTERWAL_SPRAWDZANIA_MIN * 60, INTERWAL_SPRAWDZANIA_MAX * 60)
                time.sleep(wait_seconds)
                
            except KeyboardInterrupt:
                logging.info("Otrzymano wciśnięcie (Ctrl+C). Kończenie pracy programu.")
                break
            except Exception as e:
                logging.error(f"Niespodziewany błąd pętli głównej: {e}")
                time.sleep(60)

if __name__ == "__main__":
    main()