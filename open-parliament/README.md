# Open Parliament

A multi-agent deliberation system modeled on representative democracy. Open Parliament spawns a parliament of AI agents — each with unique motives, constituent concerns, and a randomized "temperature" personality — to collaboratively solve problems through structured debate, amendment, and voting.

A **Speaker** agent enforces order, and the user holds veto power as **Prime Minister**.

## When to Use

Open Parliament works for any problem where competing concerns must be balanced:

- **Technical decisions**: architecture choices, technology selection, migration strategies
- **Business strategy**: market positioning, resource allocation, product direction
- **Policy design**: internal processes, compliance tradeoffs, organizational change
- **Creative problem-solving**: any question that benefits from adversarial collaboration across diverse viewpoints

It's most valuable when a problem is contentious — when there's no obvious right answer and multiple stakeholders have legitimate, competing priorities.

## How It Works

### Setup

The user describes a problem. The system identifies **constituent issues** (the concerns at stake) and seats a parliament of representative agents, each assigned 1–3 motives to advocate for.

### Temperature

Each agent gets a randomized **temperature** (0–100) that shapes their personality:

| Range | Archetype | Style |
|-------|-----------|-------|
| 75–100 | Visionary | Abstract, bold, synthesizes critiques into richer proposals |
| 50–74 | Pragmatic Advocate | Balances innovation with feasibility, builds coalitions |
| 25–49 | Rigorous Skeptic | Evidence-based, concise, demands specifics |
| 0–24 | Principled Guardian | Anchors to reality, values stability, hard to earn but reliable |

Temperatures are **stratified** (one agent per band, guaranteeing diversity) and **converge** as rounds progress (range narrows from 5–95 in round 1 to 35–65 by round 6), naturally pushing toward consensus.

### Deliberation

1. **Bill Drafting** (Round 0) — A drafter writes an initial proposal
2. **Debate Rounds** (up to 6) — Structured Q&A with a tightening debate clock. Each round, temperatures are re-shuffled and the exchange budget shrinks
3. **Voting** — 50%+ YES to pass. No abstentions. Every NO must include conditions for flipping to YES
4. **PM Review** — The user can approve, veto (with reasoning), or amend-and-approve
5. **Final Synthesis** — The drafter produces a polished markdown bill with full deliberation record

### Debate Clock

Time pressure tightens each round to force concision:

| Round | Max Exchanges | Sentence Budget |
|-------|--------------|-----------------|
| 1 | 2 × seats | 6 |
| 2 | 2 × seats | 5 |
| 3 | 1.5 × seats | 4 |
| 4 | 1.5 × seats | 3 |
| 5 | 1 × seats | 3 |
| 6 | 1 × seats | 2 |

### Observer Briefs

The user is kept informed throughout with three tiers of reporting: a 2–3 sentence narrative dispatch after every exchange, a position tracker table after each round, and a full vote report after each vote.

## Project Structure

```
open-parliament/
├── open-parliament/
│   ├── SKILL.md                              # Main orchestration instructions
│   ├── agents/
│   │   ├── speaker.md                        # Speaker agent prompt
│   │   └── representative.md                 # Representative agent prompt
│   ├── references/
│   │   ├── communication-protocol.md         # JSON message schemas & ledger format
│   │   ├── temperature-guide.md              # Temperature mechanics & convergence
│   │   └── bill-template.md                  # Final output markdown template
│   └── scripts/
│       ├── init_parliament.py                # Initialize session files
│       └── reassign_temperatures.py          # Re-roll temperatures each round
├── README.md
└── CLAUDE.md
```

### Key Files

- **SKILL.md** — The "Parliament Clerk" instructions. Walks through all 5 phases and contains the orchestration logic, debate clock table, and observer brief specifications.
- **agents/speaker.md** — Prompt for the impartial Speaker who manages turn order, detects deadlocks, enforces the debate clock, and calls votes.
- **agents/representative.md** — Prompt for representative agents. Covers 6 task types (draft, question, respond, amend, vote, synthesize) and the response budget rules.
- **references/communication-protocol.md** — Defines 10 JSON message types, the session state schema (including `debate_clock`), the bill structure, and the amendment lifecycle.
- **references/temperature-guide.md** — Deep reference on the 4 temperature archetypes, interaction dynamics, stratified assignment, convergence pressure, and how the debate clock interacts with temperature.
- **references/bill-template.md** — The 7-section markdown template for the final bill output.
- **scripts/init_parliament.py** — Creates `session.json`, `ledger.json`, and `bill.json` with stratified temperature assignments.
- **scripts/reassign_temperatures.py** — Re-rolls temperatures with convergence pressure and updates the debate clock. Advances the round counter.

## Usage

Trigger the skill with phrases like "open parliament", "deliberate", "multi-perspective debate", "brainstorm from all angles", or any request that benefits from structured multi-agent deliberation.

The system will walk you through:

1. Framing the problem (2–4 sentence problem statement)
2. Identifying constituent issues (8–12 concerns)
3. Setting the number of seats (3–9 representatives, default 5)
4. Running the deliberation
5. Reviewing and approving the final bill

## Scripts

Both scripts can be run standalone for testing:

```bash
# Initialize a parliament
python3 open-parliament/scripts/init_parliament.py \
  --working-dir ./parliament \
  --num-seats 5 \
  --problem "How should we approach X?" \
  --representatives '[
    {"name": "Rep. Alpha", "motives": ["cost", "speed"]},
    {"name": "Rep. Beta", "motives": ["security", "compliance"]},
    {"name": "Rep. Gamma", "motives": ["user experience"]},
    {"name": "Rep. Delta", "motives": ["maintainability", "testing"]},
    {"name": "Rep. Epsilon", "motives": ["scalability"]}
  ]'

# Reassign temperatures for the next round
python3 open-parliament/scripts/reassign_temperatures.py \
  --session-file ./parliament/session.json
```

## Design Principles

- **No obstructionists**: Every temperature archetype is constructive. The tension comes from *how* they advocate, not *whether* they engage.
- **Stratified diversity**: Pure randomness can produce degenerate distributions. Stratified assignment guarantees the full spectrum is represented every round.
- **Natural convergence**: The temperature range and debate clock both tighten over rounds, mimicking how real deliberations move from exploration to decision.
- **Transparency**: Every NO vote must include conditions for change. Dissenting opinions are preserved in the final bill. The user sees everything via observer briefs.
- **PM authority**: The user always has the final word. They can veto, amend, or approve.
