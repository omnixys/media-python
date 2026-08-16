<!-- repository: packages/python/media | kind: PACKAGE | stack: python-package -->

# media — Skill: Package Development

> Workflow for media (packages/python/media). Execute this workflow before, during, and
> after changes in this repository.

## Repository Facts

- Kind: Shared Package
- Package: `omnixys-media` (version: dynamic)
- Runtime: Python >=3.14 (uv)
- Description: Omnixys shared media/storage package (S3/MinIO with aiobotocore).
- Architecture: src/media/ S3/MinIO storage adapters
- Database: n/a; Migrations: n/a
- API: n/a
- Messaging: n/a
- Tests: pytest (tests/ directory); ruff select=ALL; mypy strict with pydantic/sqlalchemy plugins


## Workflow

### 1. Understand the change

- Identify consumers of this package across `omnixys/services` and other packages.
- This package is published (`omnixys-media`); consumers pin versions and rely on SemVer.

### 2. Implement

- Keep the public API surface explicit and intentional.
- For TypeScript packages, generated/transpiled output (e.g. `dist/`) must not be hand-edited.
- Reuse established Omnixys packages where relevant.

### 3. Write tests

- Unit tests exercise public API behavior and edge cases.
- Type tests are included where the package defines a `type-tests` suite.
- Verify exports compile from a consumer perspective.

### 4. Validate

## Validation

Run each applicable check and record the result as `PASS`, `FAIL`, `PRE-EXISTING
FAILURE`, or `NOT RUN` (with a reason). Never convert `NOT RUN` into `PASS`.

  - `uv sync --frozen`
  - `uv run ruff format --check src/`
  - `uv run ruff check src/`
  - `uv run mypy src/`
  - `uv run pytest`
  - `uv build (hatchling)`

## Commit

- Use Conventional Commits (`<type>(<scope>): <summary>`), e.g. `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `ci`, `perf`.
- Stage only files belonging to the logical change. Run `git diff --check` before committing.
- Commit locally; never push.

## Definition of Done

See the "Definition of Done" section in `AGENTS.md`. Before finishing, confirm
`AGENTS.md` and `SKILL.md` remain accurate for this repository.
