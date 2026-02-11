# Open Parliament — Solutions for Identified Gaps

Concrete solutions for the 6 high and medium impact gaps identified in
`ASSESSMENT.md`. Each solution specifies the design rationale, the exact
files affected, new schemas, and how the change integrates with the existing
architecture.

---

## Solution 1+2: Opening Statements Phase

**Addresses**: Gap 1 (single-bill lock-in) and Gap 2 (no research phase)

### Problem

The current flow goes directly from problem framing to a single
representative drafting the bill. This anchors the entire deliberation to
one person's framing and provides no mechanism for surfacing domain knowledge
or exploring alternative solution architectures.

### Design

Add a new **Phase 2: Opening Statements** between the current Phase 1
(Setup) and current Phase 2 (Bill Drafting, which becomes Phase 3). All
representatives are spawned in parallel to produce opening statements before
any bill is drafted.

Each opening statement has two sections:

1. **Briefing** — Facts, constraints, precedents, risks, and open questions
   relevant to the representative's motives. This is the research/discovery
   component that surfaces domain knowledge the parliament needs.
2. **Direction** — A high-level solution approach (3-5 sentences) the rep
   would advocate for. Not a full bill — just a directional sketch. This
   exposes fundamentally different solution architectures before the
   parliament commits to one.

After all statements are in, the Speaker evaluates them, identifies the
distinct solution directions, and selects a drafter. Critically, the drafter
is instructed to synthesize across ALL opening statements — not just draft
from their own perspective. The PM reviews the collected briefings and can
inject additional facts or steer direction before drafting begins.

### Why This Works

- **Solves both gaps with one phase**: Briefings surface domain knowledge
  (Gap 2); directions expose competing approaches (Gap 1).
- **Preserves the single-bill model**: The parliament still converges on one
  bill for debate. The difference is that the bill is informed by collective
  input rather than one rep's perspective.
- **Efficient**: All reps are spawned in parallel (one Task call with N
  parallel invocations), so this adds one round of parallelized work, not N
  sequential spawns.
- **Fits the hub-and-spoke architecture**: Statements flow through the
  ledger like any other message. The orchestrator mediates.

### File Changes

#### `SKILL.md` — New Phase 2: Opening Statements

Insert between current Phase 1 (Setup) and Phase 2 (Bill Drafting).
Renumber subsequent phases (Bill Drafting becomes Phase 3, Debate becomes
Phase 4, PM Review becomes Phase 5, Synthesis becomes Phase 6).

```markdown
## Phase 2: Opening Statements (Round 0)

Before any bill is drafted, every representative presents an opening
statement. This surfaces domain knowledge and exposes competing solution
directions.

### Step 5: Gather Opening Statements

Spawn ALL representatives in parallel (multiple Task calls in one message).
Each representative receives:

- The problem statement
- Their motives
- The full roster
- Instructions to produce an OPENING_STATEMENT

Each statement contains:
1. A briefing on facts, constraints, and precedents from their motive area
2. A directional sketch of their preferred solution approach (3-5 sentences)

Append all statements to the ledger.

### Step 6: Speaker Evaluates Directions

Spawn the Speaker with all opening statements visible. The Speaker:

1. Synthesizes the briefings into a shared **fact base** — the key facts,
   constraints, and assumptions the parliament should treat as common ground
2. Identifies the distinct solution directions proposed (typically 2-4)
3. Selects a drafter — the rep whose direction best synthesizes multiple
   concerns, or whose motives are broadest

The Speaker's evaluation is logged as a SPEAKER_RULING with action
`evaluate_statements`.

### Step 7: PM Reviews

Present the fact base and identified solution directions to the user. The
PM can:

- Add facts or constraints the representatives missed
- Signal preference for a solution direction (non-binding but influential)
- Approve or override the Speaker's drafter selection

Record any PM input as a PM_DECISION with decision `opening_guidance`.

### Step 8: Draft the Bill (informed by statements)

Proceed to bill drafting as before, but the drafter now receives:

- All opening statements (the full set, not just their own)
- The Speaker's fact base synthesis
- Any PM guidance
- Instructions to synthesize across statements, not just draft from their
  own direction
```

#### `agents/representative.md` — New OPENING_STATEMENT Task

Add after the existing "How You're Invoked" section, before DRAFT_BILL:

```markdown
### OPENING_STATEMENT

Parliament is gathering perspectives before drafting begins. You need to
contribute two things:

1. **Briefing**: Surface the facts, constraints, precedents, risks, and open
   questions that are relevant to your motives. What does the parliament need
   to know about your domain before proposing a solution? Be specific — cite
   concrete constraints, not abstract concerns.

2. **Direction**: Sketch a high-level solution approach you'd advocate for
   (3-5 sentences). This isn't a full bill — it's a directional proposal.
   What's the core idea? What principle should drive the solution?

Your temperature shapes the balance:
- Hot: Bold direction, focus on the transformative opportunity
- Warm: Balanced direction, practical but forward-looking briefing
- Cool: Evidence-heavy briefing, cautious direction grounded in precedent
- Cold: Constraint-heavy briefing, minimal direction focused on risk avoidance

Return:
```json
{
  "type": "OPENING_STATEMENT",
  "from": "<your_agent_id>",
  "content": {
    "briefing": {
      "facts": ["Concrete facts relevant to your motives"],
      "constraints": ["Hard constraints the solution must respect"],
      "precedents": ["Prior art or relevant examples"],
      "open_questions": ["Things the parliament should investigate"]
    },
    "direction": {
      "approach": "3-5 sentence description of your proposed direction",
      "principle": "The one-sentence core principle driving your approach",
      "trade_offs": "What this direction sacrifices and why that's acceptable"
    }
  }
}
```
```

#### `agents/speaker.md` — New EVALUATE_STATEMENTS Task

Add after SELECT_DRAFTER:

```markdown
### EVALUATE_STATEMENTS

All representatives have submitted opening statements. Review them and:

1. **Synthesize a fact base**: Compile the key facts, constraints, and
   precedents from all briefings into a unified summary. Note where
   representatives agree on facts and where they disagree.

2. **Identify solution directions**: Group the proposed directions into
   distinct approaches (typically 2-4). Name each direction concisely.
   Note which representatives align with which direction.

3. **Select a drafter**: Choose who should draft the initial bill. Prefer
   the representative whose direction best synthesizes multiple concerns.
   If directions are strongly divergent, prefer a moderate-temperature rep
   who can bridge them.

Return:
```json
{
  "type": "SPEAKER_RULING",
  "from": "speaker",
  "content": {
    "ruling_type": "procedure",
    "action": "evaluate_statements",
    "ruling": "Having reviewed all opening statements, I identify [N]
               distinct approaches...",
    "fact_base": {
      "agreed_facts": ["Facts multiple reps cited"],
      "contested_facts": ["Facts where reps disagree"],
      "key_constraints": ["Hard constraints from briefings"],
      "open_questions": ["Unresolved questions to keep in mind"]
    },
    "solution_directions": [
      {
        "name": "Short label for this direction",
        "description": "Brief summary",
        "advocates": ["agent_ids who proposed similar approaches"],
        "strengths": "What this direction does well",
        "risks": "What this direction may miss"
      }
    ],
    "target": "<selected_drafter_agent_id>"
  }
}
```
```

#### `references/communication-protocol.md` — New Message Type

Add after the BILL_DRAFT section:

```markdown
### OPENING_STATEMENT

A representative's opening contribution before bill drafting begins.

```json
{
  "id": "msg-002",
  "type": "OPENING_STATEMENT",
  "round": 0,
  "timestamp": "...",
  "from": "rep_1",
  "content": {
    "briefing": {
      "facts": ["..."],
      "constraints": ["..."],
      "precedents": ["..."],
      "open_questions": ["..."]
    },
    "direction": {
      "approach": "...",
      "principle": "...",
      "trade_offs": "..."
    }
  }
}
```
```

Add `"opening_guidance"` to PM_DECISION's decision values.

Add `"opening_statements"` and `"evaluate_statements"` to session status
values (between `"setup"` and `"drafting"`).

#### `scripts/init_parliament.py` — No Changes

The init script doesn't need modification. Opening statements happen after
initialization, using the same session state.

### Round Budget Impact

This adds one parallelized spawn (all reps) + one Speaker spawn + one PM
interaction before drafting. Total: 2 subagent rounds and 1 user turn. The
bill drafting that follows is the same as today. Net cost is modest relative
to the improvement in bill quality.

---

## Solution 3: Activate MOTION via Optional Attachments

**Addresses**: Gap 3 (MOTION message type is dead code)

### Problem

The communication protocol defines a MOTION message type with 5 subtypes,
and the Speaker is written to handle motions, but no representative task
type produces MOTION messages. Representatives have no procedural voice.

### Design

Rather than adding a dedicated SUBMIT_MOTION task type (which would require
the orchestrator to decide when to give reps a chance to make motions),
allow motions as **optional attachments** to existing interactions. When a
representative performs an ASK_QUESTION or RESPOND task, they may include a
`motion` field alongside their primary output.

This is natural: in real parliaments, representatives raise points of order
or call for votes during regular discourse, not in designated "motion slots."

### Why This Over a Dedicated Task Type

A dedicated SUBMIT_MOTION task would require the orchestrator to predict
when a rep wants to make a motion and spawn them specifically for it.
That's backwards — motions are reactive and spontaneous. Attaching them to
existing interactions lets reps signal procedural concerns organically when
they arise.

### File Changes

#### `agents/representative.md` — Optional Motion Field

Add to the ASK_QUESTION section, after the return schema:

```markdown
**Optional motion**: If you feel strongly that a procedural action is
needed (call a vote, request a compromise, raise a point of order), you may
attach a motion to your message. Add a `motion` field alongside your
primary response:

```json
{
  "type": "QUESTION",
  "from": "<your_agent_id>",
  "to": "<target_agent_id>",
  "content": { ... },
  "motion": {
    "motion_type": "call_vote | table_discussion | request_amendment | point_of_order | request_compromise",
    "reason": "Why you're making this motion"
  }
}
```

Only attach a motion when you genuinely believe the procedural action would
serve the parliament. The Speaker will evaluate it — motions are requests,
not commands.
```

Add the same note to the RESPOND section.

#### `SKILL.md` — Motion Extraction in Orchestration

Add to the "During a Round" section, after step 4 (messages appended to
ledger):

```markdown
4b. **Check for motions**: If the representative's response includes a
    `motion` field, extract it and append a separate MOTION message to the
    ledger (using the existing MOTION schema from the communication
    protocol). Pass the motion to the Speaker as part of the next
    NEXT_ACTION decision.
```

#### `references/communication-protocol.md` — No Schema Changes

The MOTION schema already exists and is complete. No changes needed.

#### `agents/speaker.md` — No Changes

The Speaker's NEXT_ACTION task already references motions: "Representatives
may submit MOTION messages... you may acknowledge, deny, or act on motions
at your discretion." This works as-is once motions actually appear in the
ledger.

### Behavioral Notes

- Motions should be rare. Most exchanges will not include one. The
  representative prompt should frame motions as exceptional, not routine.
- The orchestrator logs the motion as a separate ledger entry from the
  Q&A message, preserving clean message type semantics.
- The Speaker sees the motion when evaluating NEXT_ACTION and can respond
  in their ruling.

---

## Solution 4: Formal Amendment Endorsement via Stance Extension

**Addresses**: Gap 4 (amendment endorsement has no formal mechanism)

### Problem

The amendment lifecycle says incorporation requires "at least one other rep
endorses it during debate," but there's no structured way to express
endorsement. The orchestrator must subjectively interpret free-text answers.

### Design

Extend the RESPOND task's return schema with an optional
`amendment_position` field. When the discussion topic relates to a pending
amendment (the orchestrator or Speaker indicates this in the task context),
the responding rep can formally state their position on the amendment.

The orchestrator tallies these positions on the amendment object in
`bill.json`. Incorporation threshold: proposer + 1 explicit endorsement,
OR drafter acceptance.

### Why Extend RESPOND Rather Than Add a New Task

Amendment discussion happens naturally during Q&A exchanges. A rep doesn't
need a separate spawn to endorse — they endorse (or oppose) as part of
responding to the amendment's substance. This keeps the interaction flow
natural and avoids adding orchestration complexity.

### File Changes

#### `agents/representative.md` — Extend RESPOND Return Schema

Replace the current RESPOND return schema with:

```json
{
  "type": "ANSWER",
  "from": "<your_agent_id>",
  "to": "<questioner_agent_id>",
  "in_reply_to": "<message_id>",
  "content": {
    "answer": "Your response",
    "concessions": "Any points you're willing to concede (or null)",
    "stance": "maintain | soften | concede | challenge",
    "amendment_position": {
      "amendment_id": "amend-NNN",
      "position": "endorse | oppose | abstain",
      "reason": "Brief explanation"
    }
  }
}
```

Add guidance:

```markdown
**Amendment position**: If the exchange relates to a pending amendment,
state your formal position. The orchestrator tracks these to determine
whether the amendment has enough support for incorporation.

- `endorse`: You support incorporating this amendment into the bill
- `oppose`: You oppose this amendment
- `abstain`: You have no strong position (use sparingly)

The `amendment_position` field is optional. Omit it when the exchange
isn't about a specific amendment.
```

#### `references/communication-protocol.md` — Amendment Endorsement Tracking

Add to the bill.json amendment schema:

```json
{
  "amendment_id": "amend-001",
  "proposed_by": "rep_3",
  "round": 2,
  "target_section": "solution",
  "action": "add",
  "description": "...",
  "status": "debating",
  "endorsements": [
    {"agent_id": "rep_1", "position": "endorse", "round": 2},
    {"agent_id": "rep_4", "position": "oppose", "round": 2}
  ]
}
```

Add incorporation rule:

```markdown
**Incorporation threshold**: An amendment can be incorporated when:
- The proposer + at least 1 other representative has endorsed it, OR
- The bill's drafter explicitly endorses it (drafter acceptance)

The Speaker may call a formal amendment vote if positions are unclear
after 2+ exchanges of discussion.
```

#### `SKILL.md` — Update Amendment Lifecycle

Replace the current amendment incorporation language (lines 212-224) with:

```markdown
3. **Endorsed**: During debate about the amendment, representatives state
   their position via the `amendment_position` field in their responses.
   The orchestrator records these in the amendment's `endorsements` array
   in `parliament/bill.json`.
4. **Incorporated**: When the amendment has the proposer + 1 endorsement
   (or drafter acceptance), the orchestrator updates the bill text and
   sets status to `incorporated`. Increment `bill_version`.
5. **Rejected**: If the amendment has more oppose positions than endorse
   positions after discussion concludes, set status to `rejected`.
```

---

## Solution 5: Progressive Ledger Summarization

**Addresses**: Gap 5 (ledger scales unboundedly, risks context overflow)

### Problem

The orchestration instructions say to pass "the full ledger" to every agent
spawn. By round 5-6 with 5 seats, the ledger contains 80-120 messages. This
risks exceeding context limits for spawned subagents, especially since each
spawn also receives the agent prompt, session state, current bill, and
task-specific instructions.

### Design

Implement **progressive summarization**: the orchestrator generates a
structured round summary at the end of each round, and older rounds are
passed to agents as summaries rather than full message logs.

The context window strategy for spawning an agent in round R:

| Content | Source |
|---------|--------|
| Rounds 0 through R-2 | Summaries only |
| Round R-1 | Full messages |
| Round R (current) | Full messages so far this round |

This bounds the ledger context to approximately 2 rounds of full detail
plus compact summaries, regardless of how many rounds have elapsed.

### Round Summary Structure

At the end of each round, the orchestrator (not a subagent — this is
generated by the Clerk directly to avoid an extra spawn) produces:

```json
{
  "round": 2,
  "summary": "2-3 sentence narrative of what happened this round",
  "positions": {
    "rep_1": {"lean": "YES", "key_concern": "Wants phased rollout"},
    "rep_2": {"lean": "NO", "key_concern": "Encryption gap unresolved"}
  },
  "key_shifts": [
    "Rep. Innovatus conceded on encryption-at-rest requirement",
    "Rep. Securitas softened on timeline after seeing phased proposal"
  ],
  "amendments_actioned": [
    {"amendment_id": "amend-001", "status": "incorporated"},
    {"amendment_id": "amend-002", "status": "rejected"}
  ],
  "vote_result": null,
  "open_issues": ["Migration path still unresolved"]
}
```

### File Changes

#### `SKILL.md` — Round Summary Generation + Context Windowing

Add to the end of each round's flow (after the last exchange and before
advancing to the next round):

```markdown
### At the End of Each Round

Before advancing to the next round, generate a **round summary** for the
round that just completed. This summary is produced by you (the Clerk), not
by a subagent. Base it on the observer briefs you already generated.

Write the summary to `parliament/round-summaries.json` (an array of summary
objects, one per completed round).

### Context Windowing for Agent Spawns

When spawning any subagent, provide ledger context using a sliding window:

- **Round summaries** for all rounds prior to the previous round (compact)
- **Full messages** for the previous round and the current round (detailed)
- **Always include**: the full bill, session state, and opening statements

This keeps agent context bounded regardless of how many rounds have elapsed.
The full ledger remains on disk for the final synthesis phase, which needs
the complete record for the deliberation summary.
```

Update the "Spawning Subagents" section's point 3:

```markdown
3. The ledger context (using the context windowing strategy above — NOT
   necessarily the full ledger for rounds 3+)
```

#### `references/communication-protocol.md` — Round Summary Schema

Add a new section:

```markdown
## Round Summaries

Round summaries are generated by the orchestrator at the end of each round
and stored in `parliament/round-summaries.json`. They are used for context
windowing — providing older-round context to agents without passing the
full message history.

```json
[
  {
    "round": 1,
    "summary": "...",
    "positions": {},
    "key_shifts": [],
    "amendments_actioned": [],
    "vote_result": null,
    "open_issues": []
  }
]
```

Round summaries are NOT added to the ledger. They are a separate runtime
artifact used for context management.
```

#### `SKILL.md` Phase 6 (Final Synthesis) — Full Ledger Exception

Add a note that the final synthesis spawn receives the **full ledger**, not
the windowed version, because it needs complete detail for the deliberation
record section of the bill:

```markdown
Pass the drafter the **complete** `parliament/ledger.json` (not the
windowed version used during debate). The final bill's deliberation record
requires full detail from all rounds.
```

#### Runtime Artifact

New file: `parliament/round-summaries.json` — created by the orchestrator
at the end of Round 1, appended after each subsequent round.

---

## Solution 6: Temperature History and Transition Context

**Addresses**: Gap 6 (temperature continuity breaks without transition
context)

### Problem

Each round, representatives receive a new temperature but have no awareness
of their previous temperature. The "character arcs" described in the
temperature guide can't emerge when agents are spawned fresh each time with
no memory of their prior engagement style.

### Design

Track each representative's temperature history in `session.json` and pass
a **transition narrative** when spawning agents whose temperature has
shifted significantly. The narrative is a 1-2 sentence note generated by the
orchestrator that frames the shift as a natural evolution, not a personality
reset.

### Temperature History Tracking

Add a `temperature_history` array to each representative in session.json:

```json
{
  "agent_id": "rep_1",
  "name": "Rep. Pragmatis",
  "temperature": 62,
  "temperature_history": [
    {"round": 0, "temperature": 18},
    {"round": 1, "temperature": 72},
    {"round": 2, "temperature": 62}
  ],
  "motives": ["cost efficiency", "time-to-market"],
  ...
}
```

### Transition Narrative

When spawning a representative, the orchestrator includes a brief context
note if the temperature shifted by more than 15 points:

> "Last round you engaged as a Principled Guardian (temp 18) — cautious,
> evidence-focused, brief. This round you're a Pragmatic Advocate (temp 62).
> Your motives haven't changed. But where last round you were anchoring the
> group to hard constraints, this round you're more open to finding creative
> compromises that still respect those constraints. Build on the positions
> you've already established."

For shifts of 15 or less, a simpler note:

> "Your temperature shifted slightly from 72 to 62. Your approach is
> largely the same — still a Pragmatic Advocate — but slightly more
> measured this round."

For no archetype change (e.g., 55 to 68, both Pragmatic Advocate):

> No transition note needed. Just include the current temperature.

### File Changes

#### `scripts/init_parliament.py` — Initialize Temperature History

In `create_session()`, add `temperature_history` to each representative:

```python
session["representatives"].append({
    "agent_id": agent_id,
    "name": rep["name"],
    "temperature": temperatures[i],
    "temperature_history": [
        {"round": 0, "temperature": temperatures[i]}
    ],
    "motives": rep.get("motives", []),
    "is_quiet": False,
    "quiet_until_round": None,
    "voting_record": []
})
```

#### `scripts/reassign_temperatures.py` — Record History Before Overwriting

In the main loop where temperatures are applied, append to history before
overwriting:

```python
for i, rep in enumerate(session["representatives"]):
    old_temp = rep["temperature"]
    new_temp = new_temps[i]

    # Record history before overwriting
    if "temperature_history" not in rep:
        rep["temperature_history"] = []
    rep["temperature_history"].append({
        "round": next_round,
        "temperature": new_temp
    })

    rep["temperature"] = new_temp
```

#### `agents/representative.md` — Temperature Continuity Section

Add after the existing "Temperature Guide (Summary)" section:

```markdown
## Temperature Continuity

Your temperature changes between rounds, but your motives and substantive
positions do not. When you receive a transition note, use it to understand
how your engagement style has shifted:

- If you were a Guardian last round and are now a Visionary, you still
  care about the same things — but now you're looking for creative,
  ambitious ways to address them rather than cautious, risk-averse ones.
- If you were a Visionary and are now a Skeptic, your bold ideas from
  last round are still yours — but now you're stress-testing them with
  the same rigor you'd apply to anyone else's proposals.

Your positions should evolve naturally through debate, not reset with each
temperature change. Reference your prior statements in the ledger to
maintain continuity.
```

#### `SKILL.md` — Transition Narrative in Spawn Instructions

Add to the "Spawning Subagents" section:

```markdown
6. If the representative's temperature shifted by more than 15 points since
   their last spawn, include a 1-2 sentence **transition narrative** that
   frames the shift. Generate this yourself based on the `temperature_history`
   in session.json and the archetype descriptions. The narrative should
   connect the old engagement style to the new one while emphasizing that
   motives and prior positions remain intact.
```

---

## Implementation Priority

These solutions are ordered by implementation dependency, not just impact:

| Order | Solution | Reason |
|-------|----------|--------|
| 1 | **Solution 6** (temperature history) | Smallest change, no structural impact, improves every subsequent round |
| 2 | **Solution 3** (activate MOTION) | Schema already exists, only needs attachment plumbing |
| 3 | **Solution 4** (amendment endorsement) | Extends existing RESPOND schema, small orchestration change |
| 4 | **Solution 5** (ledger summarization) | New runtime artifact, changes spawn pattern, moderate complexity |
| 5 | **Solution 1+2** (opening statements) | Largest change — new phase, new task types, new Speaker task, PM interaction point |

Solutions 1-4 are independent and could be implemented in parallel.
Solution 5 becomes more valuable as the others are implemented (more agent
interactions = larger ledger = more context pressure).
