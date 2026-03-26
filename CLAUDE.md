# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **backend repository** for the Polymarket Follow-Alpha System. All Python/FastAPI backend code lives here.

## Repository Status

- **Main branch**: `main`
- **This repository contains**: All backend source code
- **Frontend code**: Lives in [PolyFollow-Frontend](https://github.com/verncake/PolyFollow-Frontend)
- **Documentation**: Lives in [PolyFollow](https://github.com/verncake/PolyFollow)

## Development Setup

```bash
# Clone and setup
cd PolyFollow-Backend
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing
```

## Project Structure

```
PolyFollow-Backend/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── api/routes/             # API endpoints
│   │   ├── account.py          # /api/v1/account/*
│   │   └── leaderboard.py      # /api/v1/leaderboard/*
│   ├── core/                   # Configuration
│   │   ├── config.py           # Environment variables
│   │   └── redis.py            # Upstash Redis client
│   ├── schemas/                # Pydantic models
│   │   └── task.py             # TradeTask for Follow-Alpha
│   └── services/               # Business logic
│       ├── gamma/              # Gamma API client
│       ├── data/               # Data API client
│       ├── clob/               # CLOB API clients
│       ├── websocket/          # WebSocket client
│       ├── auth/               # Auth clients
│       ├── account_service.py  # P/L calculations
│       ├── scoring_service.py  # 10-dimension scoring
│       ├── position_enricher.py # Position state enrichment
│       └── blockchain.py       # Polygon USDC.e queries
├── tests/                      # pytest tests (136 tests)
├── requirements.txt
└── pyproject.toml
```

## Key Technologies

- **FastAPI** - Async web framework
- **httpx** - Async HTTP client (NOT requests)
- **SQLAlchemy 2.0 + asyncpg** - Async ORM
- **Upstash Redis** - Serverless Redis for caching and queues
- **Pydantic** - Data validation
- **pytest** - Testing framework

## Coding Rules

### MUST Follow

1. **Async Only**: Use `httpx` for HTTP, NEVER `requests`. Use `asyncio` instead of `time.sleep`.
2. **Decimal for Money**: All monetary calculations must use `Decimal`, NEVER `float`.
3. **Environment Variables**: All secrets via environment variables, never hardcoded.
4. **Type Hints**: Always use type hints for function signatures.
5. **Error Handling**: Implement retry with exponential backoff for external API calls.

### API Client Pattern

All external API clients should:
- Inherit from `BaseClient` in `services/base.py`
- Implement exponential backoff retry
- Use `httpx.AsyncClient` with timeout
- Log errors before raising

### Testing Requirements

- All new features require tests
- Mock external API calls in unit tests
- Run `pytest tests/ -v` before submitting PR

## 10-Dimensional Scoring System

The scoring service evaluates traders on:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Profitability | 15% | P/L normalized |
| Win Rate | 15% | Excludes small positions |
| Profit Factor | 15% | 0-5x mapping |
| Risk Management | 10% | Based on profit factor + stop-loss |
| Experience | 10% | sqrt(days * trades) |
| Position Control | 10% | Max position ratio |
| Anti-Bot | 5% | Sleep patterns + integer preference |
| Focus | 5% | HHI concentration |
| Close Discipline | 10% | SELL vs REDEEM ratio |
| Capital | 5% | Log scale |

## Phase 4: Follow-Alpha Engine

When implementing Follow-Alpha features:

1. **TradeTask Schema** (`app/schemas/task.py`): JSON-serializable, no Pickle
2. **Redis Queue** (`app/core/redis_queue.py`): `push_task`, `pop_task`, `ack_task`
3. **TASK_CACHE**: Idempotency check before processing
4. **Monitor ↔ Worker**: Physical separation via Redis queue, no direct calls

## Commit & PR Process

1. Create feature branch: `git checkout -b feat/your-feature`
2. Commit with conventional message: `feat: add new feature`
3. Push and create PR to `main`
4. Ensure all tests pass
5. Request review

## Environment Variables

Required in `.env`:
```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
POLYMARKET_CLOB_API_URL
POLYMARKET_GAMMA_API_URL
```
