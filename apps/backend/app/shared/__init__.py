"""Shared kernel — the only package every module may import (ADR-017).

Contains what is genuinely cross-cutting: configuration, request identity, and (from
Phase 5.5a) telemetry. It imports **nothing** from any business module; `import-linter`
enforces that, because the rule is what makes the other two layers mean anything.
"""
