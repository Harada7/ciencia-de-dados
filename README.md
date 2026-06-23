# 📊 Crypto Sentiment Monitor

> Sistema de monitoramento e análise de sentimento do mercado de criptomoedas com base em portais de notícias internacionais.

Projeto final da disciplina de **Ciência de Dados** — UNIUBE (Prof. Igor Junqueira, 2026).

---

## 🖥️ Preview do Dashboard

O dashboard exibe em tempo real:
- 📌 Visão geral com métricas e narrativa automática dos dados
- 📈 Distribuição de sentimento (positivo / neutro / negativo)
- 🕒 Evolução temporal do sentimento
- ⭐ Personalidades mais mencionadas
- 🔍 Clustering de tópicos (K-Means + TF-IDF)
- 📉 Correlação entre sentimento e preço do Bitcoin

---

## ⚙️ Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/Harada7/ciencia-de-dados.git
cd ciencia-de-dados
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
pip install yfinance scipy statsmodels matplotlib
```

> ⚠️ Se o comando `pip` não funcionar, use `py -m pip` no lugar.

---

## 🗄️ Populando o banco de dados

O banco de dados **não está incluso** no repositório. É necessário popular antes de rodar o dashboard.

### Opção A — Dados históricos reais (recomendado)

Importa ~652 artigos reais de portais como CoinDesk, Reuters, Bloomberg Crypto etc.:

```bash
py import_newsapi.py
```

> ℹ️ Necessita de uma chave da [NewsAPI.org](https://newsapi.org) (plano gratuito disponível).  
> Defina a variável de ambiente `NEWSAPI_KEY` ou edite diretamente o arquivo.

### Opção B — Dados de semente para testes rápidos

Insere 72 posts realistas para testar o dashboard sem precisar da NewsAPI:

```bash
py seed_data.py
```

---

## 🚀 Como rodar

Você precisará de **dois terminais abertos** ao mesmo tempo.

### Terminal 1 — Backend (API + coleta automática)

```bash
py -m uvicorn app:app --reload
```

Aguarde aparecer:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2 — Dashboard

```bash
py -m streamlit run dashboard.py
```

O dashboard abrirá automaticamente no navegador em:

```
http://localhost:8501
```

> 💡 O sistema coleta novas notícias automaticamente a cada **30 minutos**.  
> O dashboard atualiza sozinho a cada **60 segundos**.

---

## 📁 Estrutura do projeto

```
ciencia-de-dados/
├── app.py              # Backend FastAPI — coleta RSS, análise VADER, endpoints
├── dashboard.py        # Dashboard Streamlit — visualizações interativas
├── import_newsapi.py   # Importação histórica via NewsAPI.org
├── seed_data.py        # Dados de semente para testes
├── requirements.txt    # Dependências Python
├── .env.example        # Modelo de variáveis de ambiente
└── README.md           # Este arquivo
```

---

## 🌐 Fontes de notícias monitoradas

O sistema coleta automaticamente via RSS de 16 portais internacionais:

| Portal | Portal | Portal | Portal |
|---|---|---|---|
| CoinDesk | CoinTelegraph | Decrypt | Bitcoin Magazine |
| CryptoNews | NewsBTC | AMBCrypto | CryptoPotato |
| BeInCrypto | CoinJournal | CryptoSlate | Bitcoinist |
| U.Today | CryptoNewsFlash | Daily Hodl | ZyCrypto |

---

## 🔌 Endpoints da API

Com o backend rodando, acesse `http://localhost:8000/docs` para a documentação completa.

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

## 🛠️ Tecnologias utilizadas

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

## ❓ Solução de problemas

**`pip` não reconhecido:**
```bash
py -m pip install -r requirements.txt
```

**`uvicorn` não reconhecido:**
```bash
py -m uvicorn app:app --reload
```

**Dashboard aparece vazio:**
- Certifique-se de que o backend (Terminal 1) está rodando
- Execute `py seed_data.py` ou `py import_newsapi.py` para popular o banco

**Erro de módulo não encontrado:**
```bash
py -m pip install yfinance scipy statsmodels matplotlib streamlit-autorefresh
```
