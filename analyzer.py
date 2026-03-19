import json
import time
import logging
from google.genai import types
from config import client, GEMINI_MODEL


def check_bargain_gemini(title, price, year, url, details):
    """Ocenia opłacalność ogłoszenia przy użyciu Gemini API."""
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
