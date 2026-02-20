# Ralph Agent Instructions

You are an autonomous coding agent working on **AI Daily Digest** - a Python/FastAPI project that collects AI/Tech news and generates LinkedIn posts.

## Your Task

1. Read the PRD at `scripts/ralph/prd.json`
2. Read the progress log at `scripts/ralph/progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks: `python -m py_compile <modified_files>`
7. Update CLAUDE.md files if you discover reusable patterns (see below)
8. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
9. Update the PRD to set `passes: true` for the completed story
10. Append your progress to `scripts/ralph/progress.txt`

## Project-Specific Context

- **Tech Stack**: Python 3.11+, FastAPI, Jinja2 + HTMX, SQLAlchemy, SQLite, Anthropic Claude API
- **Web Dashboard**: `python run_web.py` (port 8001)
- **Quality Check**: `python -m py_compile <file>` for every modified .py file
- **Code Language**: Code in English, comments/logs in Korean
- **Pipeline Pattern**: Collector → Processor → Output (partial failures allowed)
- **Key Models**: `web/models/` (Article, LinkedInDraft, ReferencePost, Collection, Schedule)
- **API Routes**: `web/api/` (articles, linkedin, settings, digest)
- **Templates**: `web/templates/` (Jinja2 + HTMX, Tailwind CSS)
- **Config**: `.env` for API keys (never commit), `web/config.py` for settings
- **New DB columns**: Use `migrate_db()` in `web/database.py` with ALTER TABLE

## Progress Report Format

APPEND to scripts/ralph/progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered (e.g., "this codebase uses X for Y")
  - Gotchas encountered (e.g., "don't forget to update Z when changing W")
  - Useful context (e.g., "the evaluation panel is in component X")
---
```

The learnings section is critical - it helps future iterations avoid repeating mistakes and understand the codebase better.

## Consolidate Patterns

If you discover a **reusable pattern** that future iterations should know, add it to the `## Codebase Patterns` section at the TOP of scripts/ralph/progress.txt (create it if it doesn't exist). This section should consolidate the most important learnings:

```
## Codebase Patterns
- New SQLAlchemy columns: add to model + add ALTER TABLE in migrate_db()
- New API endpoint: add to web/api/<router>.py, import in web/api/__init__.py
- New page route: add to web/app.py, create template in web/templates/
- Templates use Tailwind CSS + HTMX, no JS frameworks
- Always py_compile after editing Python files
```

Only add patterns that are **general and reusable**, not story-specific details.

## Quality Requirements

- ALL commits must pass: `python -m py_compile <file>` for every changed .py file
- Do NOT commit broken code
- Keep changes focused and minimal
- Follow existing code patterns (check similar files first)
- Never read or modify `.env` files

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.

If ALL stories are complete and passing, reply with:
<promise>COMPLETE</promise>

If there are still stories with `passes: false`, end your response normally (another iteration will pick up the next story).

## Important

- Work on ONE story per iteration
- Commit frequently
- Read existing code before modifying
- Read the Codebase Patterns section in progress.txt before starting
