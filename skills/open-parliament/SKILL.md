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

This file contains everything you need to orchestrate a parliament session. The
reference files below exist for **subagents to read** — you do NOT need to read
them yourself. Your context window is a finite resource; treat it as such.

Reference files (for subagents, not you):

1. `references/communication-protocol.md` — JSON message schemas and ledger format
2. `agents/speaker.md` — Speaker agent behavior and prompt template
3. `agents/representative.md` — Representative agent behavior and prompt template
4. `references/temperature-guide.md` — How temperature shapes agent personality
5. `references/bill-template.md` — Final output format

**Do NOT read these files.** The schemas and protocols you need are documented
inline in this file. When spawning subagents, tell them which files to read —
they have their own context windows.

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

## Phase 2: Opening Statements (Round 0)

Before any bill is drafted, every representative presents an opening statement.
This surfaces domain knowledge and exposes competing solution directions so the
parliament doesn't lock into a single perspective prematurely.

### Step 5: Gather Opening Statements

Spawn ALL representatives in parallel (multiple Task calls in one message).
Each representative receives:

- The problem statement
- Their motives and temperature
- The full roster
- Instructions to produce an OPENING_STATEMENT (see `agents/representative.md`)

Each statement contains:
1. A **briefing** on facts, constraints, and precedents from their motive area
2. A **directional sketch** of their preferred solution approach (3-5 sentences)

Append all statements to the ledger using the append script:

```bash
python3 scripts/append_to_ledger.py \
  --working-dir ./parliament \
  --message '[<statement1>, <statement2>, ...]'
```

Update session status to `"opening_statements"`.

### Step 6: Speaker Evaluates Directions

Spawn the Speaker with the EVALUATE_STATEMENTS task (see `agents/speaker.md`).
All opening statements are visible in the ledger. The Speaker:

1. Synthesizes the briefings into a shared **fact base** — the key facts,
   constraints, and assumptions the parliament should treat as common ground
2. Identifies the distinct solution directions proposed (typically 2-4)
3. Selects a drafter — the rep whose direction best synthesizes multiple
   concerns, or whose motives are broadest

The Speaker's evaluation is logged as a SPEAKER_RULING with action
`evaluate_statements`. Update session status to `"evaluating_statements"`.

### Step 7: PM Reviews Opening Statements

Present the fact base and identified solution directions to the user. The PM can:

- Add facts or constraints the representatives missed
- Signal preference for a solution direction (non-binding but influential)
- Approve or override the Speaker's drafter selection

Record any PM input as a PM_DECISION with decision `opening_guidance`.

---

## Phase 3: Bill Drafting (Round 0)

Bill drafting occurs after opening statements, still in **Round 0**. The first
debate round is Round 1.

### Step 8: Draft the Initial Bill

Spawn the selected **Representative subagent** with instructions to draft the
initial bill. Pass them:

- The problem statement
- Their motives
- The full roster (so they can anticipate objections)
- **All opening statements** (the full set, not just their own)
- The Speaker's fact base synthesis
- Any PM guidance from Step 7
- The bill structure from `references/bill-template.md`
- Instructions to synthesize across opening statements, not just draft from
  their own direction

The drafter proposes a solution, structured into clear sections. They should
acknowledge other constituents' concerns even if the draft doesn't fully resolve
them — this gives the other representatives something concrete to debate.

Write the draft to `parliament/bill.json` and append the action to the ledger.
Update session status to `"drafting"`.

---

## Phase 4: Debate Rounds (Max 6 Rounds)

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
2. **The speaking representative** is spawned as a subagent. They read the
   ledger context (see Context Windowing below) and current bill, then produce a
   message: a question, critique, or proposed amendment addressed to a specific
   other representative. Their behavior is shaped by their temperature (see
   `references/temperature-guide.md`). **Remind them of their response budget.**
   If their temperature shifted by more than 15 points since last round, include
   a transition narrative (see Temperature Transitions below).
3. **The addressed representative** is spawned to respond. **Remind them of their
   response budget.** Include transition narrative if applicable.
4. **Append both messages** to the ledger using `scripts/append_to_ledger.py`.
   Increment `exchanges_this_round` in session.json.
4b. **Check for motions**: If either representative's response includes a `motion`
    field, extract it and append a separate MOTION message to the ledger (using
    the MOTION schema from the communication protocol). Pass the motion to the
    Speaker as part of the next NEXT_ACTION decision.
4c. **Check for amendment positions**: If a response includes an
    `amendment_position` field, record the endorsement in the corresponding
    amendment's `endorsements` array in `parliament/bill.json`. Check if the
    incorporation threshold is met (proposer + 1 endorsement, or drafter
    acceptance) — if so, incorporate the amendment.
4d. **Update motive satisfaction**: If a response includes `motive_scores`,
    update the representative's `motive_satisfaction` in session.json. These
    scores are passed to the Speaker for vote-gating decisions.
4e. **Enforce concession guard**: If a representative uses `soften` or `concede`
    stance in rounds 1-2, note this as a protocol violation in the observer
    brief and instruct the Speaker to redirect.
5. **Report to the user** (see Observer Briefs below).
6. **Speaker decides**: Continue? Call a vote? Quiet someone? If `exchanges_this_round`
   hits `max_exchanges_per_round`, the Speaker MUST call a vote or end the round.
   If a motion was extracted in step 4b, include it in the Speaker's context.

**Every representative MUST speak at least once per round.** The debate clock
ensures rounds stay focused — early rounds allow more exploration, later rounds
force concision.

### Amendments

Representatives can propose amendments during debate. Amendment lifecycle:

1. **Proposed**: Rep submits an AMENDMENT message. Status is `proposed` in bill.json.
   Initialize an empty `endorsements` array on the amendment object.
2. **Debating**: Speaker acknowledges and allows discussion. Update status to `debating`.
3. **Endorsed**: During debate about the amendment, representatives state their
   position via the `amendment_position` field in their responses. The orchestrator
   records these in the amendment's `endorsements` array in `parliament/bill.json`.
4. **Incorporated**: When the amendment has the proposer + 1 endorsement (or drafter
   acceptance), the orchestrator updates the bill text and sets status to
   `incorporated`. Increment `bill_version` in both session.json and bill.json.
5. **Rejected**: If the amendment has more oppose positions than endorse positions
   after discussion concludes, set status to `rejected`. The Speaker may also call
   a formal amendment vote if positions are unclear after 2+ exchanges.
6. **Withdrawn**: The proposer may withdraw their amendment at any time.

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
  Go to Phase 5. No further debate rounds are needed even if rounds remain.
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

## Phase 5: Prime Minister Review

Present the passed (or forced) bill to the user clearly:

- What the bill proposes (summarized)
- The vote tally
- Key compromises made during debate
- Any dissenting opinions and their reasoning

The user can:

- **Approve**: Accept the bill. Proceed to Phase 6.
- **Veto**: Return to the house. Record the veto as a PM_DECISION message in the
  ledger with the user's reasoning. The parliament returns to Phase 4 as a new
  debate round (Round N+1). Temperatures ARE reassigned on veto return. The veto
  round counts toward the 6-round maximum.
- **Amend and Approve**: User modifies the bill and accepts. Proceed to Phase 6.

---

## Phase 6: Final Synthesis

Spawn the original drafter as a subagent to synthesize the final bill into a
polished markdown document following `references/bill-template.md`.

Pass the drafter:

1. The current `parliament/bill.json` with all amendments marked incorporated/rejected
2. The **complete** `parliament/ledger.json` (not the windowed version used during
   debate — the final bill's deliberation record requires full detail from all rounds)
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

### Context Budget

Your context window must last the entire parliament session — potentially 6+
rounds of debate with 5-9 representatives. **Treat context as a non-renewable
resource.** Every file you read, every subagent response you process, every
observer brief you generate stays in your context permanently.

Rules:
1. **Never read reference files** (`agents/*.md`, `references/*.md`). Subagents
   read their own role prompts and schemas.
2. **Never read the full ledger.** Use `scripts/append_to_ledger.py` for writes.
   Subagents read the ledger in their own context.
3. **Read session.json and bill.json sparingly** — only when you need specific
   values (e.g., checking a temperature for a transition narrative, confirming
   amendment status). Prefer extracting what you need from subagent return values.
4. **Keep observer briefs concise.** 2-3 sentences per exchange, not paragraphs.
5. **Don't echo subagent responses** back to the user verbatim. Summarize.

The subagents have independent context windows — let them do the heavy reading.
Your job is dispatch and coordination, not analysis.

### Spawning Subagents

Use the **Task tool** to spawn each agent. **Critical: subagents read their
own files.** Do NOT read reference files, agent prompts, or large state files
into your context just to paste them into a Task prompt. Your context window
is a finite resource — protect it.

Every subagent prompt should include:

1. **File paths to read** — tell the subagent which files to read (role prompt,
   session state, bill, ledger). They have their own context windows.
   - Speaker: "Read `agents/speaker.md` for your role instructions."
   - Representative: "Read `agents/representative.md` for your role instructions."
   - State: "Read `parliament/session.json`, `parliament/bill.json`."
   - Ledger: "Read `parliament/ledger.json`." (Or specify context windowing
     for rounds 3+ — see below.)
2. **Compact task-specific context** — inline only what the subagent can't get
   from files: the specific task (e.g., ASK_QUESTION targeting rep_2), the
   agent's profile summary (name, motives, temperature), response budget, and
   any transition narrative.
3. **Context windowing instructions** — for rounds 3+, tell the subagent which
   rounds to read in full and which to read from `parliament/round-summaries.json`.

Example Task prompt (lean):

```
You are a Representative in parliament. Read `agents/representative.md` for
your full role instructions.

Read these state files:
- `parliament/session.json` (your profile and the roster)
- `parliament/bill.json` (the current bill)
- `parliament/ledger.json` (debate history)

Your profile: Rep. Pragmatis (rep_1), motives: [cost efficiency, time-to-market],
temperature: 62 (Pragmatic Advocate).

Transition note: Last round you were at temp 18 (Guardian). Your motives haven't
changed, but you're now more open to creative compromise.

Task: ASK_QUESTION directed at rep_3 about the security audit timeline.
Response budget: 4 sentences.

Return valid JSON matching the QUESTION schema.
```

When multiple agents need to act independently (like voting or opening
statements), spawn them in parallel using multiple Task calls in the same
message.

### Ledger Management

The ledger is parliament's shared memory. **Never read the full ledger into
your own context.** Use the append script instead:

```bash
python3 scripts/append_to_ledger.py \
  --working-dir ./parliament \
  --message '<JSON message from subagent>'
```

This reads the ledger, adds metadata (id, round, timestamp), increments
`next_message_id` in session.json, and writes both files back. You only see
the script's confirmation output (message IDs), not the ledger contents.

For multiple messages at once (e.g., parallel opening statements):

```bash
python3 scripts/append_to_ledger.py \
  --working-dir ./parliament \
  --message '[<msg1>, <msg2>, ...]'
```

**When you need to check a specific message** (e.g., to extract a motion or
amendment position from a subagent's response), work from the subagent's
return value — which is already in your context — rather than re-reading
the ledger.

### Round Summaries

At the end of each debate round (after the last exchange and before advancing
to the next round), generate a **round summary** for the round that just
completed. This summary is produced by you (the Clerk), not by a subagent.
Base it on the observer briefs you already generated during the round.

Write the summary to `parliament/round-summaries.json` (an array of summary
objects, one per completed round). Create this file after Round 1 completes.

Each summary includes:
- A 2-3 sentence narrative of what happened
- Each representative's current lean (YES/NO/UNDECIDED) and key concern
- Key position shifts that occurred
- Amendments actioned and their status
- Any vote results
- Open issues heading into the next round

See `references/communication-protocol.md` for the full schema.

### Context Windowing

To prevent the ledger from overwhelming agent context in later rounds, use a
sliding window when spawning subagents:

| Content | Source |
|---------|--------|
| Rounds 0 through R-2 | Round summaries only |
| Round R-1 (previous) | Full messages from the ledger |
| Round R (current) | Full messages so far this round |

Always include: the full bill, session state, and all opening statements
(from Phase 2).

The full ledger remains on disk for the final synthesis phase, which needs
the complete record for the deliberation summary. When spawning the drafter
in Phase 6, pass the **complete** `parliament/ledger.json` (not the windowed
version).

In rounds 1-2, the full ledger is small enough to pass directly. Context
windowing becomes important from round 3 onward.

### Dissent Pressure

The parliament is designed to produce robust solutions, not fast agreement.
Three mechanisms prevent premature consensus:

**Motive satisfaction tracking**: Every ANSWER message includes `motive_scores`
— the representative's assessment of how well the bill serves each of their
motives (1-5 scale). Update `motive_satisfaction` in session.json after each
exchange. Pass these scores to the Speaker for PLAN_ROUND and NEXT_ACTION.

**Concession guard**: Representatives are restricted in which stances they
can take in early rounds:

| Round | Allowed Stances |
|-------|----------------|
| 1-2 | `maintain` or `challenge` only |
| 3 | `maintain`, `challenge`, or `soften` |
| 4+ | All stances including `concede` |

When spawning representatives in rounds 1-2, explicitly remind them:
"Concession guard is active. You may only maintain or challenge this round."

**Vote-gating**: The Speaker cannot call a vote while any representative has
a motive scoring below 3, unless forced by the debate clock hitting the
exchange cap or reaching round 6. This ensures every motive gets meaningful
attention before the parliament moves to a decision.

### Temperature Transitions

When spawning a representative whose temperature shifted by more than 15 points
since their last spawn, include a 1-2 sentence **transition narrative**. Generate
this yourself based on the `temperature_history` in session.json and the archetype
descriptions from `references/temperature-guide.md`.

The narrative should connect the old engagement style to the new one while
emphasizing that motives and prior positions remain intact. Examples:

For a large shift crossing archetypes (e.g., Guardian → Pragmatic Advocate):

> "Last round you engaged as a Principled Guardian (temp 18) — cautious,
> evidence-focused, brief. This round you're a Pragmatic Advocate (temp 62).
> Your motives haven't changed. But where last round you were anchoring the
> group to hard constraints, this round you're more open to finding creative
> compromises that still respect those constraints. Build on the positions
> you've already established."

For a moderate shift within the same archetype (e.g., 55 → 68):

> "Your temperature shifted from 55 to 68. Your approach is largely the same
> — still a Pragmatic Advocate — but slightly more assertive and willing to
> push for creative solutions this round."

For shifts of 15 or less, no transition narrative is needed.

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
