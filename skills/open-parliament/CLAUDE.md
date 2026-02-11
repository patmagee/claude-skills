# CLAUDE.md — Open Parliament

## What This Project Is

Open Parliament is a Claude skill that orchestrates multi-agent deliberation. It spawns representative AI agents (via the Task tool) that debate a problem through structured rounds of Q&A, amendment, and voting. A Speaker agent manages procedure. The user acts as Prime Minister with veto power.

The skill entry point is `SKILL.md`. That file contains the full orchestration instructions that Claude follows when running a parliament session.

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
    ├── reassign_temperatures.py    # Re-rolls temps + updates debate clock each round
    └── append_to_ledger.py         # Appends messages to ledger without full read
```

## Architecture

The system uses a hub-and-spoke pattern. The orchestrator (the "Parliament Clerk" described in SKILL.md) manages all state and spawns subagents for each action:

- **Speaker subagent** — spawned for procedural decisions (select drafter, plan round, decide next action, evaluate vote)
- **Representative subagents** — spawned one at a time for Q&A exchanges, or in parallel for voting

All communication flows through a shared **ledger** (`parliament/ledger.json`). Agents don't talk directly to each other — the orchestrator mediates everything by appending agent output to the ledger (via `scripts/append_to_ledger.py`) and directing agents to read the ledger in their own context.

**Context-lean orchestration**: The orchestrator never reads reference files, agent prompts, or the full ledger. Subagents read their own files using their independent context windows. The orchestrator tracks only minimal state and delegates all heavy reading to subagents. See the Context Budget section in SKILL.md.

State files created at runtime:
- `parliament/session.json` — roster, temperatures (with history), round counter, debate clock, status
- `parliament/ledger.json` — ordered array of all messages (the shared memory)
- `parliament/bill.json` — current bill text with amendment tracking (including endorsements)
- `parliament/round-summaries.json` — compressed round summaries for context windowing (created after Round 1)

## Key Mechanics

**Temperature** (0–100): Shapes agent personality. Four archetypes: Visionary (75–100), Pragmatic Advocate (50–74), Rigorous Skeptic (25–49), Principled Guardian (0–24). All are constructive — no obstructionists. Assigned via stratified randomness with convergence pressure (range narrows from 5–95 to 35–65 over 6 rounds). Full details in `references/temperature-guide.md`. Temperature history is tracked per agent across rounds, and transition narratives are provided when an agent's temperature shifts by more than 15 points between rounds.

**Opening Statements**: Before any bill is drafted, all reps produce opening statements in parallel — each containing a domain briefing (facts, constraints, precedents) and a directional solution sketch. The Speaker synthesizes a shared fact base and identifies distinct solution directions. The PM reviews before drafting begins. This prevents single-perspective anchoring and surfaces domain knowledge early.

**Debate Clock**: Each round has a max exchange count (shrinks from 2×seats to 1×seats) and a sentence budget per agent response (shrinks from 6 to 2). Enforced by the Speaker. Defined in the `DEBATE_CLOCK_TABLE` in `scripts/reassign_temperatures.py` and mirrored in SKILL.md and `references/temperature-guide.md`.

**Observer Briefs**: The orchestrator reports to the user at three levels — narrative dispatch after each exchange, position tracker table after each round, full vote report after each vote. These are for the user only, never added to the ledger.

**Amendment Lifecycle**: proposed → debating → endorsed → incorporated/rejected/withdrawn. Tracked in both the ledger and `bill.json`. Endorsements are formally recorded via the `amendment_position` field on ANSWER messages. Incorporation requires proposer + 1 endorsement, or drafter acceptance.

**Motions**: Representatives can attach optional `motion` fields to QUESTION and ANSWER messages to make procedural requests (call votes, request compromises, etc.). The orchestrator extracts these as separate MOTION ledger entries for the Speaker to act on.

**Context Windowing**: To prevent context overflow in later rounds, older rounds are passed to agents as round summaries rather than full message logs. Only the current and previous round's messages are passed in full. The complete ledger is preserved on disk for final synthesis.

**Dissent Pressure**: Three mechanisms prevent premature consensus: (1) Motive satisfaction scores (1-5) on every ANSWER, tracked in session.json and used by the Speaker to direct debate; (2) Concession guard — reps can only maintain/challenge in rounds 1-2, soften in round 3, concede from round 4; (3) Vote-gating — Speaker cannot call a vote while any motive scores below 3 (unless forced by clock/round limit).

**Voting**: YES or NO only (no abstentions). 50%+ passes immediately. Every NO must include conditions for flipping. VOTE messages include final `motive_scores`.

## Communication Protocol

All agent messages are JSON. Eleven message types: OPENING_STATEMENT, BILL_DRAFT, QUESTION, ANSWER, AMENDMENT, MOTION, VOTE, SPEAKER_RULING, VOTE_TALLY, PM_DECISION. Agents return messages *without* `id`, `round`, or `timestamp` — the orchestrator fills those in using the `next_message_id` counter from session state. QUESTION and ANSWER messages may include an optional `motion` field that the orchestrator extracts as a separate MOTION entry. ANSWER and VOTE messages include required `motive_scores` for satisfaction tracking. ANSWER messages may include an optional `amendment_position` field for formal endorsement tracking. Full schemas in `references/communication-protocol.md`.

## Scripts

All Python 3 scripts are self-contained with no external dependencies.

**init_parliament.py**: Creates the three runtime JSON files. Takes `--working-dir`, `--num-seats`, `--problem`, `--representatives` (JSON array), and optionally `--issues`. Uses stratified assignment for initial temperatures. Initializes `debate_clock` with round-0 defaults and `temperature_history` per rep.

**reassign_temperatures.py**: Reads `session.json`, computes the next round's temperature range (convergence) and debate clock settings, re-rolls stratified temperatures, appends to `temperature_history`, advances `current_round`, and writes back. Run this at the start of each debate round.

**append_to_ledger.py**: Appends one or more messages to `ledger.json` with auto-generated `id`, `round`, and `timestamp` metadata. Increments `next_message_id` in `session.json`. Accepts a single JSON message or a JSON array. This is the primary mechanism for ledger writes — the orchestrator uses this script to avoid reading the full ledger into its own context window.

## Common Modifications

**Adding a new message type**: Add the schema to `references/communication-protocol.md`, add handling in SKILL.md's orchestration section, and add the task type to the relevant agent prompt (`agents/speaker.md` or `agents/representative.md`).

**Changing convergence speed**: Edit the `CONVERGENCE_TABLE` dict in `scripts/reassign_temperatures.py` and update the matching table in `references/temperature-guide.md` and the Convergence Pressure reference in SKILL.md.

**Changing debate clock pressure**: Edit the `DEBATE_CLOCK_TABLE` dict in `scripts/reassign_temperatures.py` and update the matching tables in SKILL.md and `references/temperature-guide.md`.

**Adding a new agent role**: Create a new prompt file in `agents/`, add spawn instructions to SKILL.md, and define any new message types in the communication protocol.

**Adjusting seat count limits**: The system works with 3–9 seats. Below 3 you lose meaningful debate; above 9 the rounds get very long. These limits are soft suggestions in SKILL.md Phase 1, Step 3.

## Session Phases

The session flows through 6 phases (status values in parentheses):

1. **Opening Parliament** (`setup`) — Interactive setup with the user
2. **Opening Statements** (`opening_statements` → `evaluating_statements`) — All reps produce statements, Speaker synthesizes, PM reviews
3. **Bill Drafting** (`drafting`) — Selected drafter writes initial bill informed by all statements
4. **Debate Rounds** (`debate` → `voting`) — Structured Q&A with amendments, motions, and votes
5. **PM Review** (`pm_review`) — User approves, vetoes, or amends
6. **Final Synthesis** (`synthesis` → `complete`) — Drafter produces final markdown document

## Testing

Run the scripts standalone to verify the math:

```bash
# Init with 5 agents
python3 scripts/init_parliament.py \
  --working-dir /tmp/test-parl \
  --num-seats 5 \
  --problem "Test" \
  --representatives '[{"name":"A","motives":["x"]},{"name":"B","motives":["y"]},{"name":"C","motives":["z"]},{"name":"D","motives":["w"]},{"name":"E","motives":["v"]}]'

# Run 6 rounds of reassignment to verify convergence + clock
for i in $(seq 6); do
  python3 scripts/reassign_temperatures.py \
    --session-file /tmp/test-parl/session.json
done
```

Expected: temperatures converge from full range to ~35–65, debate clock tightens from 10 exchanges / 6 sentences to 5 exchanges / 2 sentences, and `current_round` advances from 0 to 6.

## Style Notes

- Agent prompts use second person ("You are a Representative...")
- The orchestrator (SKILL.md) uses imperative instructions ("Spawn the Speaker...", "Append to the ledger...")
- Temperature archetypes use evocative names (Visionary, Guardian) but the system is domain-agnostic
- All tables in reference docs should stay in sync with the Python constants — there's no single source of truth, so check both when modifying
