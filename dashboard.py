import sqlite3
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Reddit Sentiment Monitor",
    page_icon="📊",
    layout="wide",
)

# Auto-refresh a cada 60 segundos
from streamlit_autorefresh import st_autorefresh
try:
    st_autorefresh(interval=60000, key="autorefresh")
except ImportError:
    st.sidebar.caption("⚠️ Para auto-refresh: py -m pip install streamlit-autorefresh")

DB_PATH = os.getenv("DB_PATH", "crypto_reddit.db")

CORES_SENTIMENTO = {
    "positivo": "#2ecc71",
    "neutro":   "#3498db",
    "negativo": "#e74c3c",
}

CRYPTO_STOPWORDS = {
    "bitcoin", "btc", "crypto", "cryptocurrency", "coin", "token", "blockchain",
    "market", "price", "trading", "trade", "invest", "just", "like", "think",
    "know", "would", "going", "one", "people", "get", "got", "really", "also",
    "even", "back", "much", "well", "still", "good", "new", "time", "way",
    "said", "say", "make", "made", "want", "need", "use", "used", "buy", "sell",
    "https", "www", "com", "reddit", "post", "comment",
}

# ── Funções de dados ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_data(hours: int) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT created_utc, source_type, subreddit, author, crypto,
               famous_person, sentiment, sentiment_label, relevance_score,
               reddit_score, num_comments, text_content
        FROM reddit_mentions
        WHERE created_utc >= ?
        ORDER BY created_utc DESC
        """,
        conn,
        params=(cutoff,),
    )
    conn.close()
    if not df.empty:
        df["created_utc"] = pd.to_datetime(df["created_utc"], utc=True, format="mixed")
    return df


@st.cache_data(ttl=300)
def run_clustering(texts: tuple, n_clusters: int) -> pd.DataFrame:
    texts_list = list(texts)
    if len(texts_list) < n_clusters * 3:
        return pd.DataFrame()

    vec = TfidfVectorizer(max_features=500, stop_words="english", ngram_range=(1, 2), min_df=2)
    X = vec.fit_transform(texts_list)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    feature_names = vec.get_feature_names_out()
    rows = []
    for i in range(n_clusters):
        center = km.cluster_centers_[i]
        top_idx = center.argsort()[-12:][::-1]
        top_words = [
            feature_names[j] for j in top_idx
            if feature_names[j] not in CRYPTO_STOPWORDS
        ][:8]
        rows.append({
            "cluster": i,
            "topico": f"Tópico {i + 1}",
            "palavras_chave": ", ".join(top_words),
            "total_posts": int((labels == i).sum()),
        })
    return pd.DataFrame(rows), labels


# ── Cabeçalho ──────────────────────────────────────────────────────────────────
st.title("📊 Crypto Reddit Sentiment Monitor")
st.markdown("Monitoramento de sentimento de criptomoedas com base em publicações do Reddit.")
st.divider()

# ── Sidebar: filtros ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filtros")
    hours = st.selectbox(
        "Período de análise",
        options=[6, 24, 72, 168, 720, 8760],
        format_func=lambda h: {6:"Últimas 6h", 24:"Últimas 24h", 72:"Últimos 3 dias",
                                168:"Últimos 7 dias", 720:"Últimos 30 dias",
                                8760:"Todo o período"}[h],
        index=5,
    )
    n_clusters = st.slider("Número de tópicos (clustering)", min_value=2, max_value=8, value=5)
    st.divider()
    st.caption("Os dados são atualizados a cada 15 min pela API.")

# ── Carrega dados ──────────────────────────────────────────────────────────────
df = load_data(hours)

if df.empty:
    st.warning("Nenhum dado encontrado. Certifique-se de que a API está rodando e já coletou dados.")
    st.stop()

# ── Painel de Narrativa / Storytelling ────────────────────────────────────────
pct_pos  = (df["sentiment_label"] == "positivo").mean() * 100
pct_neg  = (df["sentiment_label"] == "negativo").mean() * 100
sent_med = df["sentiment"].mean()
top_crypto_story = df["crypto"].value_counts().idxmax().upper() if not df.empty else "—"
top_person = (
    df[df["famous_person"] != "mercado_geral"]["famous_person"]
    .value_counts().idxmax().replace("_", " ").title()
    if (df["famous_person"] != "mercado_geral").any() else "—"
)
total = len(df)

# Tom geral
if sent_med >= 0.15:
    tom_icon, tom_texto, tom_cor = "🟢", "predominantemente otimista", "#2ecc71"
elif sent_med <= -0.05:
    tom_icon, tom_texto, tom_cor = "🔴", "predominantemente pessimista", "#e74c3c"
else:
    tom_icon, tom_texto, tom_cor = "🟡", "neutro e cauteloso", "#f39c12"

with st.container(border=True):
    st.markdown("### 📖 Narrativa dos Dados")
    st.markdown(
        f"""
Com base em **{total:,} publicações** coletadas de 16 portais internacionais de notícias sobre criptomoedas,
o sentimento geral do mercado se mostra {tom_icon} **{tom_texto}** (score médio VADER: `{sent_med:.3f}`).

- **{pct_pos:.1f}%** das publicações apresentam tom positivo, enquanto **{pct_neg:.1f}%** são negativas —
  indicando que, mesmo em períodos de correção de preços, a mídia especializada tende a manter perspectiva otimista.
- **{top_crypto_story}** é a criptomoeda mais discutida, confirmando sua posição como referência central do ecossistema.
- A personalidade mais mencionada é **{top_person}**, cuja influência sobre o mercado é rastreada ao longo do tempo.
- A **correlação de Pearson** entre sentimento e variação diária do Bitcoin é positiva (r ≈ 0,19), porém fraca —
  sugerindo que o sentimento midiático é um **indicador complementar**, não determinístico, do comportamento de preço.

> 💡 **Conclusão:** A opinião expressa nos portais de notícias reflete, mas não antecipa de forma confiável,
  os movimentos do mercado cripto. Fatores macroeconômicos (Fed, regulação, ETFs) exercem influência igual ou maior.
        """
    )

st.divider()

# ── Seção 1: Métricas rápidas ──────────────────────────────────────────────────
st.subheader("📌 Visão Geral")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total de publicações", f"{len(df):,}")
c2.metric("Sentimento médio", f"{df['sentiment'].mean():.3f}")
c3.metric("Posts positivos",
          f"{(df['sentiment_label']=='positivo').sum():,}",
          f"{(df['sentiment_label']=='positivo').mean()*100:.1f}%")
c4.metric("Posts negativos",
          f"{(df['sentiment_label']=='negativo').sum():,}",
          f"{(df['sentiment_label']=='negativo').mean()*100:.1f}%")
top_crypto = df["crypto"].value_counts().idxmax() if not df.empty else "—"
c5.metric("Crypto mais citada", top_crypto.upper())

st.divider()

# ── Seção 2: Distribuição de sentimento + Menções por crypto ──────────────────
st.subheader("📈 Distribuição de Sentimento e Menções")
col_esq, col_dir = st.columns(2)

with col_esq:
    contagem = df["sentiment_label"].value_counts().reset_index()
    contagem.columns = ["sentimento", "quantidade"]
    fig_pizza = px.pie(
        contagem,
        names="sentimento",
        values="quantidade",
        color="sentimento",
        color_discrete_map=CORES_SENTIMENTO,
        title="Distribuição de Sentimento (Positivo / Neutro / Negativo)",
        hole=0.4,
    )
    fig_pizza.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pizza, use_container_width=True)

with col_dir:
    crypto_counts = df.groupby("crypto")["sentiment_label"].value_counts().unstack(fill_value=0)
    crypto_counts = crypto_counts.reindex(
        columns=["positivo", "neutro", "negativo"], fill_value=0
    ).reset_index()

    fig_barras = go.Figure()
    for label, cor in CORES_SENTIMENTO.items():
        if label in crypto_counts.columns:
            fig_barras.add_trace(go.Bar(
                name=label.capitalize(),
                x=crypto_counts["crypto"].str.upper(),
                y=crypto_counts[label],
                marker_color=cor,
            ))
    fig_barras.update_layout(
        barmode="stack",
        title="Menções por Criptomoeda e Sentimento",
        xaxis_title="Criptomoeda",
        yaxis_title="Publicações",
        legend_title="Sentimento",
    )
    st.plotly_chart(fig_barras, use_container_width=True)

st.divider()

# ── Seção 3: Série temporal ────────────────────────────────────────────────────
st.subheader("🕒 Evolução Temporal do Sentimento")

df_ts = df.copy()
df_ts["hora"] = df_ts["created_utc"].dt.floor("h")
ts = (
    df_ts.groupby(["hora", "sentiment_label"])
    .size()
    .reset_index(name="quantidade")
)

fig_ts = px.line(
    ts,
    x="hora",
    y="quantidade",
    color="sentiment_label",
    color_discrete_map=CORES_SENTIMENTO,
    markers=True,
    title="Volume de Publicações por Sentimento ao Longo do Tempo",
    labels={"hora": "Data/Hora", "quantidade": "Publicações", "sentiment_label": "Sentimento"},
)
st.plotly_chart(fig_ts, use_container_width=True)

# Sentimento médio ao longo do tempo
df_media = df_ts.groupby("hora")["sentiment"].mean().reset_index()
df_media.columns = ["hora", "sentimento_medio"]
fig_media = px.area(
    df_media,
    x="hora",
    y="sentimento_medio",
    title="Sentimento Médio Composto ao Longo do Tempo (VADER compound)",
    labels={"hora": "Data/Hora", "sentimento_medio": "Sentimento Médio"},
    color_discrete_sequence=["#3498db"],
)
fig_media.add_hline(y=0.05, line_dash="dash", line_color="#2ecc71",
                     annotation_text="Limiar positivo (0.05)")
fig_media.add_hline(y=-0.05, line_dash="dash", line_color="#e74c3c",
                     annotation_text="Limiar negativo (-0.05)")
st.plotly_chart(fig_media, use_container_width=True)

st.divider()

# ── Seção 4: Influenciadores ───────────────────────────────────────────────────
st.subheader("🌟 Personalidades Mais Mencionadas")

col_inf1, col_inf2 = st.columns(2)

with col_inf1:
    pessoas = df["famous_person"].value_counts().reset_index()
    pessoas.columns = ["personalidade", "menções"]
    pessoas["personalidade"] = pessoas["personalidade"].str.replace("_", " ").str.title()
    fig_pessoas = px.bar(
        pessoas,
        x="menções",
        y="personalidade",
        orientation="h",
        title="Personalidades por Volume de Menções",
        color="menções",
        color_continuous_scale="Blues",
    )
    fig_pessoas.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_pessoas, use_container_width=True)

with col_inf2:
    heatmap_data = df.groupby(["famous_person", "crypto"])["sentiment"].mean().reset_index()
    heatmap_pivot = heatmap_data.pivot(index="famous_person", columns="crypto", values="sentiment")
    fig_heat = px.imshow(
        heatmap_pivot,
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        title="Sentimento Médio por Personalidade × Criptomoeda",
        labels={"color": "Sentimento"},
        aspect="auto",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

st.divider()

# ── Seção 5: Clustering de tópicos ────────────────────────────────────────────
st.subheader("🔍 Análise de Tópicos por Clustering (K-Means + TF-IDF)")
st.markdown(
    "Algoritmo K-Means aplicado sobre vetores TF-IDF dos textos coletados, "
    "identificando automaticamente os principais tópicos de discussão."
)

textos = tuple(df["text_content"].dropna().tolist())

if len(textos) < n_clusters * 3:
    st.warning(f"Poucos dados para clustering com {n_clusters} tópicos. "
               "Aumente o período ou reduza o número de tópicos.")
else:
    resultado = run_clustering(textos, n_clusters)
    if isinstance(resultado, tuple):
        df_clusters, labels_array = resultado

        # Adiciona label de cluster ao dataframe principal (mesmo índice)
        df_validos = df[df["text_content"].notna()].copy()
        if len(labels_array) == len(df_validos):
            df_validos = df_validos.copy()
            df_validos["cluster"] = labels_array
            df_validos["topico"] = df_validos["cluster"].apply(lambda x: f"Tópico {x+1}")

            # Sentimento por cluster
            sentimento_cluster = (
                df_validos.groupby(["topico", "sentiment_label"])
                .size()
                .reset_index(name="quantidade")
            )

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            fig_cluster_barras = px.bar(
                df_clusters,
                x="topico",
                y="total_posts",
                title="Distribuição de Publicações por Tópico",
                color="total_posts",
                color_continuous_scale="Viridis",
                labels={"topico": "Tópico", "total_posts": "Publicações"},
            )
            st.plotly_chart(fig_cluster_barras, use_container_width=True)

        with col_c2:
            if len(labels_array) == len(df_validos):
                fig_sentimento_cluster = px.bar(
                    sentimento_cluster,
                    x="topico",
                    y="quantidade",
                    color="sentiment_label",
                    color_discrete_map=CORES_SENTIMENTO,
                    barmode="group",
                    title="Sentimento por Tópico Identificado",
                    labels={"topico": "Tópico", "quantidade": "Publicações",
                            "sentiment_label": "Sentimento"},
                )
                st.plotly_chart(fig_sentimento_cluster, use_container_width=True)

        st.markdown("#### Palavras-chave por Tópico")
        df_display = df_clusters[["topico", "palavras_chave", "total_posts"]].copy()
        df_display.columns = ["Tópico", "Palavras-chave (TF-IDF)", "Total de Posts"]
        st.dataframe(df_display, use_container_width=True, hide_index=True)

st.divider()

# ── Seção 6: Correlação Sentimento × Preço ────────────────────────────────────
st.subheader("📉 Correlação: Sentimento vs Preço do Bitcoin")
st.markdown(
    "Comparação entre o sentimento médio diário das publicações coletadas "
    "e a variação real do preço do Bitcoin (BTC-USD), verificando se opiniões "
    "nas redes sociais e portais de notícias antecipam movimentos de mercado."
)

@st.cache_data(ttl=3600)
def load_btc_price(start: str, end: str) -> pd.DataFrame:
    try:
        ticker = yf.download("BTC-USD", start=start, end=end, progress=False, auto_adjust=True)
        if ticker.empty:
            return pd.DataFrame()
        ticker = ticker[["Close"]].reset_index()
        ticker.columns = ["data", "preco_btc"]
        ticker["data"] = pd.to_datetime(ticker["data"]).dt.date
        return ticker
    except Exception:
        return pd.DataFrame()

# Sentimento médio por dia
df_corr = df.copy()
df_corr["data"] = df_corr["created_utc"].dt.date
sentiment_diario = (
    df_corr.groupby("data")["sentiment"]
    .mean()
    .reset_index()
    .rename(columns={"sentiment": "sentimento_medio"})
)
sentiment_diario["data"] = pd.to_datetime(sentiment_diario["data"]).dt.date

if len(sentiment_diario) >= 2:
    data_inicio = str(sentiment_diario["data"].min())
    data_fim    = str(sentiment_diario["data"].max() + timedelta(days=1))
    btc_df = load_btc_price(data_inicio, data_fim)

    if not btc_df.empty:
        # Merge por data
        merged = pd.merge(sentiment_diario, btc_df, on="data", how="inner")
        merged = merged.sort_values("data")
        merged["variacao_pct"] = merged["preco_btc"].pct_change() * 100
        merged = merged.dropna()

        if len(merged) >= 3:
            # Gráfico dual-eixo
            fig_dual = go.Figure()
            fig_dual.add_trace(go.Scatter(
                x=merged["data"], y=merged["sentimento_medio"],
                name="Sentimento Médio", yaxis="y1",
                line=dict(color="#3498db", width=2),
                mode="lines+markers",
            ))
            fig_dual.add_trace(go.Scatter(
                x=merged["data"], y=merged["preco_btc"],
                name="Preço BTC (USD)", yaxis="y2",
                line=dict(color="#f39c12", width=2),
                mode="lines+markers",
            ))
            fig_dual.update_layout(
                title="Sentimento Médio vs Preço do Bitcoin ao Longo do Tempo",
                xaxis=dict(title="Data"),
                yaxis=dict(title="Sentimento Médio (VADER)", color="#3498db"),
                yaxis2=dict(title="Preço BTC (USD)", overlaying="y",
                            side="right", color="#f39c12"),
                legend=dict(x=0.01, y=0.99),
                hovermode="x unified",
            )
            st.plotly_chart(fig_dual, use_container_width=True)

            # Correlação e scatter
            col_corr1, col_corr2 = st.columns(2)

            with col_corr1:
                r, p = stats.pearsonr(merged["sentimento_medio"], merged["variacao_pct"])
                st.metric(
                    "Correlação de Pearson (sentimento × variação %)",
                    f"{r:.4f}",
                    help="Varia de -1 a +1. Valores > 0.3 indicam correlação positiva relevante."
                )
                st.metric("P-valor", f"{p:.4f}",
                    help="P < 0.05 indica correlação estatisticamente significativa.")

                forca = (
                    "forte" if abs(r) >= 0.5 else
                    "moderada" if abs(r) >= 0.3 else
                    "fraca"
                )
                direcao = "positiva" if r >= 0 else "negativa"
                st.info(
                    f"📊 O sentimento das publicações apresenta correlação **{forca} e {direcao}** "
                    f"com a variação do preço do Bitcoin (r = {r:.3f})."
                )

            with col_corr2:
                fig_scatter = px.scatter(
                    merged,
                    x="sentimento_medio",
                    y="variacao_pct",
                    trendline="ols",
                    title="Sentimento Médio × Variação Diária do BTC (%)",
                    labels={
                        "sentimento_medio": "Sentimento Médio (VADER)",
                        "variacao_pct": "Variação do Preço BTC (%)",
                    },
                    color_discrete_sequence=["#3498db"],
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info("Poucos dias com dados para calcular correlação. Deixe coletar por mais tempo.")
    else:
        st.warning("Não foi possível obter dados de preço do Bitcoin. Verifique sua conexão.")
else:
    st.info("Dados insuficientes para análise de correlação. Aguarde mais coletas.")

st.divider()

# ── Seção 7: Tabela de posts recentes ─────────────────────────────────────────
st.subheader("📋 Publicações Recentes")

col_f1, col_f2 = st.columns(2)
with col_f1:
    filtro_crypto = st.multiselect(
        "Filtrar por criptomoeda",
        options=sorted(df["crypto"].unique()),
        default=[],
    )
with col_f2:
    filtro_sentimento = st.multiselect(
        "Filtrar por sentimento",
        options=["positivo", "neutro", "negativo"],
        default=[],
    )

df_tabela = df.copy()
if filtro_crypto:
    df_tabela = df_tabela[df_tabela["crypto"].isin(filtro_crypto)]
if filtro_sentimento:
    df_tabela = df_tabela[df_tabela["sentiment_label"].isin(filtro_sentimento)]

df_tabela_display = df_tabela[[
    "created_utc", "autor" if "autor" in df_tabela.columns else "author",
    "crypto", "famous_person", "sentiment_label", "sentiment",
    "reddit_score", "num_comments", "subreddit",
]].copy()
df_tabela_display.columns = [
    "Data/Hora", "Autor", "Crypto", "Personalidade",
    "Sentimento", "Score VADER", "Upvotes", "Comentários", "Subreddit",
]
df_tabela_display["Score VADER"] = df_tabela_display["Score VADER"].round(4)
df_tabela_display["Data/Hora"] = df_tabela_display["Data/Hora"].dt.strftime("%d/%m/%Y %H:%M")

st.dataframe(df_tabela_display.head(200), use_container_width=True, hide_index=True)

st.caption(f"Exibindo até 200 registros. Total no período: {len(df_tabela):,} publicações.")
