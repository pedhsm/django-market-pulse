# Market Pulse — Financial News & Sentiment API

> **Objetivo**: API robusta em Django para monitoramento de ativos financeiros, integrando dados de **candles (OHLC)** e **notícias com análise de sentimento** (via LLM). O projeto inclui um dashboard em **Streamlit** para visualização de tendências.

---

## Arquitetura da Solução

O projeto segue os princípios de **Arquitetura Limpa** e **Separação de Responsabilidades**, organizado em 3 apps principais para garantir desacoplamento:

### 1) `core/` — Domínio e Regras de Negócio
* **Responsabilidade**: Define os modelos essenciais (`Company`, `Article`, `MarketCandle`) e regras de integridade.
* **Destaque**: Deduplicação automática de notícias por URL e constraints de banco de dados para garantir consistência.

### 2) `api/` — Interface REST (Django Rest Framework)
* **Contrato**: Exposição de dados via endpoints JSON otimizados.
* **Features**:
    * Filtros temporais (`?start`, `?end`) e por ticker.
    * Serializers leves com `external_url` e HATEOAS (links de navegação).

### 3) `ingestion/` — Pipelines de Dados (ETL)
* **Pipeline de Notícias**: Coleta notícias via **Finnhub**, processa análise de sentimento via **Cerebras AI** e persiste dados de forma idempotente.
* **Pipeline de Mercado**: Ingestão de dados históricos de candles (OHLC) a partir de fontes locais ou remotas.
* **Design**: Execução síncrona simplificada via Management Commands (`manage.py`), facilitando a operação sem dependência de workers complexos (Celery) nesta versão.

---

## Decisões Técnicas

* **Stack**: Python 3.10+, Django 4.x, DRF, Streamlit.
* **Estratégia de Ingestão**: Scripts customizados (`manage.py shell`) permitem controle granular sobre a atualização dos dados, com tratamento de limites de API (rate limits).
* **Análise de Sentimento**: Utilização de LLMs (via API externa) para classificar headlines, enriquecendo os dados brutos com inteligência de mercado.
* **Visualização**: O app Streamlit consome a própria API do projeto, demonstrando um fluxo real de cliente-servidor desacoplado.

---

## Fluxo de Dados

```mermaid
flowchart LR
  A[Seed: Companies] -->|Load| B[(DB: Company)]
  C[Source: Market Data] -->|ETL Pipeline| D[(DB: MarketCandle)]
  B -->|Active Tickers| E[News Pipeline (Finnhub + AI)]
  E --> F[(DB: Article + Sentiment)]
  F -->|/api/articles| G[Dashboard Streamlit]
  D -->|/api/marketcandles| G