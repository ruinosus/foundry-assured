"""Business modules — one package per bounded context (ADR-017).

Each module exposes `public.py` and hides everything else under `internal/`. A module may
import `app.shared` and other modules' `public`; never another module's `internal`, and never
the composition root. `import-linter` enforces all three.
"""
