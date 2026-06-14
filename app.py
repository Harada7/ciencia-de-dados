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
from urllib.parse import quote_plus

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
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2.5"))
POST_LIMIT_PER_QUERY = int(os.getenv("POST_LIMIT_PER_QUERY", "10"))
COMMENT_LIMIT_PER_POST = int(os.getenv("COMMENT_LIMIT_PER_POST", "30"))
MAX_COMMENT_POSTS_PER_CYCLE = int(os.getenv("MAX_COMMENT_POSTS_PER_CYCLE", "12"))
MAX_QUERIES_PER_CYCLE = int(os.getenv("MAX_QUERIES_PER_CYCLE", "12"))

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
def reddit_get_json(url: str, retries: int = 4) -> Optional[Any]:
    for attempt in range(retries):
        # Delay + jitter para reduzir bloqueios 429.
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0.2, 1.2))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 10
                print(f"[WAIT] 429 recebido. Aguardando {wait}s antes de tentar novamente.")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"[WARN] Falha HTTP: {exc}")
            time.sleep((attempt + 1) * 3)
        except ValueError as exc:
            print(f"[WARN] Resposta não-JSON: {exc}")
            return None
    return None

# =========================
# Coleta Reddit público .json
# =========================
def reddit_url(path: str) -> str:
    return f"https://www.reddit.com{path}"


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

    if not cryptos_found or not people_found:
        return 0

    sentiment = analyzer.polarity_scores(text_content)["compound"]
    created_iso = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()
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


def process_post(post: Dict[str, Any], allow_comments: bool) -> Tuple[int, bool]:
    post_id = post.get("id")
    if not post_id:
        return 0, False

    post_key = f"post_{post_id}"
    already_seen = is_seen(post_key)
    if not already_seen:
        mark_seen(post_key)

    title = post.get("title") or ""
    body = post.get("selftext") or ""
    post_text = f"{title}\n{body}".strip()
    reddit_score = int(post.get("score") or 0)
    num_comments = int(post.get("num_comments") or 0)

    saved = 0
    if not already_seen:
        saved += analyze_and_store_item(
            source_type="post",
            base_reddit_id=post_id,
            subreddit=post.get("subreddit"),
            author=post.get("author"),
            permalink=post.get("permalink"),
            created_utc=post.get("created_utc", time.time()),
            text_content=post_text,
            reddit_score=reddit_score,
            num_comments=num_comments,
        )

    fetched_comments = False
    if allow_comments and should_fetch_comments(post_text, reddit_score, num_comments):
        saved += collect_comments_for_post(post)
        fetched_comments = True

    return saved, fetched_comments


def fetch_search_posts(query: str) -> List[Dict[str, Any]]:
    encoded = quote_plus(query)
    url = reddit_url(f"/search.json?q={encoded}&sort=new&t=week&limit={POST_LIMIT_PER_QUERY}&raw_json=1")
    payload = reddit_get_json(url)
    return extract_posts_from_listing(payload) if payload else []


def fetch_subreddit_posts(subreddit: str) -> List[Dict[str, Any]]:
    url = reddit_url(f"/r/{subreddit}/new.json?limit={max(3, POST_LIMIT_PER_QUERY // 2)}&raw_json=1")
    payload = reddit_get_json(url)
    return extract_posts_from_listing(payload) if payload else []


def collect_cycle() -> Dict[str, int]:
    stats = {
        "queries_processed": 0,
        "subreddits_processed": 0,
        "posts_seen": 0,
        "comment_posts_fetched": 0,
        "matches_saved": 0,
    }

    comment_budget = MAX_COMMENT_POSTS_PER_CYCLE

    # 1) Busca principal por queries direcionadas.
    for query in SEARCH_QUERIES[:MAX_QUERIES_PER_CYCLE]:
        posts = fetch_search_posts(query)
        stats["queries_processed"] += 1
        for post in posts:
            stats["posts_seen"] += 1
            allow_comments = comment_budget > 0
            saved, fetched_comments = process_post(post, allow_comments=allow_comments)
            stats["matches_saved"] += saved
            if fetched_comments:
                comment_budget -= 1
                stats["comment_posts_fetched"] += 1

    # 2) Complemento por subreddits, com baixa agressividade.
    for subreddit in SUBREDDITS:
        posts = fetch_subreddit_posts(subreddit)
        stats["subreddits_processed"] += 1
        for post in posts:
            stats["posts_seen"] += 1
            allow_comments = comment_budget > 0
            saved, fetched_comments = process_post(post, allow_comments=allow_comments)
            stats["matches_saved"] += saved
            if fetched_comments:
                comment_budget -= 1
                stats["comment_posts_fetched"] += 1

    return stats


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


@app.post("/collect")
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
