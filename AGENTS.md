# AGENTS.md

**Stack:** Python 3.14 · Reflex.dev · FastAPI · SQLAlchemy · Alembic · Pydantic · appkit_mantine · appkit_commons

---

## Rules & Principles

**NEVER** guess — **ALWAYS** read the doc first (use Context7 or a skill)!

1. State assumptions explicitly; push back on over-engineering; ask when unclear.
2. No features, abstractions, or flexibility beyond what was asked. If 200 lines could be 50, rewrite it.
3. Only touch what's needed; match existing style; mention (don't delete) unrelated dead code; remove only orphans YOUR changes created.
4. Goal-driven: "Fix X" → "Write a reproducing test, then make it pass." Plan multi-step tasks:

   ```code
   1. [Step] → verify: [check]
   ```

5. **Think → Memory → Tools → Code → Memory.** Search Memory and context first; write learnings back.
6. **Tests are truth.** Fix code first; change tests only if clearly wrong spec.
7. **Minimal diff.** Add tests before code. Keep simple.
8. **Consistency > cleverness.** Follow SOPs and stack idioms.
9. **Memory multiplies.** Persist decisions, patterns, error signatures, proven fixes.
10. **Files ≤ 1000 lines.** Exceed → refactor.
11. No docs/summaries/comments unless requested.
12. No `--autogenerate` for Alembic migrations; write manually.
13. No `cat` to create files; use tools.
14. Log: `logger.debug` default, `.info` important, `.warning/.error` issues. **No `print`.**

> Prefer *local* changes over cross-module refactors.

---

## 1) Development Workflow

**Task Runner:** `task` (via `Taskfile.dist.yml`), not `make`.

- `task test`
- `task lint`
- `task run`
- `task --help`

### Plan

Create a plan block at task start:

```markdown
<!-- plan:start
goal: <one line clear goal>
constraints:
- Python 3.14; Reflex UI; FastAPI; SQLAlchemy 2.0; Alembic; Pydantic; appkit_mantine; appkit_commons;
- logging: no f-strings in logger calls
- files ≤ 1000 lines; apply design patterns where appropriate
- minimal diff; add/adjust tests first
definition_of_done:
- tests pass; coverage ≥ 80% (non-Reflex classes & Reflex states); lint/type checks clean; memory updated
steps:
1) Search Memory for "<keywords>"
2) Draft/adjust failing test to capture expected behavior
3) Implement minimal code change
4) Run task test; iterate until green
5) Update Memory: decisions, patterns, error→fix
plan:end -->
```

### Implement

1. `task sync` (uv, Python 3.14) then `task test` — baseline failures.
2. Tests-first. No `print` — use `logging`. No f-strings in logger calls:

   ```python
   log = logging.getLogger(__name__)
   log.info("Loaded %d items", count)  # ✅
   # log.info(f"Loaded {count} items") # ❌
   ```

3. After every code change, run `task lint` — not just at PR time.

### Ship

- `task format && task lint && task test` — coverage ≥ **80%** non-Reflex classes & Reflex states.
- Conventional Commits (`feat:`, `fix:`, `refactor:`…).
- PR: description, `Closes #123`, UI screenshots, migration rationale.
- Dependencies: `uv add <package>`. Write learnings to Memory.

---

## 2) Tooling Decision Matrix

| Situation | Primary | Secondary | Store to Memory |
| --- | --- | --- | --- |
| API/pattern uncertainty | **Context7** | — | Canonical snippet + link; edge cases |
| Ecosystem bug/issue | **DuckDuckGo** | Context7 | Minimal repro; versions; workaround |
| Repeated test failure | **Memory (search)** | Context7 | Error signature → fix; root cause |
| New feature scaffold | **Context7** | — | How‑to snippet; checklist |
| House style/tooling | **This file** | Context7 | Checklist results |

Prefer official docs; widen via web search for cross-version issues.

---

## 3) Python Code & Testing

Full rules in **python-coding** skill. Key:

- Line length **88**; type annotations on all functions/methods.

---

## 4) Reflex Best Practices

Full rules in **reflex-state-and-architecture** skill. Appkit-specific:

- **Substates & Mixins:** State vars on main class; methods split by concern in mixins.
- **Background Task Chaining:** Yield class method ref: `yield MyState.background_task`.
- **rx.cond operators:** `&` and `|`, not `and`/`or`.
- **DB Access:** No `rx.session()` in background/callbacks/utils. Use `appkit_commons.database.session_manager.get_session_manager().session()`.

---

## 5) appkit_mantine Components

Full API in **appkit-mantine-reference** skill. Rules:

- `import appkit_mantine as mn` — Mantine 9.2.0.
- Never redeclare inherited props — `MantineComponentBase` → `MantineLayoutComponentBase` → `MantineInputComponentBase` provide ~40 common props.
- `MantineProvider` auto-injected at priority 44 — no manual wrap.

---

## 6) Security & Config

- No credentials in code/history; `.env` local, Key Vault prod.
- Non-secret YAML; env `__` override pattern.
- Parameterized logs; no sensitive values.
- `SecretStr` → `.get_secret_value()`.
- Update vulnerable deps; document CVE-driven updates in commits & Memory.

---

## 7) Pre‑PR Checklist

- [ ] Tests added/updated; all green
- [ ] Coverage ≥ 80% non-Reflex classes & Reflex states
- [ ] `task format && task lint` pass
- [ ] No file > 1000 lines
- [ ] Design patterns applied
- [ ] Migrations reviewed & documented
- [ ] Memory updated (decisions, patterns, error→fix)
- [ ] PR description complete; links/screenshots added

---

## 8) Skills

| Skill | Purpose |
| --- | --- |
| `python-coding` | Python 3.14 style, logging, type annotations, design patterns, testing |
| `python-clean-code` | Clean Code Developer (CCD) architecture and quality principles |
| `reflex-state-and-architecture` | State design, event handlers, background tasks, form validation, page factory, service registry, repo pattern, DB models, architecture |
| `appkit-mantine-reference` | Full API for appkit_mantine components — inputs, layout, overlays, charts, data display, navigation |
| `appkit-commons` | appkit-commons usage patterns |
| `reflex-testing-state` | Pytest unit tests for Reflex State — event handlers, computed vars, substates |
| `reflex-docs` | Reflex.dev framework documentation |
| `docker-multi-stage` | Optimized multi-stage Dockerfiles, layer caching, security, healthchecks |
| `frontend-design` | Create distinctive, production-grade frontend interfaces |
