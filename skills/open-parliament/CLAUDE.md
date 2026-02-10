# CLAUDE.md — Open Parliament

## What This Project Is

Open Parliament is a Claude skill that orchestrates multi-agent deliberation. It spawns representative AI agents (via the Task tool) that debate a problem through structured rounds of Q&A, amendment, and voting. A Speaker agent manages procedure. The user acts as Prime Minister with veto power.

The skill entry point is `open-parliament/SKILL.md`. That file contains the full orchestration instructions that Claude follows when running a parliament session.

## Project Layout

```
open-parliament/
├── SKILL.md                    # Main orchestration — read this first
├── agents/
│   ├── speaker.md              # Speaker agent prompt template
│   └── representative.md       # Representative agent prompt template
├── references/
│   ├── communication-protocol.md   # JSON schemas, ledger format, session state
│   ├── temperature-guide.md        # Temperature archetypes & convergence mechanics
│   └── bill-template.md            # Final bill markdown template (7 sections)
└── scripts/
    ├── init_parliament.py          # Creates session.json, ledger.json, bill.json
    └── reassign_temperatures.py    # Re-rolls temps + updates debate clock each round
```

## Architecture

The system uses a hub-and-spoke pattern. The orchestrator (the "Parliament Clerk" described in SKILL.md) manages all state and spawns subagents for each action:

- **Speaker subagent** — spawned for procedural decisions (select drafter, plan round, decide next action, evaluate vote)
- **Representative subagents** — spawned one at a time for Q&A exchanges, or in parallel for voting

All communication flows through a shared **ledger** (`parliament/ledger.json`). Agents don't talk directly to each other — the orchestrator mediates everything by reading agent output, appending it to the ledger, and passing the updated ledger to the next agent.

State files created at runtime:
- `parliament/session.json` — roster, temperatures, round counter, debate clock, status
- `parliament/ledger.json` — ordered array of all messages (the shared memory)
- `parliament/bill.json` — current bill text with amendment tracking

## Key Mechanics

**Temperature** (0–100): Shapes agent personality. Four archetypes: Visionary (75–100), Pragmatic Advocate (50–74), Rigorous Skeptic (25–49), Principled Guardian (0–24). All are constructive — no obstructionists. Assigned via stratified randomness with convergence pressure (range narrows from 5–95 to 35–65 over 6 rounds). Full details in `references/temperature-guide.md`.

**Debate Clock**: Each round has a max exchange count (shrinks from 2×seats to 1×seats) and a sentence budget per agent response (shrinks from 6 to 2). Enforced by the Speaker. Defined in the `DEBATE_CLOCK_TABLE` in `scripts/reassign_temperatures.py` and mirrored in SKILL.md and `references/temperature-guide.md`.

**Observer Briefs**: The orchestrator reports to the user at three levels — narrative dispatch after each exchange, position tracker table after each round, full vote report after each vote. These are for the user only, never added to the ledger.

**Amendment Lifecycle**: proposed → debating → incorporated/rejected/withdrawn. Tracked in both the ledger and `bill.json`.

**Voting**: YES or NO only (no abstentions). 50%+ passes immediately. Every NO must include conditions for flipping.

## Communication Protocol

All agent messages are JSON. Ten message types: BILL_DRAFT, QUESTION, ANSWER, AMENDMENT, MOTION, VOTE, SPEAKER_RULING, VOTE_TALLY, PM_DECISION. Agents return messages *without* `id`, `round`, or `timestamp` — the orchestrator fills those in using the `next_message_id` counter from session state. Full schemas in `references/communication-protocol.md`.

## Scripts

Both Python 3 scripts are self-contained with no external dependencies.

**init_parliament.py**: Creates the three runtime JSON files. Takes `--working-dir`, `--num-seats`, `--problem`, `--representatives` (JSON array), and optionally `--issues`. Uses stratified assignment for initial temperatures. Initializes `debate_clock` with round-0 defaults.

**reassign_temperatures.py**: Reads `session.json`, computes the next round's temperature range (convergence) and debate clock settings, re-rolls stratified temperatures, advances `current_round`, and writes back. Run this at the start of each debate round.

## Common Modifications

**Adding a new message type**: Add the schema to `references/communication-protocol.md`, add handling in SKILL.md's orchestration section, and add the task type to the relevant agent prompt (`agents/speaker.md` or `agents/representative.md`).

**Changing convergence speed**: Edit the `CONVERGENCE_TABLE` dict in `scripts/reassign_temperatures.py` and update the matching table in `references/temperature-guide.md` and the Convergence Pressure reference in SKILL.md.

**Changing debate clock pressure**: Edit the `DEBATE_CLOCK_TABLE` dict in `scripts/reassign_temperatures.py` and update the matching tables in SKILL.md and `references/temperature-guide.md`.

**Adding a new agent role**: Create a new prompt file in `agents/`, add spawn instructions to SKILL.md, and define any new message types in the communication protocol.

**Adjusting seat count limits**: The system works with 3–9 seats. Below 3 you lose meaningful debate; above 9 the rounds get very long. These limits are soft suggestions in SKILL.md Phase 1, Step 3.

## Testing

Run the scripts standalone to verify the math:

```bash
# Init with 5 agents
python3 open-parliament/scripts/init_parliament.py \
  --working-dir /tmp/test-parl \
  --num-seats 5 \
  --problem "Test" \
  --representatives '[{"name":"A","motives":["x"]},{"name":"B","motives":["y"]},{"name":"C","motives":["z"]},{"name":"D","motives":["w"]},{"name":"E","motives":["v"]}]'

# Run 6 rounds of reassignment to verify convergence + clock
for i in $(seq 6); do
  python3 open-parliament/scripts/reassign_temperatures.py \
    --session-file /tmp/test-parl/session.json
done
```

Expected: temperatures converge from full range to ~35–65, debate clock tightens from 10 exchanges / 6 sentences to 5 exchanges / 2 sentences, and `current_round` advances from 0 to 6.

## Style Notes

- Agent prompts use second person ("You are a Representative...")
- The orchestrator (SKILL.md) uses imperative instructions ("Spawn the Speaker...", "Append to the ledger...")
- Temperature archetypes use evocative names (Visionary, Guardian) but the system is domain-agnostic
- All tables in reference docs should stay in sync with the Python constants — there's no single source of truth, so check both when modifying
