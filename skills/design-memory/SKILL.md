---
name: design-memory
description: >
  Manage a local vector store of design docs, decision records, and design patterns across
  all repos. Use this skill whenever the user wants to: index a design doc or decision record
  into the team's design memory, search for prior design decisions relevant to current work,
  get context from past decisions before starting a new design session, check what's in
  the design store, discover or manage design patterns, or remove outdated entries. Also
  trigger when the user mentions "design memory", "prior decisions", "what have we decided
  about", "index this doc", "design history", "what pattern do we use", "how do we handle",
  or wants to feed past decisions into a superpowers brainstorm session. This skill works
  across repos — it maintains a single global store at ~/.design-memory/. Trigger this skill
  even when the user just finished a brainstorm/design session and might benefit from indexing
  the result, when starting new design work that could benefit from prior context, or when
  asking about established team patterns and conventions.
---

# Design Memory

A cross-repo vector store for design docs and decision records, built on ChromaDB
with Gemini `text-embedding-004` embeddings via Application Default Credentials.
Persists at `~/.design-memory/`.

## Dependencies

Install into the skill's venv:

```bash
python3 -m venv ~/.claude/skills/design-memory/.venv
~/.claude/skills/design-memory/.venv/bin/pip install -r ~/.claude/skills/design-memory/requirements.txt
```

Requires: `chromadb`, `google-genai`, `pyyaml`

One-time auth setup:

```bash
gcloud auth application-default login
```

## Core Script

All operations go through:

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py <command> [args]
```

## Frontmatter Schema

Design docs should use YAML frontmatter for structured metadata:

```yaml
---
title: Retry semantics for connector HTTP calls
date: 2026-03-10
repo: dlcon-gcs-storage
services: [dlcon-gcs-storage, dlcon-az-storage, dlcon-s3-storage]
tags: [infrastructure, api-design]
status: active              # active | superseded | draft
superseded_by:              # relative path to newer doc if superseded
related: []                 # relative paths to related design docs
human_reviewed: true
decisions:
  - Use Resilience4j at HTTP client layer
  - Dead letter to Postgres not Kafka
  - 3 max retries with exponential backoff
---
```

**Required fields:** `title`, `date`, `repo`, `status`, `decisions`

**Optional fields:** `services` (defaults to `[repo]`), `tags`,
`superseded_by`, `related`, `human_reviewed` (defaults to `false`)

**Tag vocabulary** (use consistently for filtered retrieval):
`data-modeling`, `api-design`, `infrastructure`, `clinical`, `workflow`, `auth`,
`frontend`, `testing`, `devops`, `performance`, `security`, `observability`,
`tenant-isolation`, `data-pipeline`, `event-driven`

## Decision Confidence Tiers

Tag each decision in the document body with its confidence tier:

**Tier 1 — Human Decision** (highest confidence): engineer explicitly chose this.

```markdown
[HUMAN DECISION]
We chose Resilience4j over Spring Retry because...
[/HUMAN DECISION]
```

**Tier 2 — Confirmed Decision** (medium confidence): AI proposed, engineer approved.

```markdown
[CONFIRMED DECISION]
AI proposed Postgres for dead letter storage. Engineer confirmed.
[/CONFIRMED DECISION]
```

**Tier 3 — AI Decision** (lower confidence): AI decided, engineer didn't weigh in.

```markdown
[AI DECISION]
Selected OpenAPI 3.1 over AsyncAPI since all interfaces are REST.
[/AI DECISION]
```

The `decisions` frontmatter field is a flat summary of all decisions (all tiers).
The body blocks carry reasoning and are the authoritative source of tier info.
Decisions without a body block default to AI tier.

## Commands

### 1. Index a design doc

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py index <file_or_directory> \
    [--repo <source-repo-name>] \
    [--services <comma,separated,services>] \
    [--tags <comma,separated,tags>] \
    [--human-reviewed] \
    [--human-decisions "Decision 1|Decision 2"]
```

When frontmatter is present, metadata is extracted automatically — no CLI flags
needed. CLI flags override frontmatter values when both are present.

`--repo` auto-detects from git if omitted and not in frontmatter.

`--services` is which services this decision *applies to* (may differ from
`--repo`). Defaults to `[repo]`.

`--human-reviewed` marks docs where a human actively shaped the content. Always
ask the user before setting this.

`--human-decisions` overrides the frontmatter `decisions` list with explicit
pipe-delimited human decisions.

Files over 500KB are skipped with a warning.

**What to index vs skip:**
- Index: design docs with decisions, rationale, and tradeoffs; ADRs; normative
  API specs; architecture docs
- Skip: implementation plans (they go stale); raw brainstorm output; boilerplate

### 2. Query for prior decisions

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py query "<search text>" \
    [--top-k 5] \
    [--repo <filter-by-repo>] \
    [--service <filter-by-service>] \
    [--tags <filter-by-tags>] \
    [--decisions-only]
```

Results are deduplicated by source file (highest-similarity chunk per doc).

### 3. Generate context for brainstorm integration

This is the primary integration point with superpowers brainstorm.

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py context "<topic>" \
    [--top-k 5] \
    [--service <filter-service>] \
    [--repo <filter-repo>] \
    [--tags <filter-tags>] \
    [--min-similarity 0.3]
```

Outputs an XML `<prior_design_decisions>` block with decisions grouped by
confidence tier: human first, then confirmed, then AI. Results are deduplicated
and filtered by min-similarity (default 0.3).

### 4. Status, list, remove

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py status

~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py list [--repo <name>]

~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py remove <filename> [--force]
```

`remove` shows what would be deleted by default. Add `--force` to actually delete.
Uses exact filename matching (not substring).

## Design Patterns

Patterns are cross-cutting generalizations extracted from multiple decisions. While a
decision is a specific choice in a specific context, a pattern is an established convention:
"When [situation], we use [approach] because [rationale]."

Patterns live in a separate `design_patterns` ChromaDB collection alongside `design_docs`.
They have their own lifecycle (draft → active → superseded) and confidence levels derived
from supporting evidence.

### Pattern Commands

#### Add a pattern manually

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns add \
    "When building REST APIs, we use cursor-based pagination because offset-based breaks under concurrent writes" \
    --name "REST Cursor Pagination" \
    --category api-design \
    --evidence retry-semantics.md,api-standards.md
```

Manual patterns start as `active` status. The `--evidence` flag takes comma-separated
filenames that must already be indexed in design_docs.

#### Extract patterns via AI

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns extract \
    [--tags api-design,infrastructure] \
    [--repo my-service] \
    [--min-evidence 2] \
    [--cluster-threshold 0.70] \
    [--dry-run]
```

Clusters related decisions by semantic similarity, then uses Gemini to synthesize
pattern statements. AI-extracted patterns start as `draft` — use `patterns confirm`
to promote to `active`.

Use `--dry-run` first to preview clusters without making LLM calls.

#### Query patterns

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns query "how do we paginate" \
    [--top-k 5] \
    [--category api-design] \
    [--status active]
```

#### List, show, remove patterns

```bash
# List all patterns
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns list \
    [--category api-design] [--status active] [--confidence human]

# Show pattern details with full evidence
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns show <pattern_id_or_name>

# Remove a pattern
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns remove <pattern_id> [--force]
```

#### Pattern lifecycle

```bash
# Promote draft to active
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns confirm <pattern_id>

# Mark as superseded by a newer pattern
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns supersede <old_id> <new_id>

# Re-evaluate evidence from current indexed docs
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py patterns refresh [<pattern_id>] [--all]
```

### Pattern Confidence

Pattern confidence is derived from the highest tier in its evidence:
- **human**: at least one evidence decision is a `[HUMAN DECISION]`
- **confirmed**: highest evidence tier is `[CONFIRMED DECISION]`
- **ai**: all evidence is AI-extracted or `[AI DECISION]`

Confidence auto-upgrades when higher-tier evidence is added.

### Patterns in Context Output

The `context` command automatically includes active patterns in its XML output:

```xml
<design_patterns>
<pattern name="REST Cursor Pagination" confidence="human" evidence="3 decisions" category="api-design">
When building REST APIs, we use cursor-based pagination because offset-based breaks under concurrent writes.
Sources: retry-semantics.md, api-standards.md, search-api-design.md
</pattern>
</design_patterns>
```

Use `--no-patterns` to suppress patterns in context output.

### Post-Index Pattern Check

Use `--check-patterns` on the index command to check newly indexed decisions
against existing patterns:

```bash
~/.claude/skills/design-memory/.venv/bin/python \
  ~/.claude/skills/design-memory/scripts/design_memory.py index docs/ --check-patterns
```

## Integrating with Superpowers Brainstorm

Add the following to your global `~/.claude/CLAUDE.md`. Since superpowers reads
CLAUDE.md during brainstorm's "explore project context" step, this makes the
integration automatic.

```markdown
## Design Memory

Design decisions are tracked across repos using the design-memory skill.
The vector store lives at ~/.design-memory/ and the skill at
~/.claude/skills/design-memory/.

### Before brainstorming

When starting any design or brainstorm session:
1. Run `~/.claude/skills/design-memory/.venv/bin/python
   ~/.claude/skills/design-memory/scripts/design_memory.py
   context '<topic>' --top-k 5` where `<topic>` summarizes what you're
   about to design. If working on a specific service, add
   `--service <service-name>`.
2. Summarize relevant prior decisions and note which you'll align with
   or diverge from.

### During spec writing

When writing design specs to `docs/superpowers/specs/`:
1. Add YAML frontmatter (title, date, repo, services, tags, status,
   decisions).
2. Tag each decision in the body with its confidence tier:
   - `[HUMAN DECISION]...[/HUMAN DECISION]` — engineer explicitly chose
   - `[CONFIRMED DECISION]...[/CONFIRMED DECISION]` — AI proposed,
     engineer approved
   - `[AI DECISION]...[/AI DECISION]` — AI decided, engineer didn't
     weigh in
3. List all decisions (all tiers) in the frontmatter `decisions` field.

### After design sessions

When a brainstorm produces a committed spec:
1. Ask: "Should I index this into design memory?"
2. If yes, run the index command with appropriate flags.
3. Confirm what was indexed and current store stats.
```

## Workflow Patterns

### Pattern A: Pre-brainstorm context loading

1. Understand the topic from the ticket or user description
2. Run `context` with a descriptive search covering the key concepts
3. If a specific service is the focus, use `--service` to narrow results
4. Present a brief summary: "I found N prior decisions relevant to this work.
   Key prior choices: [list human decisions]. I'll keep these in mind."
5. Proceed with the brainstorm, referencing prior decisions where relevant

### Pattern B: Post-brainstorm indexing

1. Ask: "Did you review and shape this design doc? Should I index it?"
2. If yes, ask: "Which services does this apply to beyond [current repo]?"
3. Index — frontmatter is parsed automatically, no flags needed for well-formed docs
4. Confirm with stats

### Pattern C: Cross-repo pattern discovery

1. Run `query` without repo or service filter
2. Group results by service
3. Highlight convergence vs divergence across services
4. If divergence exists, check which approaches are human-reviewed
5. Suggest whether a shared standard should be established

### Pattern D: Decision archaeology

1. Run `query` with the specific topic
2. Filter to `--decisions-only` for cleaner results
3. Surface the human decisions and rationale
4. Note which repo and when the decision was indexed

### Pattern E: Pattern discovery and enforcement

1. Run `patterns extract --dry-run` to preview potential patterns
2. If clusters look good, run `patterns extract` to synthesize via LLM
3. Review drafts with `patterns list --status draft`
4. Use `patterns show <id>` to inspect evidence
5. `patterns confirm <id>` for patterns that reflect real conventions
6. `patterns remove <id> --force` for false positives
7. Run `patterns refresh --all` periodically to keep evidence current

### Pattern F: Answering "what pattern do we use for X?"

1. Run `patterns query "X"` (e.g., `patterns query "CLI command structure"`)
2. If a matching active pattern exists, present it with its evidence
3. If no pattern matches but related decisions exist, suggest running
   `patterns extract --tags <relevant-tag>` to discover implicit patterns
4. If creating a new pattern manually, use `patterns add` with evidence links
