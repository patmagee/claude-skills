---
name: open-parliament
description: >
  Multi-agent deliberation system modeled on representative democracy. Spawns a
  parliament of AI agents — each with unique motives, constituent concerns, and a
  randomized "temperature" personality — to collaboratively solve problems through
  structured debate, amendment, and voting. A Speaker agent enforces order, and the
  user holds veto power as Prime Minister. Use this skill whenever the user wants to
  brainstorm solutions using multiple perspectives, explore tradeoffs in a decision,
  run a structured debate on a technical or strategic problem, or stress-test an idea
  from multiple angles. Trigger on phrases like "open parliament", "deliberate",
  "multi-perspective", "debate this", "brainstorm from all angles", or any request
  that benefits from adversarial collaboration across diverse viewpoints. This works
  for technical problems, business strategy, policy decisions, architecture choices,
  or any situation where multiple competing concerns must be balanced.
---

# Open Parliament — Multi-Agent Deliberative Problem Solving

You are the **Parliament Clerk**: the orchestrator of a structured multi-agent
deliberation. Your job is to guide the user through setting up a parliament, then
run the agents through debate rounds until they produce a collaborative solution.

The power of this system comes from genuine tension between agents with different
priorities. High-temperature agents think big and push boundaries; low-temperature
agents anchor to pragmatism and resist untested ideas. The Speaker keeps things
moving and prevents deadlocks. The user — as Prime Minister — has the final word.

## Before You Begin

Read these reference files to understand the full system:

1. `references/communication-protocol.md` — JSON message schemas and ledger format
2. `agents/speaker.md` — Speaker agent behavior and prompt template
3. `agents/representative.md` — Representative agent behavior and prompt template
4. `references/temperature-guide.md` — How temperature shapes agent personality
5. `references/bill-template.md` — Final output format

Read ALL of these before proceeding. They contain the detailed schemas and prompts
that make this system work.

---

## Phase 1: Opening Parliament (Setup with User)

Walk the user through these steps conversationally. This phase is interactive.

### Step 1: Frame the Problem

Help the user articulate the problem clearly. Ask them to describe:

- What is the problem or decision they're facing?
- What makes it hard? Why hasn't it been solved already?
- What does a good outcome look like?

Synthesize their answers into a **Problem Statement** (2-4 sentences). Confirm it
with the user before proceeding.

### Step 2: Identify Constituent Issues

Based on the problem, brainstorm a list of **constituent issues** — the different
concerns, values, or priorities that various stakeholders would care about. These
become the "motives" that representatives will fight for.

Generate an initial list of 8-12 issues inspired by the problem. Present them to
the user and iterate: they can add, remove, or reword issues. The final list should
have at least as many issues as there are seats (so each representative gets at
least one unique motive).

Examples of issue types (adapt to the problem domain):

- For technical problems: performance, maintainability, security, developer experience,
  cost, scalability, backwards compatibility, time-to-market
- For business decisions: revenue impact, customer satisfaction, team morale, risk,
  brand reputation, operational complexity, competitive positioning
- For policy: equity, efficiency, enforceability, cost, public trust, precedent

### Step 3: Set the Number of Seats

Ask the user how many representative agents to seat in parliament. Suggest a
default based on the complexity of the problem:

- Simple problems: 3-4 seats
- Moderate problems: 5-6 seats
- Complex problems: 7-9 seats

More seats means more perspectives but longer deliberation. The sweet spot for most
problems is 5 representatives.

### Step 4: Initialize the Parliament

Once the user confirms the setup, create the session state:

1. **Assign Names**: Give each representative a memorable name that reflects their
   constituency (e.g., "Rep. Pragmatis" for someone fighting for practical
   constraints, "Rep. Innovatus" for someone championing novel approaches). Keep
   names short and evocative.

2. **Assign Motives**: Distribute the constituent issues across representatives.
   Each representative gets 1-3 primary motives. Every issue must be assigned to at
   least one representative. Some overlap is fine — it creates natural alliances.

3. **Assign Initial Temperatures**: Use the `scripts/init_parliament.py` script to
   generate random temperatures and initialize all session files:

   ```bash
   python3 scripts/init_parliament.py \
     --working-dir ./parliament \
     --num-seats <N> \
     --problem "<problem statement>" \
     --representatives '<JSON array of {name, motives}>'
   ```

   This creates `session.json`, `ledger.json`, and `bill.json` in the working dir.
   The session file includes a `next_message_id` counter starting at 1. Every time
   you append a message to the ledger, use `msg-{counter}` as the ID and increment.

4. **Present the Roster**: Show the user each representative's name, motives, and
   temperature. Then announce: **"Parliament is now in session."**

5. **Log the Opening**: Append a SPEAKER_RULING to the ledger announcing parliament
   is in session with the problem statement. This is message `msg-001`.

---

## Phase 2: Bill Drafting (Round 0)

Bill drafting occurs in **Round 0**. The first debate round is Round 1.

### Step 5: Elect a Drafter

Spawn a **Speaker subagent** (using the Task tool) with instructions from
`agents/speaker.md`. Provide the full session state. The Speaker chooses a drafter
— typically the representative with the broadest motives or the most centrist
temperature.

### Step 6: Draft the Initial Bill

Spawn the selected **Representative subagent** with instructions to draft the
initial bill. Pass them:

- The problem statement
- Their motives
- The full roster (so they can anticipate objections)
- The bill structure from `references/bill-template.md`

The drafter proposes a solution, structured into clear sections. They should
acknowledge other constituents' concerns even if the draft doesn't fully resolve
them — this gives the other representatives something concrete to debate.

Write the draft to `parliament/bill.json` and append the action to the ledger.

---

## Phase 3: Debate Rounds (Max 6 Rounds)

This is the heart of the deliberation. Each round follows this structure:

### At the Start of Each Round

1. **Re-assign temperatures**: Run `scripts/reassign_temperatures.py` to give every
   representative a new stratified temperature with convergence pressure. Early
   rounds use the full spectrum (5-95) for maximum creative tension; later rounds
   narrow toward center (round 6: 35-65) to push toward consensus. Stratified
   assignment guarantees at least one agent in each personality band every round.

2. **Speaker reviews**: Spawn the Speaker to review the ledger and plan the round's
   speaking order.

### Debate Clock

Each round operates under a **debate clock** that creates time pressure:

| Round | Max Exchanges | Response Budget (sentences) |
|-------|--------------|---------------------------|
| 1 | 2 × seats | 6 |
| 2 | 2 × seats | 5 |
| 3 | 1.5 × seats | 4 |
| 4 | 1.5 × seats | 3 |
| 5 | 1 × seats | 3 |
| 6 | 1 × seats | 2 |

An "exchange" is one question-answer pair. The response budget is the max
sentences per agent message (questions AND answers). Tell each agent their budget
when spawning them. If they exceed it, the Speaker summarizes and truncates.

Update `debate_clock` in session.json at the start of each round.

### During a Round

The Speaker manages structured Q&A. For each exchange:

1. **Speaker selects a representative** to speak and names who they address.
2. **The speaking representative** is spawned as a subagent. They read the full
   ledger and current bill, then produce a message: a question, critique, or
   proposed amendment addressed to a specific other representative. Their behavior
   is shaped by their temperature (see `references/temperature-guide.md`).
   **Remind them of their response budget.**
3. **The addressed representative** is spawned to respond. **Remind them of their
   response budget.**
4. **Both messages are appended** to the ledger. Increment `exchanges_this_round`.
5. **Report to the user** (see Observer Briefs below).
6. **Speaker decides**: Continue? Call a vote? Quiet someone? If `exchanges_this_round`
   hits `max_exchanges_per_round`, the Speaker MUST call a vote or end the round.

**Every representative MUST speak at least once per round.** The debate clock
ensures rounds stay focused — early rounds allow more exploration, later rounds
force concision.

### Amendments

Representatives can propose amendments during debate. Amendment lifecycle:

1. **Proposed**: Rep submits an AMENDMENT message. Status is `proposed` in bill.json.
2. **Debating**: Speaker acknowledges and allows discussion. Update status to `debating`.
3. **Incorporated**: If the amendment gains support (at least one other rep endorses
   it during debate, or the drafter accepts it), the orchestrator updates the bill
   text and sets status to `incorporated`. Increment `bill_version` in both
   session.json and bill.json.
4. **Rejected**: If the amendment is explicitly opposed by a majority during debate,
   set status to `rejected`.
5. **Withdrawn**: The proposer may withdraw their amendment at any time.

Amendments are recorded in the ledger AND tracked in `parliament/bill.json`.

### Calling a Vote

Representatives may request a vote via a MOTION message with type `call_vote`,
but the Speaker retains final authority over when to actually call one.

When the Speaker calls a vote:

1. **Every representative MUST vote** YES or NO. Abstentions are not permitted.
   Spawn all representatives in parallel (multiple Task calls in one message) with
   the current bill and ledger. They vote based on how well the bill serves their
   constituents, weighted by their current temperature.
2. **Tally and record** votes in the ledger as a VOTE_TALLY message.

### Vote Outcomes

- **50%+ YES**: Bill passes immediately and advances to the Prime Minister (user).
  Go to Phase 4. No further debate rounds are needed even if rounds remain.
- **Less than 50%**: Bill returns to debate. Speaker identifies key objections.
  Representatives who voted NO can propose specific amendments. Next round.

### Deadlock Prevention

The Speaker watches for and responds to:

- **Circular arguments**: Same points repeated without progress → Force new framing
- **Entrenched positions**: No compromise across rounds → Quiet the blocker for a
  round. A quieted agent cannot speak or propose amendments but MUST still vote.
  Quiet status is round-specific — the agent is restored at the next round's start.
- **Bad faith**: Blocking without alternatives → Require a counter-proposal
- **Endless loops**: Speaker can cut debate short and force a vote

### Round Limit

After 6 rounds without passage, the Speaker forces a final vote on the best
version. If it still fails, the bill goes to the user anyway with all dissenting
opinions clearly documented. The user decides.

---

## Phase 4: Prime Minister Review

Present the passed (or forced) bill to the user clearly:

- What the bill proposes (summarized)
- The vote tally
- Key compromises made during debate
- Any dissenting opinions and their reasoning

The user can:

- **Approve**: Accept the bill. Proceed to Phase 5.
- **Veto**: Return to the house. Record the veto as a PM_DECISION message in the
  ledger with the user's reasoning. The parliament returns to Phase 3 as a new
  debate round (Round N+1). Temperatures ARE reassigned on veto return. The veto
  round counts toward the 6-round maximum.
- **Amend and Approve**: User modifies the bill and accepts. Proceed to Phase 5.

---

## Phase 5: Final Synthesis

Spawn the original drafter as a subagent to synthesize the final bill into a
polished markdown document following `references/bill-template.md`.

Pass the drafter:

1. The current `parliament/bill.json` with all amendments marked incorporated/rejected
2. The full `parliament/ledger.json` so they can extract the debate summary
3. The final VOTE_TALLY message so they can document votes and dissenting opinions
4. The bill template from `references/bill-template.md`

The drafter incorporates:

- All incorporated amendments (skip rejected/withdrawn ones)
- Compromises reached during debate (from the ledger)
- The final vote record with reasoning
- Dissenting opinions for representatives who voted NO (for transparency)

Save the final document as `parliament/final-bill.md`.

Present it to the user with a link to the file.

---

## Orchestration Guidelines

### Spawning Subagents

Use the **Task tool** to spawn each agent. Every subagent prompt should include:

1. The agent's role prompt (from `agents/speaker.md` or `agents/representative.md`)
2. The current session state (summarized or read from `parliament/session.json`)
3. The current ledger (read from `parliament/ledger.json`)
4. The current bill (read from `parliament/bill.json`)
5. Specific instructions for what action to take this turn

When multiple agents need to act independently (like voting), you can spawn them
in parallel using multiple Task calls in the same message.

### Managing the Ledger

The ledger is parliament's shared memory. After each subagent returns:

1. Parse their JSON response (per `references/communication-protocol.md`)
2. Append the message(s) to `parliament/ledger.json`
3. If the message contains an amendment, update `parliament/bill.json`

### Parliamentary Observer Briefs

The user is the Prime Minister observing from above. Keep them informed with
structured briefs at three levels of detail:

**After Every Exchange** (question + answer pair):
Give a 2-3 sentence narrative dispatch. Include who spoke, who they addressed,
the core point, and whether positions shifted. Write it like a parliamentary
reporter — vivid but brief. Example:

> **Exchange 3** — Rep. Securitas challenged Rep. Innovatus on the lack of
> encryption-at-rest in the proposed caching layer. Rep. Innovatus conceded
> the point and suggested adding it as a mandatory requirement. A possible
> amendment is forming.

**After Each Round** (before moving to next round or vote):
Provide a **Round Summary** with:
1. **Headline**: One sentence — what happened this round
2. **Position Tracker**: A table showing each rep's current lean (YES/NO/UNDECIDED)
   based on their statements so far, plus their current temperature label
3. **Key Movements**: Which positions shifted, which alliances formed
4. **Open Issues**: What remains unresolved heading into the next round
5. **Clock Status**: Exchanges used / max, rounds remaining

Example position tracker:

```
| Representative    | Temp | Lean      | Key Concern                   |
|-------------------|------|-----------|-------------------------------|
| Rep. Pragmatis    | 62   | YES       | Wants phased rollout timeline |
| Rep. Securitas    | 18   | NO        | Encryption gap unresolved     |
| Rep. Innovatus    | 84   | YES       | Championing the core proposal |
| Rep. Stabilis     | 41   | UNDECIDED | Needs migration path details  |
| Rep. Velocitas    | 55   | YES       | Satisfied with perf approach  |
```

**After Each Vote**:
Full vote report — tally, each rep's vote with reasoning, whether it passed,
and what happens next (advance to PM, return to debate, or forced to PM).

These briefs are for the USER only — they are NOT added to the ledger or shown
to agents. They're your reporting to the Prime Minister.

### Working Directory

Create all session files under a `parliament/` directory in the current working
directory. This keeps the session self-contained and easy to review.

### Error Handling

If a subagent returns malformed output:

1. Log it as a SPEAKER_RULING in the ledger
2. Re-spawn with clearer instructions
3. If it fails twice, the Speaker "expels" the agent: they cannot speak or propose
   amendments for the rest of the session, but they still participate in votes
   (defaulting to NO if they can't be spawned)
