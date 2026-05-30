# ACIS — Claude Code Standards

## Python Style (PEP 8)

- Line length: 100 characters maximum.
- Indentation: 4 spaces, never tabs.
- Imports: standard library first, third-party second, local (`acis.*`) last — one blank line between each group.
- Use `from __future__ import annotations` at the top of every module.
- Blank lines: 2 between top-level definitions, 1 between methods inside a class.
- Trailing whitespace: none.
- String quotes: double quotes for docstrings and prose strings; single quotes are acceptable elsewhere but be consistent within a file.
- f-strings preferred over `%` or `.format()`.
- Type hints required on all function signatures and dataclass fields.
- Use `|` union syntax (`str | None`) not `Optional[str]` — requires `from __future__ import annotations`.

## Documentation

- Every public class and function gets a docstring.
- Docstrings: one or two lines only — describe the **what** and **why**, not the **how**.
  ```python
  def compute_salience(...) -> dict[str, float]:
      """Score each detected topic using TF × log(IDF-proxy) against the video's full token counts."""
  ```
- Inline comments only for non-obvious invariants or workarounds — not for self-explanatory code.
- Field-level comments on dataclass fields that carry domain-specific meaning:
  ```python
  transcript_completeness: float  # 0–1; fraction of video duration covered by transcript
  ```

## Dataclass conventions

- Use `@dataclass(slots=True)` for all model and agent classes.
- Fields without defaults come before fields with defaults.
- Private / internal fields use `field(default=None, init=False, repr=False)`.

## Error handling

- Validate at system boundaries (YouTube API responses, DB connections, CLI env vars).
- Raise specific exceptions with context messages; avoid bare `except Exception`.
- Use `raise SystemExit(...)` only in CLI entry-point (`run.py`); raise normal exceptions elsewhere.

## Imports (live dependencies)

- `google-api-python-client`, `youtube-transcript-api`, `sqlalchemy`, `psycopg2-binary` are optional (`acis[live]`).
- Import them inside `__post_init__` or helper methods with a clear `ImportError` message directing to `pip install 'acis[live]'`.
- Never import optional dependencies at module level.

## Testing

- Sample-data mode (`python run.py --sample-data`) must always pass with zero dependencies beyond the base package.
- Tests live in `tests/` and use the `SampleIngestionClient` — no real API calls.

## Commit hygiene

- Commits are in present tense imperative: `Add YouTubeIngestionClient`, `Fix salience score overflow`.
- Never commit `.env`; commit `.env.example` with placeholder values only.
