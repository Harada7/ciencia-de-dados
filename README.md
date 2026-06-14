# Crypto Social Sentiment Monitor

Projeto em Python para coletar dados públicos do Reddit via endpoints `.json`, analisar sentimento sobre criptoativos e pessoas famosas, armazenar em SQLite e expor dados em API para Grafana ou planilha.

## O que esta versão otimizada faz

- Usa buscas direcionadas em vez de varrer muitos subreddits.
- Reduz erro `429 Too Many Requests` com delay, retry e backoff.
- Evita processar posts/comentários repetidos com cache local.
- Busca comentários somente em posts promissores.
- Calcula sentimento com VADER.
- Calcula `relevance_score` para priorizar registros mais úteis.
- Expõe endpoints JSON para Grafana.
- Gera CSV para planilha.

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload
```

Acesse:

```txt
http://127.0.0.1:8000/docs
```

## Configuração `.env`

```env
REDDIT_USER_AGENT=python:crypto-sentiment-monitor:v2.0 (academic project; contact: local-app)
POLL_INTERVAL_SECONDS=900
POST_LIMIT_PER_QUERY=10
COMMENT_LIMIT_PER_POST=30
MAX_COMMENT_POSTS_PER_CYCLE=12
MAX_QUERIES_PER_CYCLE=12
REQUEST_TIMEOUT_SECONDS=20
REQUEST_DELAY_SECONDS=2.5
DB_PATH=crypto_reddit.db
```

### Valores recomendados para evitar 429

Se aparecerem muitos erros `429`, use:

```env
POLL_INTERVAL_SECONDS=1800
POST_LIMIT_PER_QUERY=5
COMMENT_LIMIT_PER_POST=15
MAX_COMMENT_POSTS_PER_CYCLE=5
REQUEST_DELAY_SECONDS=4
```

## Endpoints principais

### Saúde da API

```txt
GET /health
```

### Executar coleta manual

```txt
POST /collect
```

### Resumo agregado

```txt
GET /summary?hours=168
```

### Série temporal para Grafana

```txt
GET /timeseries?hours=168
```

Com filtros:

```txt
GET /timeseries?hours=168&crypto=bitcoin&famous_person=elon_musk
```

### Registros recentes

```txt
GET /recent?limit=100
```

### Exportar CSV para planilha

```txt
GET /export/csv?limit=1000
```

## Sugestão de uso no Grafana

Use um datasource JSON/Infinity e conecte em:

- `/summary` para tabelas agregadas.
- `/timeseries` para gráficos de linha.
- `/recent` para tabela de comentários/posts recentes.

## Observação metodológica para o trabalho

Devido às restrições atuais da API oficial do Reddit, a coleta foi realizada por meio de endpoints públicos `.json`, aplicando controle de taxa, filtros de relevância e análise de sentimento para obter dados úteis sobre criptoativos e personalidades públicas.

## Limitações

- A coleta pública `.json` pode sofrer rate limit.
- A análise de sentimento é heurística e pode errar ironias ou contexto.
- Para produção real, o ideal seria usar API oficial aprovada, filas e observabilidade mais completa.
