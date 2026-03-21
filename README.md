# Skills

A personal collection of Claude skills — structured prompt packages that give Claude specialized capabilities for complex, multi-step tasks.

Each skill lives in its own directory and follows the Claude skill format: a `SKILL.md` entry point, optional agent prompts, reference documents, and helper scripts.

## Available Skills

| Skill | Description |
|-------|-------------|
| [consensus-planning](skills/consensus-planning/) | Multi-agent consensus planning system. Spawns a panel of AI analysts with diverse analytical perspectives to collaboratively solve problems through structured rounds of critique, revision, and assessment. |
| [design-memory](skills/design-memory/) | Cross-repo vector store for design docs, decision records, and design patterns. Index, query, and surface prior design decisions and established patterns before brainstorming or spec writing. Includes AI-assisted pattern extraction from clustered decisions. Built on ChromaDB with Gemini embeddings. |

## Skill Structure

All skills live under the `skills/` directory. Each skill follows this convention:

```
skills/
└── <skill-name>/
    ├── <skill-name>/
    │   ├── SKILL.md              # Entry point — orchestration instructions
    │   ├── agents/               # Agent prompt templates (if multi-agent)
    │   ├── references/           # Schemas, guides, templates
    │   └── scripts/              # Helper scripts
    ├── README.md                 # Human-readable documentation
    └── CLAUDE.md                 # Developer/AI-facing reference
```

The inner `<skill-name>/` directory is what gets loaded as the skill. The outer directory holds documentation and any supporting files.

## Adding a New Skill

1. Create a directory under `skills/` named after the skill
2. Inside it, create another directory with the same name containing `SKILL.md`
3. Add agent prompts, references, and scripts as needed
4. Add a `README.md` alongside the inner directory documenting the skill for humans
5. Add a `CLAUDE.md` with architecture notes, modification guides, and testing instructions
6. Update this table with the new skill

## Usage

These skills can be installed into Claude by pointing it at the skill directory. Trigger phrases and activation instructions are documented in each skill's `SKILL.md` frontmatter.
