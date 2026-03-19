import time
import re
import logging


def extract_from_otomoto(page):
    """Pobiera listę ogłoszeń z bieżącej strony Otomoto."""
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
            if not listing_id:
                continue

            is_today = False
            article_text = article.inner_text().lower()
            # Regex obsługuje wszystkie polskie formy odmiany:
            # minuta/minuty/minut temu, godzina/godziny/godzin temu, sekunda/sekundy/sekund temu
            if re.search(
                r'dzisiaj|'
                r'\d+\s+minut[ay]?\s+temu|'
                r'\d+\s+godzin[ya]?\s+temu|'
                r'\d+\s+sekund[ay]?\s+temu',
                article_text
            ):
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

            year = "Nieznany rocznik"

            # Strategia 1: indywidualne elementy [data-testid="ad-label"] (liczba pojedyncza)
            label_items = article.locator('[data-testid="ad-labels"]').all()
            for item in label_items:
                try:
                    item_text = item.inner_text().strip()
                    match = re.search(r'\b(19\d{2}|20[0-4]\d)\b', item_text)
                    if match:
                        year = match.group(1)
                        break
                except Exception:
                    continue

            # Strategia 2: kontener ad-labels (jeśli strategia 1 nie znalazła)
            if year == "Nieznany rocznik":
                labels_selectors = [
                    '[data-testid="ad-labels"]',
                    '[data-id="ad-labels"]',
                    '.ad-labels',
                    '[data-testid="listing-ad-labels"]',
                ]
                for sel in labels_selectors:
                    labels_elem = article.locator(sel).first
                    if labels_elem.count() > 0:
                        labels_text = labels_elem.inner_text().strip()
                        match = re.search(r'\b(19\d{2}|20[0-4]\d)\b', labels_text)
                        if match:
                            year = match.group(1)
                            break

            # Strategia 3: fallback - szukaj roku w tytule ogłoszenia
            if year == "Nieznany rocznik":
                match = re.search(r'\b(19\d{2}|20[0-4]\d)\b', title)
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
    """Otwiera stronę ogłoszenia i wyciąga szczegółowe parametry."""
    details = {"description": "", "parameters": "", "highlights": "", "year": ""}
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

        # --- Ekstrakcja rocznika ze strony szczegółowej ---
        extracted_year = ""
        # Szukaj w highlights i parametrach
        for text_source in [details['highlights'], details['parameters']]:
            if text_source:
                year_match = re.search(r'(?:Rok produkcji|Rocznik)[:\s]*(19\d{2}|20[0-4]\d)', text_source)
                if year_match:
                    extracted_year = year_match.group(1)
                    break
        # Fallback: szukaj dowolnego roku w parametrach
        if not extracted_year:
            for text_source in [details['highlights'], details['parameters']]:
                if text_source:
                    year_match = re.search(r'\b(19\d{2}|20[0-4]\d)\b', text_source)
                    if year_match:
                        extracted_year = year_match.group(1)
                        break
        details['year'] = extracted_year

        logging.info(
            f"Pobrano szczegóły - Opis: {len(details['description'])} zn., "
            f"Highlights: {len(details['highlights'])} zn., "
            f"Parametry: {len(details['parameters'])} zn., "
            f"Rocznik: {details['year'] or 'nie znaleziono'}"
        )

    except KeyboardInterrupt:
        raise
    except Exception as e:
        logging.error(f"Błąd podczas pobierania detali ogłoszenia {url}: {e}")
    finally:
        if page and not page.is_closed():
            try:
                page.close()
            except Exception:
                pass

    return details
