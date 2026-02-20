---
paths:
  - "src/**/*.py"
  - "web/**/*.py"
  - "*.py"
---

# Python Code Style

- Use `@dataclass` for data structures, not plain dicts
- Type hints on all function signatures: `def func(arg: str) -> list[Article]:`
- Use `Optional[T]` for nullable types
- f-string for all string formatting
- Structured logging: `print(f"[ModuleName] 메시지")`
- Import order: stdlib → third-party → local modules
- Class-based collectors with `collect()` method returning `list[Article]`
- Each collector/processor is a single file with a single main class
- Error handling: wrap external API calls in try/except, log and continue
- Never hardcode API keys — always `os.getenv("KEY_NAME")`
