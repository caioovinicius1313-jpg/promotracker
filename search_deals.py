#!/usr/bin/env python3
"""Busca diária de promoções: para cada produto em products.json, pesquisa preços
(Google Shopping via Serper, barato; ou Claude com web search) e grava em data/deals.json."""

import datetime as dt
import json
import os
import re
import statistics
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
PRODUCTS_FILE = ROOT / "products.json"
DEALS_FILE = ROOT / "data" / "deals.json"

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES", "5"))  # buscas web por produto
HISTORY_DAYS = 90

SYSTEM = """Você é um caçador de promoções no Brasil. Dado um produto, pesquise na web \
e encontre as MELHORES ofertas disponíveis hoje em lojas brasileiras confiáveis \
(Kabum, Pichau, Terabyte, Amazon BR, Mercado Livre, Magalu, Americanas, Casas Bahia, \
Shopee, AliExpress, etc.), comparando preços à vista (Pix/boleto) e também o parcelado.

Regras:
- Use somente preços e links que você viu nos resultados da busca. Nunca invente.
- O produto precisa ser exatamente o pedido (mesmo modelo/especificações). Ignore \
variações incompatíveis, kits diferentes e anúncios suspeitos.
- Prefira lojas confiáveis; sinalize vendedores desconhecidos em "note".
- Preço em reais, como número (ex.: 1299.90), o menor preço à vista com frete \
quando conseguir saber; se o frete for desconhecido, diga em "shipping".
- Retorne de 1 a 5 ofertas, da mais barata para a mais cara. Se não achar nada \
confiável, retorne "offers": [].

Responda APENAS com um bloco JSON, sem texto fora dele, neste formato:
{"offers":[{"store":"","title":"","price":0,"url":"","condition":"novo|usado|reembalado","shipping":"","note":""}],"summary":"1-2 frases sobre o cenário de preço hoje"}"""


def build_prompt(p: dict) -> str:
    lines = [f"Produto: {p['name']}"]
    if p.get("notes"):
        lines.append(f"Detalhes/requisitos: {p['notes']}")
    if p.get("target_price"):
        lines.append(f"Preço-alvo do usuário: R$ {p['target_price']}")
    lines.append(f"Data de hoje: {dt.date.today().isoformat()}")
    return "\n".join(lines)


def extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def clean_offers(offers: list) -> list:
    out = []
    for o in offers or []:
        try:
            price = float(o.get("price"))
        except (TypeError, ValueError):
            continue
        url = str(o.get("url", ""))
        if price <= 0 or not url.startswith(("http://", "https://")):
            continue
        out.append({
            "store": str(o.get("store", ""))[:60],
            "title": str(o.get("title", ""))[:160],
            "price": round(price, 2),
            "url": url,
            "condition": str(o.get("condition", "novo"))[:20],
            "shipping": str(o.get("shipping", ""))[:80],
            "note": str(o.get("note", ""))[:200],
        })
    return sorted(out, key=lambda o: o["price"])


def search_claude(client, product: dict) -> dict:
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": MAX_SEARCHES,
        "user_location": {"type": "approximate", "country": "BR",
                          "timezone": "America/Sao_Paulo"},
    }]
    messages = [{"role": "user", "content": build_prompt(product)}]
    resp = None
    for _ in range(5):  # continua se a API pausar um turno longo
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM,
                                      tools=tools, messages=messages)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = extract_json(text)
    return {"offers": clean_offers(data.get("offers")),
            "summary": str(data.get("summary", ""))[:400]}


# ---------- Provedor barato: Google Shopping via Serper (sem LLM) ----------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", _norm(s)) if len(t) > 1}


def parse_brl(txt):
    s = re.sub(r"[^\d,.]", "", str(txt or ""))
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def search_serper(product: dict) -> dict:
    body = json.dumps({"q": product["name"], "gl": "br", "hl": "pt-br", "num": 40}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/shopping", data=body, method="POST",
        headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)

    want = _tokens(product["name"])
    fallback = "https://www.google.com/search?tbm=shop&hl=pt-BR&gl=br&q=" + urllib.parse.quote(product["name"])
    cands = []
    for it in data.get("shopping", []):
        price, title = parse_brl(it.get("price")), str(it.get("title", ""))
        if not price or not title:
            continue
        if want and len(want & _tokens(title)) / len(want) < 0.6:  # título precisa bater com a busca
            continue
        used = re.search(r"\b(usad[oa]|seminov[oa]|recondicionad[oa]|open box)\b", _norm(title))
        if used:  # só produtos novos
            continue
        cands.append({"store": it.get("source", ""), "title": title, "price": price,
                      "url": it.get("link") or fallback,
                      "condition": "novo",
                      "shipping": it.get("delivery", ""), "note": ""})
    if len(cands) >= 4:  # descarta acessórios/anúncios muito abaixo do normal
        med = statistics.median(c["price"] for c in cands)
        cands = [c for c in cands if c["price"] >= 0.5 * med]
    cheapest = {}
    for c in sorted(cands, key=lambda c: c["price"]):
        cheapest.setdefault(c["store"], c)
    offers = clean_offers(list(cheapest.values())[:5])
    if offers:
        med = statistics.median(c["price"] for c in cands)
        summary = f"{len(cands)} anúncios no Google Shopping; preço mediano R$ {med:.2f}".replace(".", ",", 1)
    else:
        summary = "Nenhum anúncio relevante no Google Shopping."
    return {"offers": offers, "summary": summary}


def provider() -> str:
    p = os.environ.get("PROVIDER", "").lower()
    return p or ("serper" if os.environ.get("SERPER_API_KEY") else "claude")


def search(product: dict) -> dict:
    if provider() == "serper":
        return search_serper(product)
    import anthropic  # só necessário no modo Claude
    return search_claude(anthropic.Anthropic(), product)


def run_single(query: str, rid: str) -> int:
    """Pesquisa avulsa (aba Pesquisar do site): grava data/search.json."""
    query = query.strip()[:200]
    out = {"id": rid, "query": query, "date": dt.date.today().isoformat()}
    try:
        res = search({"name": query,
                              "notes": "Encontre o menor preço atual deste produto."})
        out.update(status="ok", offers=res["offers"], summary=res["summary"])
    except Exception as e:
        print(f"erro: {e}", file=sys.stderr)
        out.update(status="error", error=str(e)[:200], offers=[], summary="")
    DEALS_FILE.parent.mkdir(exist_ok=True)
    (DEALS_FILE.parent / "search.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--query":
        return run_single(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    deals = {}
    if DEALS_FILE.exists():
        deals = json.loads(DEALS_FILE.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    cutoff = (dt.date.today() - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    failures = 0

    for p in products:
        pid = p["id"]
        entry = deals.get(pid, {"history": []})
        print(f"→ {p['name']}", flush=True)
        try:
            result = search(p)
        except Exception as e:  # um produto com erro não derruba os demais
            failures += 1
            print(f"  erro: {e}", file=sys.stderr)
            entry["error"] = str(e)[:200]
            deals[pid] = entry
            continue
        entry.pop("error", None)
        entry.update(updated=today, offers=result["offers"], summary=result["summary"])
        if result["offers"]:
            hist = [h for h in entry.get("history", []) if h["d"] != today and h["d"] >= cutoff]
            hist.append({"d": today, "p": result["offers"][0]["price"]})
            entry["history"] = hist
        deals[pid] = entry

    # remove produtos que saíram da lista
    deals = {k: v for k, v in deals.items() if k in {p["id"] for p in products}}
    DEALS_FILE.parent.mkdir(exist_ok=True)
    DEALS_FILE.write_text(json.dumps(deals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Pronto: {len(products) - failures}/{len(products)} produtos atualizados.")
    return 1 if failures == len(products) and products else 0


if __name__ == "__main__":
    sys.exit(main())
