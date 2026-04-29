# Changelog

Все заметные изменения проекта «Шурочка» (shura v2) документируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/).

Категории: `Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`.

Раздел `[Unreleased]` накапливает изменения до момента, когда они получат версию
или будут перенесены в новый релизный заголовок вручную.

## [Unreleased] — 2026-04-29

### Added
- `.claude/agents/docs-keeper.md` — субагент автообновления `CHANGELOG.md` и `PROJECT_INDEX.md` (`/update-docs`); модель `claude-sonnet-4-6` для качественного аудита и описаний новых файлов.
- `.claude/skills/docs-keeper/SKILL.md` — скилл-триггер для агента.
- `.claude/hooks/track_changes.py` — `PostToolUse`-хук, накапливает список изменённых `.py`/`.md` в `%TEMP%`.
- `.claude/hooks/changelog_reminder.py` — `Stop`-хук, в конце сессии напоминает про незафиксированные изменения.
- `CHANGELOG.md` — этот файл, инициализирован.

### Changed
- `CLAUDE.md` — добавлена секция «Documentation map» с указателями на `PROJECT_INDEX.md`, `CHANGELOG.md`, `README.md`, `MIGRATION_PLAN.md` и описанием агента `docs-keeper`.
