"""
Popula o banco com dados realistas de posts do Reddit sobre criptomoedas.
Roda uma vez: py seed_data.py
"""
import random
import sqlite3
import os
from datetime import datetime, timedelta, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DB_PATH = os.getenv("DB_PATH", "crypto_reddit.db")
analyzer = SentimentIntensityAnalyzer()

# ── Conteúdo realista de posts ─────────────────────────────────────────────────
POSTS = [
    # Bitcoin + Elon Musk
    ("Bitcoin is mooning again after Elon Musk tweeted about BTC adoption in Tesla payments. The market is going crazy bullish right now!", "bitcoin", "elon_musk", "Bitcoin", 4200, 312),
    ("Elon Musk just dumped all Bitcoin from Tesla balance sheet. BTC price crashing hard. This is insane.", "bitcoin", "elon_musk", "Bitcoin", 8900, 1204),
    ("Do you think Elon Musk manipulates BTC price on purpose? Every tweet pumps or dumps the market.", "bitcoin", "elon_musk", "CryptoCurrency", 1100, 489),
    ("Elon posted a BTC meme on Twitter and price jumped 8% in one hour. Unbelievable influence.", "bitcoin", "elon_musk", "Bitcoin", 3300, 678),
    ("BTC holding strong at 95k despite Elon Musk silence. The market is maturing.", "bitcoin", "elon_musk", "CryptoCurrency", 720, 145),
    ("Elon Musk confirmed SpaceX will accept Bitcoin for satellite subscriptions. Huge bullish signal for BTC.", "bitcoin", "elon_musk", "Bitcoin", 5600, 892),
    ("I'm tired of Elon manipulating Bitcoin. This is not good for retail investors.", "bitcoin", "elon_musk", "CryptoCurrency", 2100, 567),
    ("BTC just broke ATH and Elon Musk is nowhere to be found. Organic pump? Yes please.", "bitcoin", "elon_musk", "Bitcoin", 6400, 1100),

    # Bitcoin + Michael Saylor
    ("Michael Saylor says Bitcoin is the apex predator of monetary assets. MicroStrategy bought another 10k BTC.", "bitcoin", "michael_saylor", "Bitcoin", 3800, 445),
    ("Saylor keeps buying BTC at every dip. MicroStrategy now holds over 400k Bitcoin. Incredible conviction.", "bitcoin", "michael_saylor", "Bitcoin", 2900, 388),
    ("Michael Saylor predicts Bitcoin will reach $1 million by 2030. Is he right or delusional?", "bitcoin", "michael_saylor", "CryptoCurrency", 1500, 712),
    ("MicroStrategy announced another $500M Bitcoin purchase. Saylor is all in on BTC, no doubt.", "bitcoin", "michael_saylor", "Bitcoin", 4100, 534),
    ("Saylor's BTC strategy is paying off massively. MicroStrategy stock up 300% this year.", "bitcoin", "michael_saylor", "Bitcoin", 2200, 298),
    ("Michael Saylor is the biggest Bitcoin bull out there. His thesis is solid: BTC as digital gold.", "bitcoin", "michael_saylor", "Bitcoin", 980, 167),
    ("I disagree with Saylor. Bitcoin is too volatile to be a treasury reserve asset.", "bitcoin", "michael_saylor", "CryptoCurrency", 1300, 423),
    ("MicroStrategy quarterly report shows massive BTC gains. Saylor's bet is paying off.", "bitcoin", "michael_saylor", "Bitcoin", 1750, 289),

    # Bitcoin + Donald Trump
    ("Trump signed the Bitcoin Strategic Reserve executive order today. BTC pumping hard!", "bitcoin", "donald_trump", "Bitcoin", 9200, 1567),
    ("Trump administration is pro-crypto. Bitcoin ETF inflows at record high after election.", "bitcoin", "donald_trump", "Bitcoin", 4500, 723),
    ("Donald Trump promised to make USA the crypto capital of the world. BTC reacting positively.", "bitcoin", "donald_trump", "CryptoCurrency", 3100, 589),
    ("Trump's tariffs causing uncertainty. Bitcoin dropping as risk assets sell off.", "bitcoin", "donald_trump", "Bitcoin", 2800, 445),
    ("Trump appointed pro-Bitcoin SEC chair. This changes everything for crypto regulation.", "bitcoin", "donald_trump", "CryptoCurrency", 5300, 934),
    ("Trump says he will never sell the Bitcoin strategic reserve. Long term bullish signal.", "bitcoin", "donald_trump", "Bitcoin", 3700, 612),
    ("Economic uncertainty from Trump policies pushing investors towards Bitcoin as safe haven.", "bitcoin", "donald_trump", "Bitcoin", 1900, 334),

    # Ethereum + Vitalik
    ("Vitalik Buterin published new roadmap for Ethereum scaling. ETH price up 12% on the news.", "ethereum", "vitalik_buterin", "Ethereum", 2100, 378),
    ("Ethereum staking rewards are incredible right now. Vitalik's PoS transition was the right call.", "ethereum", "vitalik_buterin", "Ethereum", 1400, 245),
    ("Vitalik warns about centralization risks in ETH staking. Valid concern for the ecosystem.", "ethereum", "vitalik_buterin", "CryptoCurrency", 1800, 423),
    ("ETH 2.0 is finally delivering on its promises. Vitalik's vision is coming true.", "ethereum", "vitalik_buterin", "Ethereum", 2500, 512),
    ("Vitalik donated millions in ETH to charity again. Legend.", "ethereum", "vitalik_buterin", "CryptoCurrency", 3200, 891),
    ("Ethereum gas fees still too high despite upgrades. Vitalik needs to fix this.", "ethereum", "vitalik_buterin", "Ethereum", 890, 234),
    ("Vitalik's new paper on cryptographic proofs is mind-blowing. ETH tech is ahead of everyone.", "ethereum", "vitalik_buterin", "Ethereum", 1600, 312),

    # Dogecoin + Elon Musk
    ("Elon Musk changed Twitter logo to Doge meme. DOGE pumping 40% right now!", "dogecoin", "elon_musk", "CryptoCurrency", 12000, 2345),
    ("Dogecoin accepted on Tesla website for merch. Elon delivering on his promises for DOGE.", "dogecoin", "elon_musk", "CryptoCurrency", 8700, 1678),
    ("Elon Musk tweeted just one word: 'Doge' and it pumped 20%. This is ridiculous.", "dogecoin", "elon_musk", "CryptoCurrency", 15000, 3100),
    ("DOGE is a meme coin but Elon keeps giving it legitimacy. Up 60% this month.", "dogecoin", "elon_musk", "CryptoCurrency", 5400, 1234),
    ("Elon keeps pumping Dogecoin. When will retail investors learn not to chase meme coins?", "dogecoin", "elon_musk", "CryptoCurrency", 2100, 567),

    # XRP + Trump / Gensler
    ("XRP pumping massively after SEC drops lawsuit against Ripple. Trump era changing everything.", "xrp", "donald_trump", "CryptoCurrency", 6800, 1123),
    ("Gary Gensler resigned from SEC. XRP up 80% as crypto regulatory pressure eases.", "xrp", "gary_gensler", "CryptoCurrency", 9100, 1890),
    ("Trump's pro-crypto SEC pick is bullish for XRP and all altcoins.", "xrp", "donald_trump", "CryptoCurrency", 3400, 678),
    ("Gensler's war on crypto is finally over. XRP, ETH, SOL all pumping.", "xrp", "gary_gensler", "CryptoCurrency", 4200, 934),

    # Solana + various
    ("Solana TPS hitting new records. ETH killers are real and SOL is leading the charge.", "solana", "vitalik_buterin", "Ethereum", 1900, 412),
    ("Cathie Wood added SOL to ARK Invest portfolio. Big institutional move for Solana.", "solana", "cathie_wood", "CryptoCurrency", 2300, 389),
    ("Solana ecosystem growing faster than any other chain. SOL could flip ETH market cap.", "solana", "elon_musk", "CryptoCurrency", 1700, 278),

    # BTC + Cathie Wood / Kiyosaki
    ("Cathie Wood says Bitcoin will reach $1.5M by 2030. ARK Invest increasing BTC exposure.", "bitcoin", "cathie_wood", "CryptoCurrency", 2800, 445),
    ("Robert Kiyosaki bought more Bitcoin and gold. He says the dollar is dying.", "bitcoin", "robert_kiyosaki", "CryptoCurrency", 1900, 334),
    ("Kiyosaki warns of massive economic crash. Says Bitcoin is the only escape.", "bitcoin", "robert_kiyosaki", "CryptoCurrency", 2400, 512),
    ("Cathie Wood is doubling down on Bitcoin ETF position. ARK leading institutional adoption.", "bitcoin", "cathie_wood", "Bitcoin", 1600, 267),
    ("Kiyosaki's prediction of dollar collapse is extreme but Bitcoin hedge makes sense.", "bitcoin", "robert_kiyosaki", "CryptoCurrency", 1100, 189),

    # Powell / Fed
    ("Jerome Powell hints at rate cuts. Bitcoin and crypto markets surging on the news.", "bitcoin", "jerome_powell", "Bitcoin", 3400, 567),
    ("Fed decision to hold rates pushing investors to alternative assets like Bitcoin.", "bitcoin", "jerome_powell", "CryptoCurrency", 2100, 389),
    ("Powell says crypto regulation needs clarity. Markets waiting for guidance.", "ethereum", "jerome_powell", "CryptoCurrency", 1300, 245),
    ("Rate cuts incoming according to Powell. Bitcoin historically pumps in low rate environment.", "bitcoin", "jerome_powell", "Bitcoin", 2700, 456),

    # Comentários adicionais
    ("Just bought more BTC on this dip. Michael Saylor strategy is the way to go.", "bitcoin", "michael_saylor", "Bitcoin", 430, 89),
    ("Ethereum staking is passive income. Vitalik created something revolutionary.", "ethereum", "vitalik_buterin", "Ethereum", 560, 123),
    ("Can't believe Trump is actually pro-Bitcoin. The world has changed.", "bitcoin", "donald_trump", "Bitcoin", 780, 167),
    ("Elon Musk is either a genius or the biggest manipulator in crypto history.", "bitcoin", "elon_musk", "CryptoCurrency", 1200, 312),
    ("XRP holders finally getting rewarded after years of SEC battle.", "xrp", "gary_gensler", "CryptoCurrency", 890, 201),
    ("Cathie Wood's long-term BTC thesis is the most rational I've heard.", "bitcoin", "cathie_wood", "CryptoCurrency", 670, 145),
    ("Bitcoin is digital gold. Kiyosaki has been saying this for years and he's right.", "bitcoin", "robert_kiyosaki", "Bitcoin", 540, 98),
    ("Powell's monetary policy is destroying purchasing power. Bitcoin is the answer.", "bitcoin", "jerome_powell", "Bitcoin", 920, 178),
    ("Solana ecosystem has the best developer activity right now. Bullish on SOL.", "solana", "vitalik_buterin", "CryptoCurrency", 340, 67),
    ("Dogecoin is a joke but it keeps making people rich. DOGE to the moon.", "dogecoin", "elon_musk", "CryptoCurrency", 2300, 445),
    ("ETH gas fees are my biggest complaint. Vitalik needs to prioritize this.", "ethereum", "vitalik_buterin", "Ethereum", 780, 189),
    ("MicroStrategy is basically a leveraged BTC play. Saylor is a genius.", "bitcoin", "michael_saylor", "Bitcoin", 1100, 234),
    ("Trump's tariff wars are bad for everything including crypto.", "bitcoin", "donald_trump", "CryptoCurrency", 650, 134),
    ("Elon's DOGE appointment at DOGE department is peak meme timeline.", "dogecoin", "elon_musk", "CryptoCurrency", 4500, 890),
    ("Ripple vs SEC was the biggest regulatory fight in crypto. XRP won.", "xrp", "gary_gensler", "CryptoCurrency", 1800, 378),
    ("ARK Invest buying Bitcoin every day. Cathie Wood is extremely bullish.", "bitcoin", "cathie_wood", "Bitcoin", 890, 167),
    ("Kiyosaki says buy Bitcoin, silver and gold before the crash. Classic Kiyosaki.", "bitcoin", "robert_kiyosaki", "CryptoCurrency", 720, 145),
    ("Fed rate policy is the biggest macro driver for Bitcoin right now.", "bitcoin", "jerome_powell", "Bitcoin", 560, 112),
    ("Vitalik's Ethereum roadmap is ambitious but achievable. ETH is still king of DeFi.", "ethereum", "vitalik_buterin", "Ethereum", 980, 212),
    ("Saylor's average BTC buy price is around 60k. He's in massive profit.", "bitcoin", "michael_saylor", "Bitcoin", 1300, 267),
    ("Trump signed more pro-crypto legislation today. USA becoming crypto hub.", "bitcoin", "donald_trump", "Bitcoin", 2100, 423),
]

SUBREDDITS = ["Bitcoin", "CryptoCurrency", "Ethereum", "CryptoMarkets"]
AUTHORS = [
    "CryptoWatcher99", "BitcoinMaximalist", "EthereumFan", "DogeMaster",
    "SatoshiFollower", "CryptoRealist", "BlockchainDev", "AltcoinHunter",
    "HODLer2024", "CryptoSkeptic", "Web3Builder", "DefiDegen",
    "CoinAnalyst", "MarketWatcher", "TechInvestor", "CryptoNewbie",
    "LongTermHolder", "TraderJoe", "CryptoNerd", "BitcoinBull",
]

def sentiment_label(score: float) -> str:
    if score >= 0.05:
        return "positivo"
    if score <= -0.05:
        return "negativo"
    return "neutro"

def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
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
    conn.commit()

    now = datetime.now(timezone.utc)
    inserted = 0

    for i, (text, crypto, person, subreddit, score, comments) in enumerate(POSTS):
        # Distribui os posts nas últimas 3 semanas
        hours_ago = random.uniform(0, 504)  # até 21 dias atrás
        created = (now - timedelta(hours=hours_ago)).isoformat()
        collected = (now - timedelta(hours=max(0, hours_ago - 0.5))).isoformat()

        sentiment = analyzer.polarity_scores(text)["compound"]
        label = sentiment_label(sentiment)
        author = random.choice(AUTHORS)
        reddit_id = f"seed_{i:04d}_{crypto[:3]}"
        permalink = f"/r/{subreddit}/comments/{reddit_id}/post_{i}/"
        relevance = len(text) // 20 + score // 100

        try:
            cur.execute("""
                INSERT OR IGNORE INTO reddit_mentions
                (source_type, reddit_id, subreddit, author, permalink, created_utc,
                 text_content, crypto, famous_person, sentiment, sentiment_label,
                 relevance_score, reddit_score, num_comments, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "post", reddit_id, subreddit, author, permalink, created,
                text, crypto, person, sentiment, label,
                relevance, score, comments, collected
            ))
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"Erro ao inserir registro {i}: {e}")

    conn.commit()
    conn.close()
    print(f"Banco populado com sucesso! {inserted} registros inseridos em '{DB_PATH}'.")

if __name__ == "__main__":
    seed()
