"""
Robô de alerta de ofertas de notebook no Mercado Livre -> Telegram.

Variáveis de ambiente (GitHub Secrets):
  TELEGRAM_TOKEN      - token do bot (@BotFather)
  TELEGRAM_CHAT_ID    - id do chat que recebe os alertas
  ML_CLIENT_ID        - App ID do Mercado Livre (developers.mercadolivre.com.br)
  ML_CLIENT_SECRET    - Secret Key do app do Mercado Livre
  ML_REFRESH_TOKEN    - Token de atualização gerado via OAuth
Opcionais:
  PRECO_MAXIMO        - padrão 10000
  SEEN_FILE           - arquivo para não repetir alertas (padrão seen_ids.json)
"""

import json
import os
import sys
from pathlib import Path

import requests

ML_API = "https://api.mercadolibre.com"
SITE_ID = "MLB"
TERMOS_BUSCA = ["notebook 16gb ryzen 7", "notebook 16gb core i7"]
PRECO_MAXIMO = float(os.getenv("PRECO_MAXIMO", "10000"))
SEEN_FILE = Path(os.getenv("SEEN_FILE", "seen_ids.json"))
LIMITE_POR_BUSCA = 50
TIMEOUT = 20

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")

HEADERS_BASE = {"User-Agent": "ofertas-notebook-bot/1.0", "Accept": "application/json"}


# ---------------------------------------------------------------- Mercado Livre
def obter_access_token() -> str | None:
    """Token de aplicação via refresh_token (a busca exige autenticação de usuário)."""
    if not (ML_CLIENT_ID and ML_CLIENT_SECRET and ML_REFRESH_TOKEN):
        print("[erro] Credenciais ausentes. Verifique ML_CLIENT_ID, SECRET e REFRESH_TOKEN.")
        return None
    
    resp = requests.post(
        f"{ML_API}/oauth/token",
        headers={**HEADERS_BASE, "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "refresh_token": ML_REFRESH_TOKEN,
        },
        timeout=TIMEOUT,
    )
    
    if resp.status_code != 200:
        print(f"[erro] Falha ao renov
