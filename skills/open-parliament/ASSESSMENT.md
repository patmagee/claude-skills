# Open Parliament Skill — Problem-Solving Assessment

An audit of the open-parliament skill's problem-solving effectiveness, covering
architectural strengths, implementation gaps, and areas where deliberation
quality is likely to degrade.

---

## Strengths

The skill has a well-considered design with several mechanisms that support
genuine multi-perspective problem solving:

1. **Dual convergence mechanism**: Temperature range narrowing (5-95 → 35-65)
   and debate clock tightening (6 sentences → 2, 2×seats exchanges → 1×seats)
   work in tandem to create a natural arc from exploration to consensus. This
   mirrors real negotiation dynamics.

2. **Stratified temperature assignment**: Dividing the range into N equal bands
   with one agent per band guarantees a diverse spectrum every round. This
   prevents degenerate all-cold (gridlock) or all-hot (chaos) distributions
   that pure randomness could produce.

3. **No obstructionists by design**: All four temperature archetypes are
   constructive — they differ in *how* they engage, not *whether* they engage.
   Every NO vote must include conditions for flipping. This keeps deliberation
   productive.

4. **Transparency through observer briefs**: Three tiers of reporting (per-
   exchange narrative, per-round position tracker, per-vote full report) give
   the PM good situational awareness without overwhelming them.

5. **Well-defined communication protocol**: 9 message types with explicit JSON
   schemas, a sequential message ID counter, and clear metadata separation
   (agents return content, orchestrator adds id/round/timestamp) create a
   clean contract between agents and orchestrator.

6. **PM authority as safety valve**: The user can approve, veto, or amend-and-
   approve, with vetoes counting toward the round limit. This prevents runaway
   deliberation while preserving user control.

---

## Gap 1: Single-Bill Lock-In (No Competing Proposals)

**Impact: High**

The process commits to a single bill from the start. One representative drafts
it in Round 0, and all subsequent debate is incremental amendment to that bill.
There is no mechanism for:

- Competing proposals from different representatives
- Fundamentally different solution architectures
- A "compare two approaches" phase before committing to one direction

The amendment system (`add`/`modify`/`remove`/`replace`) can alter sections but
cannot propose a wholesale alternative to the bill's core approach. If the
initial drafter frames the problem narrowly or picks a suboptimal solution
direction, the entire deliberation is anchored to that frame.

In real deliberative bodies, competing bills or a committee stage with multiple
draft proposals produces better outcomes by exploring the solution space more
broadly before converging.

---

## Gap 2: No Information-Gathering Phase

**Impact: High**

The skill jumps directly from problem framing (Phase 1) to bill drafting
(Phase 2). There is no research or fact-finding phase where agents can:

- Surface domain knowledge relevant to the problem
- Identify precedents, prior art, or existing solutions
- Establish shared factual ground before proposing solutions
- Challenge assumptions in the problem statement itself

The drafter writes the initial bill based solely on the problem statement and
their motives. For problems that require factual context (e.g., "which
technology stack should we adopt?" requires understanding current constraints,
team expertise, licensing, etc.), the lack of a research phase means the bill
may be built on incomplete information.

Similarly, there is no mechanism for the orchestrator to inject factual context
mid-deliberation if agents are debating based on incorrect assumptions.

---

## Gap 3: MOTION Message Type Is Dead Code

**Impact: Medium**

The communication protocol defines a `MOTION` message type with five subtypes:
`call_vote`, `table_discussion`, `request_amendment`, `point_of_order`, and
`request_compromise`. The Speaker prompt references motions, saying the Speaker
"may acknowledge, deny, or act on motions at your discretion."

However, the representative agent prompt (`agents/representative.md`) defines
only six task types: `DRAFT_BILL`, `ASK_QUESTION`, `RESPOND`,
`PROPOSE_AMENDMENT`, `CAST_VOTE`, and `SYNTHESIZE_FINAL`. There is no task
type that would cause a representative to produce a `MOTION` message.

Representatives cannot:
- Request a vote when they believe debate has concluded
- Call a point of order when another rep is off-topic
- Request a compromise when positions are entrenched
- Table a discussion they consider unproductive

This removes an entire channel of agent agency. The Speaker is the sole
procedural actor, and the deliberation loses the emergent self-governance that
motions would enable.

---

## Gap 4: Amendment Endorsement Has No Formal Mechanism

**Impact: Medium**

The amendment lifecycle in SKILL.md (lines 212-224) states an amendment can be
incorporated "if at least one other rep endorses it during debate, or the
drafter accepts it." But there is no:

- Formal `ENDORSE_AMENDMENT` message type
- Structured way for a rep to signal support during an `ANSWER` task
- Threshold or quorum defined for what constitutes "support"

Whether an amendment is endorsed depends entirely on the orchestrator's
subjective interpretation of free-text ANSWER content. A rep saying "that's a
reasonable point" might or might not constitute endorsement. This ambiguity
means amendment incorporation is effectively an orchestrator judgment call
rather than a defined process.

---

## Gap 5: Ledger Scaling and Context Window Pressure

**Impact: Medium**

The orchestration instructions say to pass "the full ledger" to every spawned
subagent. With a 5-seat parliament running 6 rounds:

- ~10 exchanges per round (2×5 in early rounds, 1×5 in late rounds)
- Each exchange = 2 messages (question + answer)
- Plus amendments, speaker rulings, vote tallies
- Rough estimate: 80-120 messages in the ledger by round 5-6

Each message includes structured JSON with potentially multi-sentence content.
Combined with the agent prompt, session state, current bill, and task-specific
instructions, late-round agent spawns could approach or exceed context limits
for the Task tool subagents.

There is no mechanism for:
- Ledger summarization (passing a condensed history instead of the full log)
- Selective context (only passing relevant exchanges for the current task)
- Progressive summarization (replacing early-round details with summaries)

---

## Gap 6: Temperature Continuity Breaks in Practice

**Impact: Medium**

The temperature guide (`references/temperature-guide.md`, lines 260-271)
explains that motives stay constant across rounds while only "engagement style
shifts." But the implementation has two problems:

1. **No previous-temperature context**: When a representative is spawned, they
   receive their current temperature but not their previous-round temperature
   or any transition narrative. An agent going from temp 15 (Principled
   Guardian) to temp 85 (Visionary) has no awareness of this shift — they
   simply behave as a Visionary with no memory of having been a Guardian.

2. **Stratified shuffle randomness**: The shuffle step means any agent can land
   in any band. With 5 agents, a rep has a 20% chance of staying in the same
   archetype range and up to a 40% chance of jumping 2+ archetype levels. The
   "BIG SHIFT" annotation in `reassign_temperatures.py` (>30 point delta)
   triggers frequently, but this annotation is printed to stdout — it's not
   passed to the agent.

The temperature guide's claim of "interesting character arcs" depends on the
agent being aware of its arc, which it isn't. In practice, each round spawns a
fresh agent with no personality continuity.

---

## Gap 7: No Mid-Debate PM Intervention

**Impact: Low-Medium**

The PM (user) can only act during Phase 4 (PM Review), after a bill has passed
or been forced. During the 3-6 rounds of active debate, the PM is a passive
observer receiving briefs. They cannot:

- Redirect debate toward a topic they care about
- Inject new information or constraints discovered mid-deliberation
- Signal to agents that a particular direction is unproductive
- Set priorities for the next round

The user might watch 3 rounds of debate heading in a direction they know is
wrong, unable to intervene until the bill formally reaches them. The veto
mechanism is the only corrective tool, and it's expensive — it consumes a round
from the 6-round budget.

---

## Gap 8: Schema Mismatches Between Documents

**Impact: Low**

Several inconsistencies between the protocol, agent prompts, and scripts:

1. **`definitions` field**: The bill.json structure in `communication-protocol.md`
   (line 350) includes `scope.definitions`, but the representative's
   `DRAFT_BILL` return schema in `agents/representative.md` (line 82) omits
   it. The bill template (`references/bill-template.md`) expects definitions.
   A drafter following their prompt schema will produce a bill missing the
   definitions field.

2. **Message type count**: SKILL.md references "10 message types" but the
   communication protocol defines 9 distinct schemas (BILL_DRAFT, QUESTION,
   ANSWER, AMENDMENT, MOTION, VOTE, SPEAKER_RULING, VOTE_TALLY, PM_DECISION).

3. **`stratified_assign` duplication**: The function is copy-pasted across
   `init_parliament.py` and `reassign_temperatures.py` with identical logic.
   If the algorithm is modified in one, the other must be manually synced.

4. **`--num-seats` parameter is decorative**: `init_parliament.py` accepts
   `--num-seats` but uses `len(representatives)` for all actual logic. A
   mismatch only prints a warning — the parameter has no functional effect.

---

## Gap 9: Even-Seat Tie Votes Are Unaddressed

**Impact: Low**

The voting threshold is "50%+ YES" to pass. With an even number of
representatives (4, 6, or 8 seats), a perfect 50-50 split technically fails
(it's exactly 50%, not more than 50%). The skill doesn't address:

- Whether ties should pass or fail
- Tie-breaking mechanisms (Speaker casting vote, drafter tie-break, etc.)
- Whether the seat count recommendation should prefer odd numbers

With 4 seats, a 2-2 split sends the bill back to debate. With 6, a 3-3 split
does the same. This can create frustrating cycles where the parliament can
never reach majority because of structural parity.

---

## Gap 10: No Solution Quality Evaluation

**Impact: Low-Medium**

The final bill is synthesized by the original drafter (Phase 5), who is
inherently biased toward their initial framing. There is no mechanism for:

- An independent evaluation of whether the bill actually solves the stated
  problem
- A "devil's advocate" review by the lowest-temperature agent
- Checking that all constituent issues from Phase 1 are addressed somewhere
  in the final bill
- Measuring coverage: which motives were served, which were compromised, and
  which were ignored

The PM review is the only quality gate, but the PM may lack the multi-
perspective analysis that the parliament itself could provide.

---

## Summary of Gaps by Impact

| # | Gap | Impact |
|---|-----|--------|
| 1 | Single-bill lock-in — no competing proposals | High |
| 2 | No information-gathering or research phase | High |
| 3 | MOTION message type is defined but unreachable | Medium |
| 4 | Amendment endorsement has no formal mechanism | Medium |
| 5 | Ledger scales unboundedly, risks context overflow | Medium |
| 6 | Temperature continuity breaks without transition context | Medium |
| 7 | PM cannot intervene during active debate | Low-Medium |
| 8 | Schema mismatches between documents | Low |
| 9 | Even-seat tie votes have no resolution | Low |
| 10 | No independent quality evaluation of the final bill | Low-Medium |
