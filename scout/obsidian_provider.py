"""
ObsidianContextProvider — read + write access to an Obsidian vault.
====================================================================

Same surface as ``WikiContextProvider`` (``query_<id>`` + ``update_<id>``),
but pre-configured for an Obsidian vault:

- ``FileSystemBackend`` rooted at the vault — no git commits from this
  provider (the vault has its own auto-commit cron).
- Excludes Obsidian's local-only state (``.obsidian/``, ``.trash/``) and
  vault meta (``_vault/``). The exclusion applies to reads AND writes —
  ``Workspace.exclude_patterns`` only filters listing/search by default,
  so we subclass to extend the guard to ``write_file`` / ``edit_file``.
- Instructions bake the vault's 7-folder taxonomy, the canonical Inbox
  filename format, and the scout-originated frontmatter contract into
  the read + write sub-agents.

The provider lives in ``scout`` (not ``agno``) until it's stable enough
to upstream into ``agno.context.obsidian``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from agno.context.mode import ContextMode
from agno.context.wiki import FileSystemBackend, WikiContextProvider
from agno.tools.workspace import Workspace

if TYPE_CHECKING:
    from agno.models.base import Model


# Path components Scout must not read or write inside an Obsidian vault.
# Reads are excluded for context-pollution reasons (Obsidian plugin
# caches, sync metadata); writes are excluded as a safety invariant
# (HANDBOOK, workflow JSON, templates are operator territory).
#
# `Workspace.exclude_patterns` is matched per-component via `fnmatch`
# (see agno.tools._local_file_utils.path_matches_exclude), so these are
# bare names — NOT glob paths like `_vault/**`, which never match.
OBSIDIAN_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "_vault",
    ".obsidian",
    ".trash",
    ".stfolder",
    ".mise",
)


class _ObsidianWriteWorkspace(Workspace):
    """Workspace that refuses to write or edit excluded paths.

    Upstream ``Workspace.exclude_patterns`` only filters listing and
    search; ``write_file`` / ``edit_file`` don't consult them. For the
    vault, the ``_vault/**`` exclusion is a real safety invariant, so
    we extend the guard here.
    """

    def write_file(self, path: str, content: str, overwrite: bool = True, encoding: str = "utf-8") -> str:
        safe, file_path = self._check_path(path, self.root)
        if safe and self._is_excluded(file_path):
            return f"Error: writes to {path!r} are not allowed (path is in the vault's excluded zone)"
        return super().write_file(path, content, overwrite=overwrite, encoding=encoding)

    def edit_file(
        self,
        path: str,
        old_str: str,
        new_str: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> str:
        safe, file_path = self._check_path(path, self.root)
        if safe and self._is_excluded(file_path):
            return f"Error: edits to {path!r} are not allowed (path is in the vault's excluded zone)"
        return super().edit_file(path, old_str, new_str, replace_all=replace_all, encoding=encoding)


class ObsidianContextProvider(WikiContextProvider):
    """Read + write access to an Obsidian vault via two tools.

    Subclass of ``WikiContextProvider`` that wires the vault-specific
    defaults — backend, exclusion patterns, write-guard, and the
    Obsidian-aware read + write instructions.
    """

    def __init__(
        self,
        *,
        vault_path: Path | str,
        id: str = "obsidian",
        name: str | None = "Obsidian Vault",
        mode: ContextMode = ContextMode.default,
        model: Model | None = None,
        read: bool = True,
        write: bool = True,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self.exclude_patterns: list[str] = (
            list(exclude_patterns) if exclude_patterns is not None else list(OBSIDIAN_EXCLUDE_PATTERNS)
        )
        super().__init__(
            backend=FileSystemBackend(path=Path(vault_path)),
            id=id,
            name=name,
            mode=mode,
            model=model,
            read=read,
            write=write,
            read_instructions=OBSIDIAN_READ_INSTRUCTIONS,
            write_instructions=OBSIDIAN_WRITE_INSTRUCTIONS,
        )

    def _build_read_tools(self) -> Workspace:
        return Workspace(
            root=self.backend.path,
            allowed=Workspace.READ_TOOLS,
            exclude_patterns=self.exclude_patterns,
        )

    def _build_write_tools(self) -> Workspace:
        return _ObsidianWriteWorkspace(
            root=self.backend.path,
            allowed=["read", "list", "search", "write", "edit"],
            exclude_patterns=self.exclude_patterns,
        )


def obsidian_inbox_filename(slug: str, *, when: datetime | None = None) -> str:
    """Build the canonical Inbox filename for scout-originated captures.

    Format: ``YYYY-MM-DD-HHMMSS-scout-<slug>-<4hex-nonce>.md``.

    Second-level precision plus a 4-hex-char nonce so two scout
    sessions writing within the same second can't collide. The slug
    is the agent's responsibility — keep it short and kebab-case.
    """
    when = when or datetime.now(timezone.utc)
    nonce = secrets.token_hex(2)
    return f"{when:%Y-%m-%d-%H%M%S}-scout-{slug}-{nonce}.md"


OBSIDIAN_READ_INSTRUCTIONS = """\
You answer questions by reading the user's Obsidian vault at {path}.

The vault is organised into 7 top-level folders, each answering a single
question. Use this to decide where to look:

- `Inbox/`    — new and unprocessed (Telegram captures, daily briefs, weekly syntheses)
- `Notes/`    — external content the user is consuming (Readwise highlights, papers, transcripts)
- `Ideas/`    — the user's own writing (essays, observations, drafts)
- `Projects/` — bounded work with a deliverable (33GOD, Intelliforia, JobHunting, …)
- `Domains/`  — ongoing life zones (Family, Finance, Music, Home, Me)
- `Journal/`  — date-anchored (Dailies/, 33GOD dated brainstorms, done-tasks)
- `_vault/`   — vault operations — EXCLUDED, you will not see these files

`CLAUDE.md` at the vault root is the user's session-start context (who
they are, current projects, what they're thinking about). Read it when
the question is about *the user*.

## Workflow

1. **Map first.** `list_files(recursive=True, max_depth=2)` on the
   folder(s) you think the answer lives in. Don't guess filenames.
2. **Search by content.** `search_content(query)` surfaces pages whose
   text matches; cheaper than reading every file.
3. **Quote what you cite.** `read_file(path)` for pages you actually
   quote. Don't paraphrase notes — quote the text.
4. **Cite vault-relative paths.** `Notes/foo.md`, not absolute.

Many files carry frontmatter with `source`, `captured`, `tags`. Use
these when the question is "where did this come from" or "when did I
capture this".

You are read-only. Writes happen through the update tool.
"""


OBSIDIAN_WRITE_INSTRUCTIONS = """\
You file notes into the user's Obsidian vault at {path}.

## Default destination: Inbox/

Unless the user explicitly names a folder, write new files to `Inbox/`.
The vault's filing rule is "when in doubt, Inbox" — the daily brief and
weekly synthesis will surface the keepers later.

## Filename convention for new scout-originated files

`Inbox/YYYY-MM-DD-HHMMSS-scout-<kebab-slug>-<4hex-nonce>.md`

Example: `Inbox/2026-05-11-104530-scout-hindsight-bank-routing-a3f2.md`

Pick a short kebab-case slug from the note's topic. The nonce prevents
collisions between concurrent scout sessions writing within the same
second; if you can't generate random hex, use `noid` and the provider
will accept it.

## Frontmatter contract

Every new markdown file you create MUST start with this YAML block:

```yaml
---
source: scout-<origin>          # scout-web, scout-followup, scout-user, scout-research, ...
captured: YYYY-MM-DD
captured_at: YYYY-MM-DDTHH:MM:SSZ
tags: [scout-generated, <topic-tags>]
---
```

Then a `# Title` heading, then the body.

## Allowed paths

The toolkit will refuse writes under `_vault/`, `.obsidian/`, `.trash/`,
or `.stfolder/`. Don't try them. If the user asks you to "update the
HANDBOOK", explain that the handbook lives in `_vault/` and is
operator-managed.

Editing existing notes in `Notes/`, `Ideas/`, `Projects/`, `Domains/`,
or `Journal/` is fine — `read_file` first so your `old_str` is exact,
then `edit_file`. Preserve existing frontmatter unless asked otherwise.

## Reporting

After writing, return one sentence with the vault-relative path:

  Saved `Inbox/2026-05-11-104530-scout-hindsight-bank-routing-a3f2.md`.

Don't dump file contents. Don't invoke git — the vault has its own
auto-commit cron.
"""
