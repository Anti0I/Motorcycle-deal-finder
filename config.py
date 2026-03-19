import os
import logging
from dotenv import load_dotenv

load_dotenv()

# --- URLs do monitorowania ---
MONITORED_URLS = [
    "https://www.otomoto.pl/motocykle-i-quady/sportowy--typ-naked?search%5Bfilter_float_engine_capacity%3Afrom%5D=300&search%5Bfilter_float_engine_capacity%3Ato%5D=1500&search%5Bfilter_float_mileage%3Afrom%5D=5000&search%5Bfilter_float_mileage%3Ato%5D=50000&search%5Border%5D=created_at_first%3Adesc"
]

# --- Klucze i webhooki ---
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Ollama ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")

# --- Interwał sprawdzania (minuty) ---
INTERWAL_SPRAWDZANIA_MIN = 3
INTERWAL_SPRAWDZANIA_MAX = 7

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
