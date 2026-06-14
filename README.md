# Crypto Sentiment Monitor

Sistema de monitoramento e análise de sentimento do mercado de criptomoedas com base em portais de notícias internacionais.

Projeto final da disciplina de **Ciência de Dados** — UNIUBE (Prof. Igor Junqueira, 2026).

---

## Como rodar

### Pré-requisitos

```bash
py -m pip install -r requirements.txt
py -m pip install yfinance scipy statsmodels matplotlib
```

### 1 — Iniciar o backend (API + coleta automática)

Abra um terminal e execute:

```bash
cd C:\Users\Casa\Documents\ciencia-de-dados
py -m uvicorn app:app --reload
```

A API ficará disponível em: `http://localhost:8000`  
Documentação interativa: `http://localhost:8000/docs`

### 2 — Iniciar o dashboard

Abra **outro terminal** e execute:

```bash
cd C:\Users\Casa\Documents\ciencia-de-dados
py -m streamlit run dashboard.py
```

O dashboard abrirá automaticamente em: `http://localhost:8501`

---

## Populando o banco de dados

### Dados históricos via NewsAPI (rodar uma vez)

```bash
py import_newsapi.py
```

Importa ~652 artigos reais de portais como Reuters, CoinDesk, Bloomberg Crypto, etc.

### Dados de semente (opcional)

```bash
py seed_data.py
```

Insere 72 posts realistas para testes iniciais.

---

## Estrutura do projeto

```
ciencia-de-dados/
├── app.py              # Backend FastAPI — coleta RSS, análise VADER, endpoints
├── dashboard.py        # Dashboard Streamlit — visualizações interativas
├── import_newsapi.py   # Importação histórica via NewsAPI.org
├── seed_data.py        # Dados de semente para testes
├── requirements.txt    # Dependências Python
└── .env.example        # Variáveis de ambiente (copie para .env)
```

---

## Endpoints da API

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status da API |
| `/collect` | GET/POST | Dispara coleta manual |
| `/summary?hours=168` | GET | Resumo agregado por período |
| `/timeseries?hours=168` | GET | Série temporal do sentimento |
| `/recent?limit=100` | GET | Últimas publicações |
| `/clustering` | GET | Análise K-Means + TF-IDF |
| `/export/csv` | GET | Exportar dados em CSV |

---

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Banco de dados | SQLite |
| Análise de sentimento | VADER (vaderSentiment) |
| Clustering de tópicos | K-Means + TF-IDF (scikit-learn) |
| Preço do Bitcoin | yfinance |
| Correlação estatística | scipy.stats.pearsonr |
| Dashboard | Streamlit + Plotly |
| Linguagem | Python 3.13 |

---

## Fontes de dados monitoradas (RSS)

CoinDesk · CoinTelegraph · Decrypt · Bitcoin Magazine · CryptoNews · NewsBTC · AMBCrypto · CryptoPotato · BeInCrypto · CoinJournal · CryptoSlate · Bitcoinist · U.Today · CryptoNewsFlash · Daily Hodl · ZyCrypto
