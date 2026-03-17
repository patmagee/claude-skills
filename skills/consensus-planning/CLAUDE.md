# CLAUDE.md — Consensus Planning

## What This Is

A Claude skill that orchestrates multi-agent consensus planning. Spawns analyst
agents (via the Agent tool) that critique a proposal through structured rounds.
A facilitator agent manages procedure. A review agent validates output. The user
has final authority.

Entry point: `SKILL.md`.

## Layout

```
consensus-planning/
├── SKILL.md                         # Orchestration instructions (entry point)
├── agents/
│   ├── facilitator.md               # Facilitator agent prompt
│   ├── analyst.md                   # Analyst agent prompt
│   └── reviewer.md                  # Review agent prompt
├── references/
│   └── schemas.md                   # JSON schemas for messages, state, proposal
└── scripts/
    ├── init_session.py              # Creates session.json, log.json, proposal.json
    ├── reassign_perspectives.py     # Re-rolls perspectives + updates debate clock
    └── append_to_log.py             # Appends messages to log
```

## Architecture

Hub-and-spoke. The orchestrator (SKILL.md) is the hub. All communication flows
through a shared **log** (`planning/log.json`). Agents don't talk directly —
the orchestrator mediates by appending output to the log and directing agents
to read it.

**Context-lean orchestration**: The orchestrator never reads reference files,
agent prompts, or the full log. Subagents read their own files.

Runtime state files (in `planning/`):
- `session.json` — Roster, perspectives, round counter, debate clock, status
- `log.json` — All messages (shared memory)
- `proposal.json` — Current proposal with revision tracking
- `round-summaries.json` — Compressed summaries for context windowing (after round 1)

## Key Mechanics

**Perspective scores** (0-100): Shape analyst style. Four modes: Bold (75-100),
Balanced (50-74), Critical (25-49), Conservative (0-24). Stratified random
assignment with convergence pressure (5-95 narrowing to 35-65 over 6 rounds).

**Session phases**: Discovery (clarifying questions) → Brainstorm (parallel
analysis) → Draft → Refine (up to 6 rounds) → Review → Deliver.

**Debate clock**: Exchange count shrinks from 2x to 1x analysts. Sentence
budget shrinks from 6 to 2. Constants in `scripts/reassign_perspectives.py`.

**Dissent pressure**: (1) Priority satisfaction scores 1-5 on every response,
(2) Stance guard limits concessions in early rounds, (3) Assessment gating
prevents votes while priorities are below 3.

**Review phase**: Independent reviewer evaluates completeness, feasibility,
risk coverage, and consensus quality before the user sees the final output.

## Scripts

All Python 3, standard library only.

- **init_session.py**: Creates state files. Stratified perspective assignment.
- **reassign_perspectives.py**: Convergence + debate clock update per round.
- **append_to_log.py**: Append messages with auto-generated metadata.

## Common Modifications

**Changing convergence**: Edit `CONVERGENCE_TABLE` in `reassign_perspectives.py`
and update the table in SKILL.md.

**Changing debate clock**: Edit `DEBATE_CLOCK_TABLE` in `reassign_perspectives.py`
and update the table in SKILL.md.

**Adding a message type**: Add to `references/schemas.md`, handle in SKILL.md,
add task to the relevant agent prompt.

**Adding an agent role**: Create prompt in `agents/`, add spawn instructions to
SKILL.md, define message types in schemas.

## Testing

```bash
python3 scripts/init_session.py \
  --working-dir /tmp/test \
  --num-analysts 5 \
  --problem "Test" \
  --analysts '[{"name":"A","priorities":["x"]},{"name":"B","priorities":["y"]},{"name":"C","priorities":["z"]},{"name":"D","priorities":["w"]},{"name":"E","priorities":["v"]}]'

for i in $(seq 6); do
  python3 scripts/reassign_perspectives.py --session-file /tmp/test/session.json
done
```

Expected: perspectives converge, debate clock tightens, round advances.
