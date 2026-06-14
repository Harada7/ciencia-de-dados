"""
Importa notícias históricas do NewsAPI para o banco de dados.
Roda uma vez: py import_newsapi.py
"""
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

API_KEY  = os.getenv("NEWSAPI_KEY", "6fc0cb597f3a428897ed1434ad0a887d")
DB_PATH  = os.getenv("DB_PATH", "crypto_reddit.db")
BASE_URL = "https://newsapi.org/v2/everything"

analyzer = SentimentIntensityAnalyzer()

CRYPTO_KEYWORDS = {
    "bitcoin":  ["bitcoin", "btc", "satoshi"],
    "ethereum": ["ethereum", "eth", "ether"],
    "solana":   ["solana", "sol"],
    "xrp":      ["xrp", "ripple"],
    "dogecoin": ["dogecoin", "doge"],
    "cardano":  ["cardano", "ada"],
    "bnb":      ["bnb", "binance coin"],
}

FAMOUS_PEOPLE = {
    "elon_musk":        ["elon musk", "elon", "musk"],
    "michael_saylor":   ["michael saylor", "saylor"],
    "vitalik_buterin":  ["vitalik buterin", "vitalik"],
    "donald_trump":     ["donald trump", "trump"],
    "cathie_wood":      ["cathie wood", "ark invest"],
    "robert_kiyosaki":  ["robert kiyosaki", "kiyosaki"],
    "gary_gensler":     ["gary gensler", "gensler", "sec chair"],
    "jerome_powell":    ["jerome powell", "powell", "federal reserve"],
    "changpeng_zhao":   ["changpeng zhao", "cz binance"],
}

# Queries para buscar — variadas para cobrir mais artigos históricos
QUERIES = [
    "bitcoin price",
    "ethereum crypto",
    "bitcoin elon musk",
    "bitcoin michael saylor",
    "crypto trump",
    "dogecoin elon",
    "ethereum vitalik",
    "XRP ripple SEC",
    "solana crypto",
    "bitcoin ETF",
    "crypto market",
    "bitcoin cathie wood",
    "bitcoin kiyosaki",
    "crypto powell fed",
    "bitcoin regulation",
    "cryptocurrency investing",
]


def normalize(text: str) -> str:
    return f" {text or ''} ".lower()


def match_keywords(text: str, kw_map: dict) -> list:
    norm = normalize(text)
    found = []
    for label, keywords in kw_map.items():
        for kw in keywords:
            kw = kw.lower().strip()
            pattern = rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])" if len(kw) <= 4 else kw
            if re.search(pattern, norm) if len(kw) <= 4 else kw in norm:
                found.append(label)
                break
    return found


def sentiment_label(score: float) -> str:
    if score >= 0.05:  return "positivo"
    if score <= -0.05: return "negativo"
    return "neutro"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reddit_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            reddit_id TEXT NOT NULL UNIQUE,
            subreddit TEXT,
            author TEXT,
            permalink TEXT,
            created_utc TEXT NOT NULL,
            text_content TEXT NOT NULL,
            crypto TEXT NOT NULL,
            famous_person TEXT NOT NULL,
            sentiment REAL NOT NULL,
            sentiment_label TEXT NOT NULL,
            relevance_score INTEGER NOT NULL,
            reddit_score INTEGER,
            num_comments INTEGER,
            collected_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_items (
            reddit_key TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def is_seen(conn: sqlite3.Connection, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM seen_items WHERE reddit_key = ?", (key,)
    ).fetchone() is not None


def fetch_articles(query: str, page: int = 1) -> list:
    params = {
        "q":        query,
        "apiKey":   API_KEY,
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": 100,
        "page":     page,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != "ok":
            print(f"  [WARN] {data.get('message', 'Erro desconhecido')}")
            return []
        return data.get("articles", [])
    except Exception as exc:
        print(f"  [WARN] Erro ao buscar '{query}': {exc}")
        return []


def import_all():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    total_saved = 0
    total_seen  = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for query in QUERIES:
        print(f"\n🔍 Buscando: '{query}'")
        for page in range(1, 4):  # até 3 páginas = 300 artigos por query
            articles = fetch_articles(query, page)
            if not articles:
                break

            saved_this_page = 0
            for art in articles:
                title   = (art.get("title") or "").strip()
                desc    = (art.get("description") or "").strip()
                content = (art.get("content") or "").strip()
                source  = art.get("source", {}).get("name", "NewsAPI")
                author  = art.get("author") or source
                url     = art.get("url") or ""
                pub     = art.get("publishedAt") or now_iso

                text = f"{title} {desc} {content}".strip()
                if not text or len(text) < 20:
                    continue

                # Deduplicação por URL
                key = f"newsapi_{url[-40:].replace('/', '_')}"
                total_seen += 1
                if is_seen(conn, key):
                    continue

                cryptos = match_keywords(text, CRYPTO_KEYWORDS)
                if not cryptos:
                    conn.execute(
                        "INSERT OR IGNORE INTO seen_items VALUES (?, ?)",
                        (key, now_iso)
                    )
                    continue

                people = match_keywords(text, FAMOUS_PEOPLE) or ["mercado_geral"]
                score  = analyzer.polarity_scores(text)["compound"]
                label  = sentiment_label(score)

                # Converte data da notícia
                try:
                    pub_iso = datetime.strptime(
                        pub, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc).isoformat()
                except Exception:
                    pub_iso = now_iso

                relevance = len(cryptos) * 10 + len(people) * 8

                for crypto in cryptos:
                    for person in people:
                        rec_key = f"newsapi_{url[-30:]}_{crypto}_{person}".replace("/","_")
                        try:
                            conn.execute("""
                                INSERT OR IGNORE INTO reddit_mentions
                                (source_type, reddit_id, subreddit, author, permalink,
                                 created_utc, text_content, crypto, famous_person,
                                 sentiment, sentiment_label, relevance_score,
                                 reddit_score, num_comments, collected_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                "news", rec_key, source, author, url,
                                pub_iso, text[:3000], crypto, person,
                                score, label, relevance, 0, 0, now_iso
                            ))
                            if conn.total_changes > 0:
                                saved_this_page += 1
                        except Exception:
                            pass

                conn.execute(
                    "INSERT OR IGNORE INTO seen_items VALUES (?, ?)", (key, now_iso)
                )

            conn.commit()
            total_saved += saved_this_page
            print(f"  Página {page}: {len(articles)} artigos → {saved_this_page} salvos")

            if len(articles) < 100:
                break  # última página
            time.sleep(1)  # respeita rate limit

        time.sleep(0.5)

    conn.close()
    print(f"\n✅ Importação concluída! {total_saved} registros salvos de {total_seen} artigos processados.")


if __name__ == "__main__":
    import_all()
