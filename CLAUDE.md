# CLAUDE.md — Skills Repository

## What This Is

A personal collection of Claude skills. Each skill is a self-contained prompt package that gives Claude specialized capabilities for complex tasks. Skills are organized one-per-directory at the repo root.

## Repo Layout

```
skills/                             # The repo
├── README.md                       # Repo overview and skill index
├── CLAUDE.md                       # This file
├── .gitignore
└── skills/                         # All skills live here
    └── open-parliament/            # One directory per skill
        ├── open-parliament/        # Inner dir is the installable skill
        │   ├── SKILL.md            # Entry point
        │   ├── agents/             # Agent prompts
        │   ├── references/         # Schemas, templates, guides
        │   └── scripts/            # Helper scripts
        ├── README.md               # Skill-specific human docs
        └── CLAUDE.md               # Skill-specific dev/AI docs
```

## Conventions

Each skill lives under `skills/` and follows a double-directory pattern: `skills/<name>/<name>/SKILL.md`. The outer directory holds documentation (README.md, CLAUDE.md). The inner directory is the installable skill itself — what gets loaded when the skill is activated.

SKILL.md is always the entry point. It contains the orchestration instructions that Claude follows when the skill is triggered. Frontmatter at the top of SKILL.md declares the skill's name, description, and trigger phrases.

## Adding a Skill

1. Create `skills/<skill-name>/` under the skills directory
2. Create `skills/<skill-name>/<skill-name>/SKILL.md` with frontmatter and instructions
3. Add supporting files (agents/, references/, scripts/) inside the inner directory
4. Add `skills/<skill-name>/README.md` for human documentation
5. Add `skills/<skill-name>/CLAUDE.md` for architecture and modification notes
6. Update the root README.md skills table

## Current Skills

- **open-parliament** — Multi-agent parliamentary deliberation. Spawns representative agents with temperature-based personalities to debate problems through structured rounds. See `skills/open-parliament/CLAUDE.md` for architecture details.

## Runtime Artifacts

Skills may generate runtime files (JSON session state, ledger files, output documents) during execution. These are created in a `parliament/` or similar working directory at runtime — not checked into the repo. The `.gitignore` excludes common patterns.

## No External Dependencies

All scripts use Python 3 standard library only. No pip installs required.
