import time
import random
import logging
import sqlite3
import requests
import json
from google import genai
from playwright.sync_api import sync_playwright

# ==========================================
# KONFIGURACJA
# ==========================================
MONITORED_URLS = [
    "https://www.otomoto.pl/motocykle-i-quady/sportowy--typ-naked?search%5Bfilter_float_engine_capacity%3Afrom%5D=125&search%5Border%5D=created_at_first%3Adesc",
    "https://www.olx.pl/motoryzacja/motocykle-skutery/szosowo-turystyczny/?search%5Border%5D=created_at:desc",
    "https://www.olx.pl/motoryzacja/motocykle-skutery/sportowy/?search%5Border%5D=created_at:desc",
    "https://www.olx.pl/motoryzacja/motocykle-skutery/pozostale/?search%5Border%5D=created_at:desc"
]

WEBHOOK_URL = "TUTAJ_WKLEJ_SWOJ_WEBHOOK_DISCORD"
GEMINI_API_KEY = "TUTAJ_WKLEJ_SWOJ_KLUCZ_GEMINI"

INTERWAL_SPRAWDZANIA_MIN = 3  # Minimalny czas oczekiwania (w minutach)
INTERWAL_SPRAWDZANIA_MAX = 3  # Maksymalny czas oczekiwania (w minutach)
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def init_db():
    conn = sqlite3.connect('otomoto_listings.db')
    cursor = conn.cursor()
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
        page.wait_for_selector('article[data-id]', timeout=15000)
    except Exception:
        logging.warning("Nie znaleziono ogłoszeń Otomoto w zadanym czasie. Możliwa kontrola antybotowa.")
        return listings
        
    articles = page.locator('article[data-id]').all()
    for article in articles:
        try:
            listing_id = article.get_attribute('data-id')
            if not listing_id: continue
                
            title_elem = article.locator('h1 a, h2 a, h6 a').first
            if title_elem.count() == 0: title_elem = article.locator('a').first
            title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Nieznany pojazd"
            url = title_elem.get_attribute('href') if title_elem.count() > 0 else ""
                
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
                image_url = img_elem.get_attribute('src')
                if not image_url or image_url.startswith('data:image'):
                    try_lazy = img_elem.get_attribute('data-src')
                    if try_lazy: image_url = try_lazy

            listings.append({'id': listing_id, 'title': title, 'price': price_text, 'url': url, 'image_url': image_url})
        except Exception as e:
            logging.debug(f"Błąd parsowania elementu Otomoto: {e}")
    return listings

def extract_from_olx(page):
    listings = []
    try:
        page.wait_for_selector('div[data-cy="l-card"]', timeout=15000)
    except Exception:
        logging.warning("Nie znaleziono ogłoszeń OLX w zadanym czasie. Możliwa kontrola antybotowa.")
        return listings
        
    cards = page.locator('div[data-cy="l-card"]').all()
    for card in cards:
        try:
            anchor = card.locator('a').first
            url = anchor.get_attribute('href') if anchor.count() > 0 else ""
            if url and url.startswith('/'):
                url = "https://www.olx.pl" + url
            
            # W OLX link ogłoszenia (lub jego ścieżka bez parametrów) to dobry unikalny ID
            listing_id = url.split('#')[0].split('?')[0]
            if not listing_id: continue
            
            title_elem = card.locator('h6').first
            title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Nieznany pojazd (OLX)"
            
            price_elem = card.locator('[data-testid="ad-price"]').first
            price_text = price_elem.inner_text().strip() if price_elem.count() > 0 else "Nieznana cena"
            
            image_url = ""
            img_elem = card.locator('img').first
            if img_elem.count() > 0:
                image_url = img_elem.get_attribute('src')
                
            listings.append({'id': listing_id, 'title': title, 'price': price_text, 'url': url, 'image_url': image_url})
        except Exception as e:
            logging.debug(f"Błąd parsowania elementu OLX: {e}")
    return listings

def check_bargain_gemini(title, price):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "TUTAJ_WKLEJ_SWOJ_KLUCZ_GEMINI":
        return False, "Brak skonfigurowanego klucza Gemini API. System oznaczania rynkowej ceny nie zadziałał."
        
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Jesteś ekspertem i analitykiem polskiego rynku motocyklowego. Przeanalizuj poniższe ogłoszenie, aby określić, czy to wyjątkowa okazja cenowa.
        
        Dane ogłoszenia:
        - Tytuł: {title}
        - Cena: {price}
        
        Twoje zadanie:
        1. Rozpoznaj z tytułu markę, model, rocznik, pojemność, przebieg oraz informacje o stanie (np. "uszkodzony", "po szlifie", "silnik stuka", "idealny", "igła").
        2. Oszacuj przybliżoną średnią cenę rynkową dla tego modelu w Polsce (biorąc pod uwagę rocznik, jeśli jest w tytule).
        3. Oblicz, o ile ta oferta jest tańsza (lub droższa) od rynkowej średniej.
        4. Weź pod uwagę, że niska cena może wynikać z uszkodzeń wymienionych w tytule. Jeśli sprzęt jest mocno uszkodzony, to niska cena to norma, a nie "super okazja".
        5. Oceń, czy relacja stanu do ceny sprawia, że jest to wybitnie opłacalny zakup (prawdziwa okazja do szybkiego zakupu/handlu).
        
        Zwróć wynik WŁĄCZNIE w czystym formacie JSON (bez znaczników markdown typu ```json) według schematu:
        {{
            "is_bargain": true/false,
            "analysis": "Twój szczegółowy werdykt w punktach. Wypisz: \\n• Szacowana cena rynkowa: (kwota) \\n• Stan/uszkodzenia wywnioskowane z tytułu: (opis) \\n• Przebieg: (jeśli podano) \\n• O ile taniej od średniej: (kwota) \\n• Werdykt opłacalności: (krótkie podsumowanie)"
        }}
        """
        
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                # Oczyszczanie odpowiedzi ze znaczników markdown, jeśli AI by je dodało
                text = response.text.replace('```json', '').replace('```', '').strip()
                data = json.loads(text)
                return data.get("is_bargain", False), data.get("analysis", "Brak dokładnej analizy.")
            except Exception as api_err:
                if '429' in str(api_err):
                    logging.warning("Limit darmowego API Gemini wyczerpany (Zbyt dużo zapytań w minucie). Odczekuję 60 sekund przed ponowieniem...")
                    time.sleep(60)
                else:
                    raise api_err
                    
        return False, "Nie udało się zweryfikować z powodu nałożonych limitów prędkości API."
        
    except Exception as e:
        logging.error(f"Zapytanie AI zwróciło błąd: {e}")
        return False, f"Brak możliwości weryfikacji. Błąd API Gemini: {e}"
def send_discord_notification(title, price, url, image_url, is_bargain=False, analysis=""):
    if not WEBHOOK_URL or WEBHOOK_URL == "TUTAJ_WKLEJ_SWOJ_WEBHOOK_DISCORD":
        logging.warning("Nie wysłano powiadomienia - webhook nie jest skonfigurowany!")
        return

    embed = {
        "title": title[:256] if title else "Ogłoszenie pojazdu",
        "color": 0xFF3333, # Czerwony kolor paska
    }
    
    if url and str(url).startswith('http'):
        embed["url"] = url
    
    if is_bargain:
        embed["title"] = f"🚨 [OKAZJA / WAŻNE] {title}"[:256]
        embed["color"] = 0x33FF33 # Zielony kolor paska dla weryfikacji
        embed["description"] = f"**Cena:** {price}\n\n**Werdykt Sztucznej Inteligencji (Gemini Flash):**\n{analysis}"[:4096]
    else:
        # Standardowa nieokazyjna oferta / zablokowane API
        embed["description"] = f"**Cena:** {price}"[:4096]
        
    if image_url and str(image_url).startswith('http'):
        embed["thumbnail"] = {"url": image_url}
        
    data = {
        "username": "Otomoto/OLX Monitor AI",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Otomoto_logo_2021.svg/1024px-Otomoto_logo_2021.svg.png",
        "embeds": [embed]
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=data)
        if response.status_code >= 400:
            logging.error(f"Błąd Discord (Code {response.status_code}): {response.text}")
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Błąd podczas wysyłania powiadomienia Discord: {e}")

def main():
    if not WEBHOOK_URL or WEBHOOK_URL == "TUTAJ_WKLEJ_SWOJ_WEBHOOK_DISCORD":
        logging.warning("UWAGA: Nie skonfigurowano WEBHOOK_URL w skrypcie.")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "TUTAJ_WKLEJ_SWOJ_KLUCZ_GEMINI":
        logging.warning("UWAGA: Nie skonfigurowano GEMINI_API_KEY w skrypcie. Oceny rynkowe ofert nie będą działać!")
        
    logging.info("Inicjalizacja środowiska bazodanowego i start aplikacji...")
    init_db()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        first_run = True
        while True:
            try:
                # Otwarcie karty
                page = context.new_page()
                new_count = 0
                
                for target_url in MONITORED_URLS:
                    logging.info(f"Sprawdzam źródło: {target_url.split('?')[0]} ...")
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                        
                        if "otomoto.pl" in target_url:
                            listings = extract_from_otomoto(page)
                        elif "olx.pl" in target_url:
                            listings = extract_from_olx(page)
                        else:
                            listings = []
                            
                        # Sprawdzamy oferty
                        for listing in reversed(listings):
                            if is_listing_new(listing['id']):
                                if first_run:
                                    # Przy pierwszym uruchomieniu po prostu zapamiętujemy "stare" odnawiane ogłoszenia zastane na stronie
                                    save_listing(listing['id'])
                                else:
                                    new_count += 1
                                    logging.info(f"Znaleziono nowe ogłoszenie: {listing['title']} - {listing['price']}")
                                    
                                    # Odpalenie Gemini tylko dla konkretnej nieznajomej oferty!
                                    is_bargain, analysis = check_bargain_gemini(listing['title'], listing['price'])
                                    if is_bargain:
                                        logging.info("Oznaczono bieżące ogłoszenie jako OKAZJĘ rynkową!")
                                        
                                    send_discord_notification(
                                        title=listing['title'],
                                        price=listing['price'],
                                        url=listing['url'],
                                        image_url=listing['image_url'],
                                        is_bargain=is_bargain,
                                        analysis=analysis
                                    )
                                    
                                    save_listing(listing['id'])
                                    time.sleep(1)
                                
                    except Exception as e:
                        logging.error(f"Problem ze źródłem {target_url}: {e}")
                
                if first_run:
                    logging.info("Początkowe skanowanie zakończone. Obecne oferty zostały zignorowane.")
                    first_run = False
                
                # Zamknięcie karty po spenetrowaniu całego stosu na to jedno przejście
                page.close()
                
                if new_count == 0:
                    logging.info("Brak nowych ogłoszeń w tym sprawdzeniu dla wszystkich serwisów.")
                    
                wait_seconds = random.randint(INTERWAL_SPRAWDZANIA_MIN * 60, INTERWAL_SPRAWDZANIA_MAX * 60)
                logging.info(f"Usypiam robota. Kolejne sprawdzenie za ok. {wait_seconds // 60} minut i {wait_seconds % 60} sekund.")
                time.sleep(wait_seconds)
                
            except KeyboardInterrupt:
                logging.info("Otrzymano wciśnięcie (Ctrl+C). Kończenie pracy programu.")
                break
            except Exception as e:
                logging.error(f"Niespodziewany błąd w pętli: {e}")
                time.sleep(60)

if __name__ == "__main__":
    main()
