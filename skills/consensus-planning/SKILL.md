---
name: consensus-planning
description: >
  Multi-agent consensus planning system. Spawns a panel of AI analysts — each
  assigned different focus areas and a randomized analytical perspective — to
  collaboratively solve problems through structured rounds of critique, revision,
  and assessment. A facilitator agent manages the process. A review agent
  validates the final output. Use this skill for technical architecture
  decisions, complex tradeoff analysis, strategy problems, or any situation
  where multiple competing concerns must be balanced. Trigger on phrases like
  "consensus plan", "multi-perspective", "brainstorm from all angles",
  "structured debate", or any request that benefits from adversarial
  collaboration across diverse viewpoints.
---

# Consensus Planning — Multi-Agent Collaborative Problem Solving

You are the **orchestrator** of a structured multi-agent planning session. Your
job is to guide the user through problem definition, then run analyst agents
through iterative refinement rounds until they produce a robust consensus plan.

The system's strength comes from genuine tension between analysts with different
analytical perspectives. Bold analysts push creative solutions; conservative
analysts stress-test with rigor. The facilitator keeps things productive. A
review agent validates the final output. The user has final authority.

## Before You Begin

This file contains your orchestration instructions. Reference files exist for
**subagents to read** — do NOT read them yourself. Your context window is finite.

Reference files (for subagents only):

1. `references/schemas.md` — JSON message schemas and log format
2. `agents/facilitator.md` — Facilitator agent behavior
3. `agents/analyst.md` — Analyst agent behavior
4. `agents/reviewer.md` — Review agent behavior

**Do NOT read these files.** Subagents read their own prompts in independent
context windows.

---

## Phase 1: Discovery (Interactive with User)

Before any planning begins, understand the problem deeply. Ask clarifying
questions iteratively until you have a clear picture.

### Step 1: Understand the Problem

Ask the user to describe their problem. Then ask targeted clarifying questions:

- What is the problem or decision?
- What has been tried or considered already?
- What constraints exist (technical, budget, timeline, team)?
- What does success look like?
- Who are the stakeholders?
- What's the risk of doing nothing?

Don't ask all questions at once. Ask 2-3, process the answers, then ask
follow-up questions based on what you learned. Continue until you can write a
clear problem statement.

### Step 2: Confirm Problem Statement

Synthesize a **problem statement** (2-4 sentences). Confirm with the user.

### Step 3: Identify Focus Areas

Based on the problem, brainstorm **focus areas** — the different concerns and
priorities that matter. These become the priorities assigned to analysts.

Generate 8-12 focus areas. Examples for technical problems:

- Performance, maintainability, security, developer experience, cost,
  scalability, backwards compatibility, time-to-market, operational complexity,
  testing strategy, data integrity, user experience

Present them. Let the user add, remove, or reword. The final list needs at
least as many items as analysts.

### Step 4: Set Panel Size

Ask how many analysts to seat. Suggest based on complexity:

- Simple: 3-4 analysts
- Moderate: 5-6 analysts
- Complex: 7-9 analysts

Default recommendation: 5.

### Step 5: Initialize the Session

Once confirmed:

1. **Name analysts** with functional labels (e.g., "Security Analyst",
   "Performance Analyst", "Cost Analyst"). Names should reflect their focus
   areas. Keep them short and descriptive — no role-play personas.

2. **Assign priorities**: Distribute focus areas across analysts. Each gets 1-3
   priorities. Every focus area must be assigned to at least one analyst.

3. **Initialize state**: Run the init script:

   ```bash
   python3 scripts/init_session.py \
     --working-dir ./planning \
     --num-analysts <N> \
     --problem "<problem statement>" \
     --analysts '<JSON array of {name, priorities}>'
   ```

4. **Present the panel**: Show each analyst's name, priorities, and perspective
   score. Then announce the session is starting.

5. **Log the opening**: Append a FACILITATOR_RULING to the log announcing the
   session has started with the problem statement.

---

## Phase 2: Brainstorm (Round 0)

Every analyst produces an independent technical analysis before any proposal
is drafted. This surfaces domain knowledge and competing solution directions.

### Step 6: Gather Initial Analyses

Spawn ALL analysts in parallel. Each receives:

- The problem statement
- Their priorities and perspective score
- The full roster
- Instructions to produce an INITIAL_ANALYSIS

Each analysis contains:
1. **Technical briefing**: Facts, constraints, precedents, risks from their area
2. **Solution sketch**: A high-level approach they'd advocate (3-5 sentences)
3. **Key questions**: What must be answered before committing to any approach

Use brainstorming techniques — analysts should think broadly:
- "How might we..." framing for opportunities
- Constraint analysis: what are the hard limits?
- Risk identification: what could go wrong?
- Prior art: what has worked in similar situations?

Append all analyses to the log using the append script.

### Step 7: Facilitator Synthesizes

Spawn the facilitator with the EVALUATE_ANALYSES task. It:

1. Compiles a shared **fact base** from all briefings
2. Identifies distinct solution directions (typically 2-4)
3. Selects a drafter — the analyst whose direction best synthesizes concerns

### Step 8: User Reviews

Present the fact base and solution directions. The user can:

- Add facts or constraints the analysts missed
- Signal preference for a direction (non-binding)
- Approve or override the drafter selection

---

## Phase 3: Draft Proposal (Round 0)

### Step 9: Draft the Initial Proposal

Spawn the selected analyst to draft. Pass them:

- The problem statement and their priorities
- All initial analyses
- The facilitator's synthesis
- Any user guidance from Step 8

The drafter produces a structured proposal: problem, scope, solution,
implementation considerations. They should synthesize across all analyses, not
just their own direction.

Write the draft to `planning/proposal.json` and append to the log.

---

## Phase 4: Refinement Rounds (Max 6 Rounds)

### At the Start of Each Round

1. **Re-assign perspectives**: Run `scripts/reassign_perspectives.py`. Early
   rounds use the full spectrum (5-95) for maximum analytical diversity; later
   rounds narrow toward center for convergence.

2. **Facilitator plans**: Spawn the facilitator to review the log and plan the
   round's discussion order.

### Debate Clock

| Round | Max Exchanges | Response Budget (sentences) |
|-------|--------------|---------------------------|
| 1     | 2 x analysts | 6                         |
| 2     | 2 x analysts | 5                         |
| 3     | 1.5 x analysts | 4                       |
| 4     | 1.5 x analysts | 3                       |
| 5     | 1 x analysts | 3                         |
| 6     | 1 x analysts | 2                         |

### During a Round

The facilitator manages structured Q&A. For each exchange:

1. **Facilitator selects** an analyst to speak and names who they address.
2. **The speaking analyst** reads the log context and current proposal, then
   produces a critique or question addressed to another analyst. Their style
   is shaped by their perspective score. **Remind them of their response budget.**
   Include a transition note if their perspective shifted by more than 15 points.
3. **The addressed analyst** responds. Include transition note if applicable.
4. **Append both messages** to the log. Increment `exchanges_this_round`.
4b. **Check for requests**: If either response includes a `request` field,
    pass it to the facilitator.
4c. **Check for revision positions**: If a response includes a
    `revision_position` field, record endorsement in `proposal.json`.
4d. **Update satisfaction scores**: If a response includes `priority_scores`,
    update in session.json.
4e. **Enforce stance guard**: Rounds 1-2 allow only `maintain` or `challenge`.
5. **Report to user**: 2-3 sentence status update.
6. **Facilitator decides**: Continue, call assessment, quiet someone, etc.

Every analyst MUST contribute at least once per round.

### Revisions

Analysts can propose revisions during discussion:

1. **Proposed** → 2. **Debating** → 3. **Incorporated/Rejected/Withdrawn**

Incorporation requires the proposer + 1 endorsement, or drafter acceptance.

### Assessment (Voting)

When the facilitator calls an assessment:

1. Every analyst evaluates YES or NO. Spawn all in parallel.
2. **50%+ YES**: Proposal passes. Go to Phase 5.
3. **Less than 50%**: Return to refinement. Analysts who voted NO propose revisions.

### Round Limit

After 6 rounds without passage, the facilitator forces a final assessment.
If it fails, the proposal goes to the user with all dissenting views documented.

---

## Phase 5: Review

Spawn the **review agent** to evaluate the final proposal. Pass it:

- The current `planning/proposal.json`
- The complete `planning/log.json`
- The session state with all analyst profiles and satisfaction scores

The reviewer evaluates:

1. **Completeness**: Does the proposal address all identified focus areas?
2. **Feasibility**: Are the implementation steps realistic and actionable?
3. **Risk coverage**: Were major risks identified and mitigated?
4. **Consensus quality**: Were dissenting views genuinely addressed or just
   outvoted? Are the remaining objections reasonable?
5. **Gaps**: What did the panel miss that a fresh perspective catches?

The reviewer produces a structured assessment. Present it to the user alongside
the proposal. The user can:

- **Approve**: Accept the proposal. Proceed to Phase 6.
- **Send back**: Return to refinement with reviewer's feedback incorporated.
  The review findings are added to the log for all analysts to see.
- **Amend and approve**: User modifies and accepts.

---

## Phase 6: Final Output

Spawn the original drafter to synthesize the final document. Pass them:

1. The current `planning/proposal.json` with all revisions
2. The **complete** `planning/log.json` (full history, not windowed)
3. The final assessment results
4. The review agent's findings

The output document structure:

1. **Problem Statement** — What and why
2. **Scope** — In/out of scope, assumptions, definitions
3. **Proposed Solution** — The plan in actionable detail
4. **Implementation Considerations** — Phasing, resources, risks, success criteria
5. **Analysis Record** — Key debates, revisions incorporated, compromises
6. **Dissenting Views** — Analysts who voted NO, their concerns, conditions
7. **Assessment Record** — Each analyst's vote, reasoning, final scores

Save as `planning/final-proposal.md`. Present to the user.

---

## Orchestration Guidelines

### Context Budget

Your context must last the full session. **Treat it as non-renewable.**

1. **Never read reference files.** Subagents read their own prompts.
2. **Never read the full log.** Use `scripts/append_to_log.py` for writes.
3. **Read session.json and proposal.json sparingly.**
4. **Keep status updates concise.** 2-3 sentences per exchange.
5. **Don't echo subagent responses.** Summarize.

### Spawning Subagents

Every subagent prompt should include:

1. **File paths to read** — tell them which files to read
2. **Compact task context** — inline only what they can't get from files
3. **Context windowing** — for rounds 3+, specify which rounds to read in full

Example (lean):
```
You are an analyst in a consensus planning session. Read `agents/analyst.md`
for your role instructions.

Read: `planning/session.json`, `planning/proposal.json`, `planning/log.json`

Your profile: Security Analyst (analyst_1), priorities: [security, compliance],
perspective: 62 (balanced).

Task: CRITIQUE directed at analyst_3 about the data migration approach.
Response budget: 4 sentences.

Return valid JSON matching the CRITIQUE schema.
```

### Log Management

Use the append script — never read the full log:

```bash
python3 scripts/append_to_log.py \
  --working-dir ./planning \
  --message '<JSON from subagent>'
```

### Round Summaries

At the end of each round, generate a summary for context windowing. Write to
`planning/round-summaries.json`. Include:
- 2-3 sentence narrative
- Each analyst's current position (YES/NO/UNDECIDED) and key concern
- Position shifts, revisions actioned, open issues

### Context Windowing

For rounds 3+:

| Content | Source |
|---------|--------|
| Rounds 0 through R-2 | Round summaries only |
| Round R-1 | Full messages |
| Round R (current) | Full messages so far |

### Dissent Pressure

Three mechanisms prevent premature consensus:

1. **Priority satisfaction scores** (1-5) on every response. Tracked in session.json.
2. **Stance guard**: Rounds 1-2 allow only `maintain` or `challenge`. Round 3
   adds `soften`. Round 4+ allows `concede`.
3. **Assessment gating**: Facilitator cannot call assessment while any priority
   scores below 3 (unless forced by clock or round 6).

### Perspective Transitions

When an analyst's perspective shifts >15 points, include a 1-2 sentence
transition note connecting old analytical style to new one.

### Status Updates

Keep the user informed at three levels:

1. **After each exchange**: 2-3 sentence narrative
2. **After each round**: Position tracker table + key movements
3. **After each assessment**: Full results with reasoning

These are for the user only — never added to the log.

### Working Directory

Create all session files under `planning/` in the current working directory.

### Error Handling

If a subagent returns malformed output:
1. Log it as a FACILITATOR_RULING
2. Re-spawn with clearer instructions
3. If it fails twice, the facilitator removes the analyst from active
   discussion (they still participate in assessments, defaulting to NO)
