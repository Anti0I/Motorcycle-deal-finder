import time
import random
import logging
from playwright.sync_api import sync_playwright

from config import MONITORED_URLS, INTERWAL_SPRAWDZANIA_MIN, INTERWAL_SPRAWDZANIA_MAX
from database import init_db, is_listing_new, save_listing
from scraper import extract_from_otomoto, extract_listing_details
from analyzer import check_bargain_gemini
from notifier import send_discord_notification


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

                                # Aktualizuj rocznik z detali strony, jeśli nie znaleziono na liście
                                if listing['year'] == "Nieznany rocznik" and details.get('year'):
                                    listing['year'] = details['year']
                                    logging.info(f"Rocznik uzupełniony ze strony szczegółowej: {listing['year']}")

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
                    except Exception:
                        pass


if __name__ == "__main__":
    main()