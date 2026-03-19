import os
import logging
from dotenv import load_dotenv
from google import genai

load_dotenv()

# --- URLs do monitorowania ---
MONITORED_URLS = [
    "https://www.otomoto.pl/motocykle-i-quady/sportowy--typ-naked?search%5Bfilter_float_engine_capacity%3Afrom%5D=125&search%5Border%5D=created_at_first%3Adesc"
]

# --- Klucze i webhooki ---
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Klient Gemini ---
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
GEMINI_MODEL = "gemini-2.5-flash"

# --- Interwał sprawdzania (minuty) ---
INTERWAL_SPRAWDZANIA_MIN = 3
INTERWAL_SPRAWDZANIA_MAX = 7

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
