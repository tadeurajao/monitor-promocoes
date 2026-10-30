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
PRECO_MAXIMO = float(os.getenv("PRECO_MAXIMO", "3500"))
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
        print(f"[erro] Falha ao renovar token: {resp.text}")
        return None
        
    return resp.json()["access_token"]


def buscar(termo: str, token: str | None) -> list[dict]:
    headers = dict(HEADERS_BASE)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {
        "q": termo,
        "limit": LIMITE_POR_BUSCA,
        "sort": "price_asc",
        "price": f"*-{int(PRECO_MAXIMO)}",  # filtro de preço no próprio servidor
        "condition": "new",
    }
    resp = requests.get(
        f"{ML_API}/sites/{SITE_ID}/search", headers=headers, params=params, timeout=TIMEOUT
    )
    if resp.status_code == 403:
        raise RuntimeError(f"403 na busca '{termo}': {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json().get("results", [])


def eh_notebook_valido(titulo: str) -> bool:
    """Filtro extra: a busca do ML traz acessórios/peças misturados."""
    t = titulo.lower()
    if "notebook" not in t and "laptop" not in t:
        return False
    if "16gb" not in t.replace(" ", ""):
        return False
    if not ("ryzen 7" in t or "i7" in t):
        return False
    lixo = ("carregador", "bateria", "tela ", "teclado", "capa", "mochila", "suporte",
            "placa mãe", "placa-mãe", "memória ram", "cooler", "peças", "defeito")
    return not any(p in t for p in lixo)


def coletar_ofertas(token: str | None) -> list[dict]:
    ofertas: dict[str, dict] = {}
    for termo in TERMOS_BUSCA:
        for item in buscar(termo, token):
            preco = item.get("price")
            titulo = item.get("title", "")
            if preco is None or preco >= PRECO_MAXIMO or not eh_notebook_valido(titulo):
                continue
            ofertas[item["id"]] = {
                "id": item["id"],
                "titulo": titulo,
                "preco": float(preco),
                "link": item.get("permalink", ""),
                "frete_gratis": item.get("shipping", {}).get("free_shipping", False),
            }
    return sorted(ofertas.values(), key=lambda o: o["preco"])


# ---------------------------------------------------------------- Persistência
def carregar_vistos() -> set[str]:
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def salvar_vistos(ids: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")


# ---------------------------------------------------------------- Telegram
def brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def enviar_telegram(texto: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()


def montar_mensagens(ofertas: list[dict]) -> list[str]:
    """Quebra em blocos para respeitar o limite de 4096 caracteres do Telegram."""
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    linhas = [
        f"💻 <b>{esc(o['titulo'])}</b>\n💰 {brl(o['preco'])}"
        f"{' 🚚 frete grátis' if o['frete_gratis'] else ''}\n🔗 {o['link']}"
        for o in ofertas
    ]
    cabecalho = f"🔥 <b>{len(ofertas)} oferta(s) abaixo de {brl(PRECO_MAXIMO)}</b>\n\n"
    mensagens, atual = [], cabecalho
    for linha in linhas:
        if len(atual) + len(linha) + 2 > 4000:
            mensagens.append(atual)
            atual = ""
        atual += linha + "\n\n"
    mensagens.append(atual)
    return mensagens


# ---------------------------------------------------------------- Main
def main() -> int:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("[erro] TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são obrigatórios.")
        return 1

    token = obter_access_token()
    ofertas = coletar_ofertas(token)
    print(f"Ofertas encontradas abaixo de {brl(PRECO_MAXIMO)}: {len(ofertas)}")

    vistos = carregar_vistos()
    novas = [o for o in ofertas if o["id"] not in vistos]
    print(f"Novas (ainda não alertadas): {len(novas)}")

    if novas:
        for msg in montar_mensagens(novas):
            enviar_telegram(msg)
        vistos.update(o["id"] for o in novas)

    salvar_vistos(vistos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
