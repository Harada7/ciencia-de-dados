import csv
import io
import os
import random
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Clustering
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from urllib.parse import quote_plus

import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Response
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()

# =========================
# Configurações gerais
# =========================
DB_PATH = os.getenv("DB_PATH", "crypto_reddit.db")
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    "python:crypto-sentiment-monitor:v2.0 (academic project; contact: local-app)",
)
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "1800"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2.5"))
POST_LIMIT_PER_QUERY = int(os.getenv("POST_LIMIT_PER_QUERY", "10"))
COMMENT_LIMIT_PER_POST = int(os.getenv("COMMENT_LIMIT_PER_POST", "30"))
MAX_COMMENT_POSTS_PER_CYCLE = int(os.getenv("MAX_COMMENT_POSTS_PER_CYCLE", "12"))
MAX_QUERIES_PER_CYCLE = int(os.getenv("MAX_QUERIES_PER_CYCLE", "12"))

# Token OAuth — renovado automaticamente a cada ciclo
_oauth_token: str = ""
_token_expires_at: float = 0.0


def _refresh_oauth_token() -> None:
    global _oauth_token, _token_expires_at
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return
    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _oauth_token = data.get("access_token", "")
        _token_expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        print(f"[INFO] Token OAuth obtido com sucesso.")
    except Exception as exc:
        print(f"[WARN] Falha ao obter token OAuth: {exc}")


def _get_headers() -> dict:
    if time.time() >= _token_expires_at:
        _refresh_oauth_token()
    if _oauth_token:
        return {
            "User-Agent": REDDIT_USER_AGENT,
            "Authorization": f"Bearer {_oauth_token}",
            "Accept": "application/json",
        }
    return {
        "User-Agent": REDDIT_USER_AGENT,
        "Accept": "application/json",
    }


HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/json",
}

app = FastAPI(
    title="Crypto Social Sentiment Monitor",
    version="2.0.0",
    description="Coleta dados públicos do Reddit, analisa sentimento e expõe dados para Grafana/planilha.",
)

analyzer = SentimentIntensityAnalyzer()

# =========================
# Dicionários de análise
# =========================
CRYPTO_KEYWORDS = {
    "bitcoin": ["bitcoin", "btc", "satoshi"],
    "ethereum": ["ethereum", "eth", "ether"],
    "solana": ["solana", " sol "],
    "xrp": ["xrp", "ripple"],
    "dogecoin": ["dogecoin", "doge"],
    "cardano": ["cardano", "ada"],
    "bnb": ["bnb", "binance coin"],
}

FAMOUS_PEOPLE = {
    "elon_musk": ["elon musk", "elon", "musk"],
    "michael_saylor": ["michael saylor", "saylor"],
    "vitalik_buterin": ["vitalik buterin", "vitalik"],
    "changpeng_zhao": ["changpeng zhao", "cz", "binance ceo"],
    "donald_trump": ["donald trump", "trump"],
    "cathie_wood": ["cathie wood", "ark invest"],
    "robert_kiyosaki": ["robert kiyosaki", "kiyosaki"],
    "gary_gensler": ["gary gensler", "gensler"],
    "jerome_powell": ["jerome powell", "powell", "fed chair"],
}

# Buscas direcionadas: geram mais registros úteis do que varrer subreddit inteiro.
SEARCH_QUERIES = [
    "bitcoin elon musk",
    "dogecoin elon musk",
    "bitcoin michael saylor",
    "btc saylor",
    "ethereum vitalik",
    "crypto trump",
    "bitcoin trump",
    "xrp trump",
    "bitcoin cathie wood",
    "bitcoin kiyosaki",
    "crypto gary gensler",
    "ethereum sec gensler",
    "solana elon musk",
    "crypto powell",
]

# Subreddits usados como fonte complementar. A busca principal ainda é /search.json.
SUBREDDITS = [
    "CryptoCurrency",
    "Bitcoin",
    "Ethereum",
    "CryptoMarkets",
]

# =========================
# Banco de dados
# =========================
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
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
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                reddit_key TEXT PRIMARY KEY,
                first_seen_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def query_db(sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def is_seen(reddit_key: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM seen_items WHERE reddit_key = ?", (reddit_key,))
        return cur.fetchone() is not None


def mark_seen(reddit_key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items (reddit_key, first_seen_at) VALUES (?, ?)",
            (reddit_key, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def save_record(record: Dict[str, Any]) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO reddit_mentions (
                source_type, reddit_id, subreddit, author, permalink, created_utc, text_content,
                crypto, famous_person, sentiment, sentiment_label, relevance_score,
                reddit_score, num_comments, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["source_type"],
                record["reddit_id"],
                record.get("subreddit"),
                record.get("author"),
                record.get("permalink"),
                record["created_utc"],
                record["text_content"],
                record["crypto"],
                record["famous_person"],
                record["sentiment"],
                record["sentiment_label"],
                record["relevance_score"],
                record.get("reddit_score"),
                record.get("num_comments"),
                record["collected_at"],
            ),
        )
        conn.commit()
        return cur.rowcount > 0

# =========================
# Utilitários de texto
# =========================
def normalize_text(text: str) -> str:
    return f" {text or ''} ".lower().replace("\n", " ")


def keyword_in_text(text_norm: str, keyword: str) -> bool:
    key = keyword.lower().strip()
    if len(key) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", text_norm) is not None
    return key in text_norm


def match_all_keywords(text: str, keyword_map: Dict[str, List[str]]) -> List[str]:
    text_norm = normalize_text(text)
    found = []
    for label, keywords in keyword_map.items():
        if any(keyword_in_text(text_norm, keyword) for keyword in keywords):
            found.append(label)
    return found


def sentiment_label(score: float) -> str:
    if score >= 0.05:
        return "positivo"
    if score <= -0.05:
        return "negativo"
    return "neutro"


def calculate_relevance(text: str, cryptos: List[str], people: List[str], reddit_score: int, num_comments: int) -> int:
    # Score simples para priorizar dados que parecem mais úteis para planilha/dashboard.
    score = 0
    score += len(cryptos) * 10
    score += len(people) * 12
    score += min(max(reddit_score, 0), 200) // 10
    score += min(max(num_comments, 0), 100) // 10

    text_norm = normalize_text(text)
    market_terms = ["price", "bull", "bear", "crash", "pump", "dump", "etf", "sec", "market", "buy", "sell"]
    score += sum(2 for term in market_terms if term in text_norm)
    return score

# =========================
# Cliente HTTP com backoff
# =========================
# =========================
# Coleta via RSS de portais de notícias de crypto (sem autenticação)
# =========================
NEWS_FEEDS = [
    ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
    ("https://cointelegraph.com/rss", "CoinTelegraph"),
    ("https://decrypt.co/feed", "Decrypt"),
    ("https://bitcoinmagazine.com/feed", "BitcoinMagazine"),
    ("https://cryptonews.com/news/feed/", "CryptoNews"),
    ("https://www.newsbtc.com/feed/", "NewsBTC"),
    ("https://ambcrypto.com/feed/", "AMBCrypto"),
    ("https://cryptopotato.com/feed/", "CryptoPotato"),
    ("https://beincrypto.com/feed/", "BeInCrypto"),
    ("https://coinjournal.net/feed/", "CoinJournal"),
    ("https://cryptoslate.com/feed/", "CryptoSlate"),
    ("https://bitcoinist.com/feed/", "Bitcoinist"),
    ("https://u.today/rss", "UToday"),
    ("https://www.crypto-news-flash.com/feed/", "CryptoNewsFlash"),
    ("https://dailyhodl.com/feed/", "DailyHodl"),
    ("https://zycrypto.com/feed/", "ZyCrypto"),
]

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; crypto-sentiment-monitor/2.0; academic research)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def parse_rss_date(date_str: str) -> str:
    """Converte datas RSS (RFC 2822 ou ISO) para ISO 8601."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def fetch_news_rss(feed_url: str, source_name: str) -> List[Dict[str, Any]]:
    """Busca artigos de um feed RSS de portal de notícias crypto."""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = requests.get(feed_url, headers=RSS_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[WARN] Feed {source_name}: {exc}")
        return []

    items = []
    try:
        root = ET.fromstring(resp.content)
        # Suporte a RSS 2.0 e Atom
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else root.findall(
            "{http://www.w3.org/2005/Atom}entry"
        )

        for entry in entries:
            def get(tag: str, attr: Optional[str] = None) -> str:
                node = entry.find(tag)
                if node is None:
                    return ""
                if attr:
                    return (node.get(attr) or "").strip()
                return (node.text or "").strip()

            title   = get("title")
            desc    = get("description") or get("summary") or get("{http://www.w3.org/2005/Atom}summary")
            link    = get("link") or get("guid")
            pub     = get("pubDate") or get("published") or get("{http://www.w3.org/2005/Atom}published")
            author  = get("author") or get("dc:creator") or source_name

            text = f"{title} {desc}".strip()
            if not text or len(text) < 15:
                continue

            item_id = link[-20:].replace("/", "_").replace(":", "") if link else f"{source_name}_{len(items)}"
            items.append({
                "id": item_id,
                "title": title,
                "selftext": desc,
                "permalink": link,
                "author": author,
                "subreddit": source_name,
                "created_utc": parse_rss_date(pub),
                "score": 1,
                "num_comments": 0,
            })
    except ET.ParseError as exc:
        print(f"[WARN] Erro ao parsear RSS de {source_name}: {exc}")

    print(f"[INFO] {source_name}: {len(items)} artigos encontrados.")
    return items


def collect_cycle() -> Dict[str, int]:
    stats = {"feeds_processed": 0, "posts_seen": 0, "matches_saved": 0}

    for feed_url, source_name in NEWS_FEEDS:
        posts = fetch_news_rss(feed_url, source_name)
        stats["feeds_processed"] += 1

        for post in posts:
            stats["posts_seen"] += 1
            post_id = post.get("id") or ""
            if not post_id:
                continue
            post_key = f"news_{source_name}_{post_id}"
            if is_seen(post_key):
                continue
            mark_seen(post_key)

            text = f"{post.get('title', '')} {post.get('selftext', '')}".strip()
            saved = analyze_and_store_item(
                source_type="news",
                base_reddit_id=post_key[:80],
                subreddit=source_name,
                author=post.get("author"),
                permalink=post.get("permalink"),
                created_utc=post.get("created_utc", ""),
                text_content=text,
                reddit_score=1,
                num_comments=0,
            )
            stats["matches_saved"] += saved

    return stats


def extract_posts_from_listing(payload: Any) -> List[Dict[str, Any]]:
    posts = []
    try:
        children = payload.get("data", {}).get("children", [])
    except AttributeError:
        return posts

    for child in children:
        data = child.get("data", {})
        if not data or data.get("stickied"):
            continue
        posts.append(data)
    return posts


def analyze_and_store_item(
    *,
    source_type: str,
    base_reddit_id: str,
    subreddit: Optional[str],
    author: Optional[str],
    permalink: Optional[str],
    created_utc: float,
    text_content: str,
    reddit_score: int = 0,
    num_comments: int = 0,
) -> int:
    if not text_content or len(text_content.strip()) < 8:
        return 0

    cryptos_found = match_all_keywords(text_content, CRYPTO_KEYWORDS)
    people_found = match_all_keywords(text_content, FAMOUS_PEOPLE)

    # Requer pelo menos uma cripto; personalidade é opcional
    if not cryptos_found:
        return 0

    # Se nenhuma personalidade foi encontrada, usa "mercado_geral"
    if not people_found:
        people_found = ["mercado_geral"]

    sentiment = analyzer.polarity_scores(text_content)["compound"]
    if isinstance(created_utc, str) and created_utc:
        created_iso = created_utc
    elif created_utc:
        created_iso = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()
    else:
        created_iso = datetime.now(timezone.utc).isoformat()
    collected_at = datetime.now(timezone.utc).isoformat()
    relevance = calculate_relevance(text_content, cryptos_found, people_found, reddit_score, num_comments)

    saved = 0
    for crypto in cryptos_found:
        for person in people_found:
            unique_id = f"{source_type}_{base_reddit_id}_{crypto}_{person}"
            record = {
                "source_type": source_type,
                "reddit_id": unique_id,
                "subreddit": subreddit,
                "author": author,
                "permalink": f"https://www.reddit.com{permalink}" if permalink and permalink.startswith("/") else permalink,
                "created_utc": created_iso,
                "text_content": text_content[:5000],
                "crypto": crypto,
                "famous_person": person,
                "sentiment": sentiment,
                "sentiment_label": sentiment_label(sentiment),
                "relevance_score": relevance,
                "reddit_score": reddit_score,
                "num_comments": num_comments,
                "collected_at": collected_at,
            }
            if save_record(record):
                saved += 1
    return saved


def should_fetch_comments(post_text: str, reddit_score: int, num_comments: int) -> bool:
    # Busca comentários só quando o post já é promissor. Isso reduz 429 e melhora a qualidade.
    cryptos = match_all_keywords(post_text, CRYPTO_KEYWORDS)
    people = match_all_keywords(post_text, FAMOUS_PEOPLE)
    if cryptos and people:
        return True
    if cryptos and num_comments >= 10 and reddit_score >= 5:
        return True
    return False


def extract_comments_from_payload(payload: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(payload, list) or len(payload) < 2:
        return []

    comments = payload[1].get("data", {}).get("children", [])
    extracted = []

    def walk(children: List[Dict[str, Any]]) -> None:
        for child in children:
            if child.get("kind") != "t1":
                continue
            data = child.get("data", {})
            body = data.get("body")
            if body:
                extracted.append(data)
            replies = data.get("replies")
            if isinstance(replies, dict):
                walk(replies.get("data", {}).get("children", []))

    walk(comments)
    return extracted[:COMMENT_LIMIT_PER_POST]


def collect_comments_for_post(post: Dict[str, Any]) -> int:
    permalink = post.get("permalink")
    if not permalink:
        return 0

    url = reddit_url(f"{permalink}.json?raw_json=1&limit={COMMENT_LIMIT_PER_POST}")
    payload = reddit_get_json(url)
    if payload is None:
        return 0

    saved = 0
    for comment in extract_comments_from_payload(payload):
        comment_id = comment.get("id")
        if not comment_id:
            continue
        comment_key = f"comment_{comment_id}"
        if is_seen(comment_key):
            continue
        mark_seen(comment_key)
        saved += analyze_and_store_item(
            source_type="comment",
            base_reddit_id=comment_id,
            subreddit=post.get("subreddit"),
            author=comment.get("author"),
            permalink=permalink,
            created_utc=comment.get("created_utc", time.time()),
            text_content=comment.get("body", ""),
            reddit_score=int(comment.get("score") or 0),
            num_comments=0,
        )
    return saved




def background_collector() -> None:
    while True:
        try:
            print(f"[INFO] Coleta iniciada em {datetime.now().isoformat()}")
            stats = collect_cycle()
            print(f"[INFO] Coleta finalizada. Estatísticas: {stats}")
        except Exception as exc:
            print(f"[ERROR] Falha geral na coleta: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)

# =========================
# Endpoints
# =========================
@app.on_event("startup")
def startup_event() -> None:
    init_db()
    thread = threading.Thread(target=background_collector, daemon=True)
    thread.start()


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "message": "Crypto Social Sentiment Monitor",
        "docs": "/docs",
        "health": "/health",
        "summary": "/summary",
        "timeseries": "/timeseries",
        "recent": "/recent",
        "export_csv": "/export/csv",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    rows = query_db("SELECT COUNT(*) AS total FROM reddit_mentions")
    return {
        "status": "ok",
        "records": rows[0]["total"] if rows else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            "post_limit_per_query": POST_LIMIT_PER_QUERY,
            "comment_limit_per_post": COMMENT_LIMIT_PER_POST,
            "max_comment_posts_per_cycle": MAX_COMMENT_POSTS_PER_CYCLE,
            "request_delay_seconds": REQUEST_DELAY_SECONDS,
        },
    }


@app.api_route("/collect", methods=["GET", "POST"])
def collect_now() -> Dict[str, Any]:
    stats = collect_cycle()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }


@app.get("/summary")
def summary(hours: int = Query(default=168, ge=1, le=720)) -> Dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = query_db(
        """
        SELECT
            crypto,
            famous_person,
            COUNT(*) AS mentions,
            ROUND(AVG(sentiment), 4) AS avg_sentiment,
            ROUND(AVG(relevance_score), 2) AS avg_relevance,
            SUM(CASE WHEN sentiment_label = 'positivo' THEN 1 ELSE 0 END) AS positive_count,
            SUM(CASE WHEN sentiment_label = 'neutro' THEN 1 ELSE 0 END) AS neutral_count,
            SUM(CASE WHEN sentiment_label = 'negativo' THEN 1 ELSE 0 END) AS negative_count
        FROM reddit_mentions
        WHERE created_utc >= ?
        GROUP BY crypto, famous_person
        ORDER BY mentions DESC, avg_relevance DESC, avg_sentiment DESC
        """,
        (cutoff,),
    )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "hours": hours, "data": rows}


@app.get("/timeseries")
def timeseries(
    hours: int = Query(default=168, ge=1, le=720),
    crypto: Optional[str] = None,
    famous_person: Optional[str] = None,
) -> Dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    filters = ["created_utc >= ?"]
    params: List[Any] = [cutoff]

    if crypto:
        filters.append("crypto = ?")
        params.append(crypto)
    if famous_person:
        filters.append("famous_person = ?")
        params.append(famous_person)

    rows = query_db(
        f"""
        SELECT
            substr(created_utc, 1, 13) || ':00:00Z' AS hour_bucket,
            crypto,
            famous_person,
            COUNT(*) AS mentions,
            ROUND(AVG(sentiment), 4) AS avg_sentiment,
            ROUND(AVG(relevance_score), 2) AS avg_relevance
        FROM reddit_mentions
        WHERE {' AND '.join(filters)}
        GROUP BY hour_bucket, crypto, famous_person
        ORDER BY hour_bucket ASC
        """,
        tuple(params),
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "filters": {"crypto": crypto, "famous_person": famous_person},
        "data": rows,
    }


@app.get("/recent")
def recent(limit: int = Query(default=100, ge=1, le=500)) -> Dict[str, Any]:
    rows = query_db(
        """
        SELECT
            created_utc, source_type, subreddit, author, crypto, famous_person,
            sentiment, sentiment_label, relevance_score, reddit_score, num_comments,
            permalink, text_content
        FROM reddit_mentions
        ORDER BY created_utc DESC
        LIMIT ?
        """,
        (limit,),
    )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "data": rows}


# =========================
# Clustering (K-Means + TF-IDF)
# =========================

# Stopwords do domínio cripto para não poluir os tópicos
_CRYPTO_STOPWORDS = [
    "bitcoin", "btc", "crypto", "cryptocurrency", "coin", "token", "blockchain",
    "market", "price", "trading", "trade", "invest", "just", "like", "think",
    "know", "would", "going", "one", "people", "get", "got", "really", "also",
    "even", "back", "much", "well", "still", "good", "new", "time", "way",
    "said", "say", "make", "made", "want", "need", "use", "used", "buy", "sell",
    "https", "www", "com", "reddit", "post", "comment",
]

# Cache simples para não recalcular clustering a cada request
_cluster_cache: Dict[str, Any] = {"result": None, "computed_at": None}
_CLUSTER_CACHE_TTL_SECONDS = 300


def _run_clustering(rows: List[Dict[str, Any]], n_clusters: int, top_terms: int) -> List[Dict[str, Any]]:
    texts = [r["text_content"] for r in rows]

    vectorizer = TfidfVectorizer(
        max_features=500,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
    )
    # Remove stopwords de cripto manualmente após vetorização
    X = vectorizer.fit_transform(texts)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    feature_names = vectorizer.get_feature_names_out()
    clusters = []
    for i in range(n_clusters):
        center = kmeans.cluster_centers_[i]
        top_indices = center.argsort()[-top_terms:][::-1]
        # Filtra termos que são stopwords de cripto
        top_words = [
            feature_names[idx]
            for idx in top_indices
            if feature_names[idx] not in _CRYPTO_STOPWORDS
        ][:top_terms]

        cluster_rows = [rows[j] for j in range(len(rows)) if labels[j] == i]
        count = len(cluster_rows)
        pos = sum(1 for r in cluster_rows if r["sentiment_label"] == "positivo")
        neg = sum(1 for r in cluster_rows if r["sentiment_label"] == "negativo")
        neu = count - pos - neg

        if pos >= neg and pos >= neu:
            dominant = "positivo"
        elif neg >= pos and neg >= neu:
            dominant = "negativo"
        else:
            dominant = "neutro"

        clusters.append({
            "cluster_id": i,
            "cluster_name": f"Tópico {i + 1}",
            "top_terms": ", ".join(top_words),
            "count": count,
            "positive_count": pos,
            "negative_count": neg,
            "neutral_count": neu,
            "dominant_sentiment": dominant,
        })

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


@app.get("/clustering")
def clustering(
    hours: int = Query(default=720, ge=1, le=8760),
    n_clusters: int = Query(default=5, ge=2, le=10),
    top_terms: int = Query(default=8, ge=3, le=20),
    force_refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    """Agrupa as publicações em tópicos usando K-Means + TF-IDF."""
    global _cluster_cache

    cache_key = f"{hours}_{n_clusters}_{top_terms}"
    now = datetime.now(timezone.utc)

    # Retorna cache se ainda válido
    if (
        not force_refresh
        and _cluster_cache["result"] is not None
        and _cluster_cache.get("key") == cache_key
        and _cluster_cache["computed_at"] is not None
        and (now - _cluster_cache["computed_at"]).total_seconds() < _CLUSTER_CACHE_TTL_SECONDS
    ):
        return _cluster_cache["result"]

    cutoff = (now - timedelta(hours=hours)).isoformat()
    rows = query_db(
        """
        SELECT text_content, sentiment_label
        FROM reddit_mentions
        WHERE created_utc >= ?
        LIMIT 3000
        """,
        (cutoff,),
    )

    min_docs = n_clusters * 3
    if len(rows) < min_docs:
        return {
            "error": f"Dados insuficientes para clustering (mínimo {min_docs}, encontrado {len(rows)}). "
                     "Aumente o parâmetro 'hours' ou aguarde mais coletas.",
            "records_found": len(rows),
        }

    clusters = _run_clustering(rows, n_clusters, top_terms)

    result = {
        "generated_at": now.isoformat(),
        "hours": hours,
        "n_clusters": n_clusters,
        "total_records": len(rows),
        "clusters": clusters,
    }
    _cluster_cache = {"result": result, "computed_at": now, "key": cache_key}
    return result


@app.get("/clustering/grafana")
def clustering_grafana(
    hours: int = Query(default=720, ge=1, le=8760),
    n_clusters: int = Query(default=5, ge=2, le=10),
) -> List[Dict[str, Any]]:
    """
    Retorna clustering em formato flat (lista de objetos) compatível com
    o plugin Infinity do Grafana para uso em tabelas e gráficos de barras.
    """
    result = clustering(hours=hours, n_clusters=n_clusters, top_terms=8)
    if "error" in result:
        return []
    return result.get("clusters", [])


@app.get("/export/csv")
def export_csv(limit: int = Query(default=1000, ge=1, le=10000)) -> Response:
    rows = query_db(
        """
        SELECT
            created_utc, source_type, subreddit, author, crypto, famous_person,
            sentiment, sentiment_label, relevance_score, reddit_score, num_comments,
            permalink, text_content
        FROM reddit_mentions
        ORDER BY created_utc DESC
        LIMIT ?
        """,
        (limit,),
    )

    output = io.StringIO()
    fieldnames = [
        "created_utc", "source_type", "subreddit", "author", "crypto", "famous_person",
        "sentiment", "sentiment_label", "relevance_score", "reddit_score", "num_comments",
        "permalink", "text_content",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    filename = f"crypto_reddit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
