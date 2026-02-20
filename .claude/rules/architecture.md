# Architecture Rules

## Pipeline Pattern
This project follows a strict pipeline pattern:
```
Collector → Processor → Output
```

Each stage is independent. A collector failure must not crash the pipeline — other collectors continue.

## Adding New Components

### New Collector
1. Create `src/collectors/{name}_collector.py`
2. Define a class with `collect(hours: int) -> list[Article]` method
3. Import `Article` from `src.collectors.rss_collector`
4. Export in `src/collectors/__init__.py`
5. Call in `main.py` collection step
6. Add API key to `.env.example` if needed

### New Processor
1. Create `src/processors/{name}.py`
2. Accept `list[Article]`, return `list[Article]`
3. Export in `src/processors/__init__.py`

### New Output
1. Create `src/outputs/{name}_output.py`
2. Implement `save(articles)` or equivalent method
3. Export in `src/outputs/__init__.py`

## Web Dashboard
- FastAPI + Jinja2 + HTMX for interactive UI without JS frameworks
- SQLAlchemy models in `web/models/`
- Business logic in `web/services/`
- API routes in `web/api/`
- HTML templates in `web/templates/`
