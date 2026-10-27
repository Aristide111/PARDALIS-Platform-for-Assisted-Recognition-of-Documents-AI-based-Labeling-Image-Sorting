import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
ALBERT_API_KEY = os.getenv("ALBERT")

if not ALBERT_API_KEY:
    raise ValueError("La clé API 'ALBERT' est introuvable dans le fichier .env.")

client = OpenAI(
    base_url="https://albert.api.etalab.gouv.fr/v1",
    api_key=ALBERT_API_KEY,
)

MODEL_ID = "mistralai/Ministral-3-8B-Instruct-2512"
NON_IDENTIFIE = "Non identifié"
AUCUNE_CORRESPONDANCE = "Aucune correspondance"

MODE_REF = "Approche 1 — Référentiel (liste fermée)"
MODE_LIBRE = "Approche 2 — Identification libre"

COLONNES_REF = ["Identifiant", "Caractéristiques"]