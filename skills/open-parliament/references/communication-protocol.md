# Communication Protocol

All communication between agents flows through a central **ledger** — a JSON array
of messages. The Parliament Clerk (orchestrator) manages the ledger, appending
messages after each agent turn.

## Ledger Structure

The ledger file (`parliament/ledger.json`) is a JSON object:

```json
{
  "parliament_id": "parl-20260210-001",
  "problem_statement": "...",
  "messages": []
}
```

## Message Types

Every message in the ledger follows this base structure:

```json
{
  "id": "msg-001",
  "type": "<MESSAGE_TYPE>",
  "round": 1,
  "timestamp": "2026-02-10T14:30:00Z",
  "from": "<agent_id or 'speaker'>",
  "content": {}
}
```

### BILL_DRAFT

Sent when a representative drafts or updates the bill.

```json
{
  "id": "msg-001",
  "type": "BILL_DRAFT",
  "round": 0,
  "timestamp": "...",
  "from": "rep_1",
  "content": {
    "bill_version": 1,
    "title": "Proposed Solution for X",
    "summary": "Brief description of the proposed approach",
    "sections": {
      "problem": "...",
      "scope": {
        "in_scope": ["..."],
        "out_of_scope": ["..."],
        "assumptions": ["..."]
      },
      "solution": "...",
      "implementation": "..."
    }
  }
}
```

### OPENING_STATEMENT

A representative's opening contribution before bill drafting begins. Produced
during the Opening Statements phase.

```json
{
  "id": "msg-002",
  "type": "OPENING_STATEMENT",
  "round": 0,
  "timestamp": "...",
  "from": "rep_1",
  "content": {
    "briefing": {
      "facts": ["Concrete facts relevant to this rep's motives"],
      "constraints": ["Hard constraints the solution must respect"],
      "precedents": ["Prior art or relevant examples"],
      "open_questions": ["Things the parliament should investigate"]
    },
    "direction": {
      "approach": "3-5 sentence description of proposed direction",
      "principle": "One-sentence core principle driving the approach",
      "trade_offs": "What this direction sacrifices and why"
    }
  }
}
```

### QUESTION

A representative asks a question directed at another representative.

```json
{
  "id": "msg-002",
  "type": "QUESTION",
  "round": 1,
  "timestamp": "...",
  "from": "rep_2",
  "to": "rep_1",
  "content": {
    "topic": "scalability concerns",
    "question": "How does your proposed caching layer handle cache invalidation across distributed nodes? My constituents need guarantees about data consistency.",
    "motive_context": "I'm asking because my constituents care deeply about system reliability."
  }
}
```

### ANSWER

A representative responds to a question.

```json
{
  "id": "msg-003",
  "type": "ANSWER",
  "round": 1,
  "timestamp": "...",
  "from": "rep_1",
  "to": "rep_2",
  "in_reply_to": "msg-002",
  "content": {
    "answer": "The bill proposes an event-driven invalidation model using pub/sub. When any node updates data, it publishes an invalidation event that all other nodes subscribe to.",
    "concessions": "I acknowledge this adds operational complexity, which I know concerns your constituents.",
    "stance": "maintain",
    "motive_scores": {
      "performance": 4,
      "scalability": 3
    },
    "amendment_position": {
      "amendment_id": "amend-001",
      "position": "endorse",
      "reason": "This aligns with our performance requirements."
    }
  }
}
```

The `stance` field indicates whether the respondent's position changed:
- `"maintain"` — Holding their position
- `"soften"` — Open to compromise on this point
- `"concede"` — Accepting the questioner's concern as valid and agreeing to address it
- `"challenge"` — Pushing back on the premise of the question

The `motive_scores` field is required on every ANSWER. Each key is a motive name
matching the representative's assigned motives, and each value is 1-5:
1 = unaddressed, 2 = inadequate, 3 = partial, 4 = mostly addressed, 5 = fully
addressed. These scores are tracked by the orchestrator and used by the Speaker
to gate votes (no vote while any motive scores below 3, unless forced by clock
or round limit).

The `amendment_position` field is optional. Include it when the exchange
relates to a pending amendment, to formally register endorsement or opposition.
Values: `"endorse"`, `"oppose"`, `"abstain"`.

**Optional motion attachment**: Both QUESTION and ANSWER messages may include
an optional top-level `motion` field (alongside `type`, `from`, `content`,
etc.) when the representative wants to make a procedural request. The
orchestrator extracts this and logs it as a separate MOTION entry in the
ledger. See the MOTION schema below.

### AMENDMENT

A representative proposes a change to the bill.

```json
{
  "id": "msg-004",
  "type": "AMENDMENT",
  "round": 2,
  "timestamp": "...",
  "from": "rep_3",
  "content": {
    "amendment_id": "amend-001",
    "target_section": "solution",
    "action": "add",
    "description": "Add a mandatory security audit phase before deployment",
    "rationale": "My constituents require that any solution undergo security review. This is non-negotiable for our compliance requirements.",
    "proposed_text": "Before deployment, the solution must pass a security audit covering OWASP Top 10 and data protection compliance."
  }
}
```

The `action` field can be: `"add"`, `"modify"`, `"remove"`, or `"replace"`.

### MOTION

A representative makes a procedural motion (request to the Speaker).

```json
{
  "id": "msg-005",
  "type": "MOTION",
  "round": 2,
  "timestamp": "...",
  "from": "rep_4",
  "content": {
    "motion_type": "call_vote",
    "reason": "I believe we have debated this sufficiently and should put it to a vote."
  }
}
```

Motion types: `"call_vote"`, `"table_discussion"`, `"request_amendment"`,
`"point_of_order"`, `"request_compromise"`.

### VOTE

A representative casts their vote on the current bill.

```json
{
  "id": "msg-010",
  "type": "VOTE",
  "round": 3,
  "timestamp": "...",
  "from": "rep_1",
  "content": {
    "vote": "YES",
    "reasoning": "While not perfect, this bill adequately addresses my constituents' core concerns about performance and includes the caching layer we advocated for.",
    "motive_scores": {
      "performance": 4,
      "scalability": 3
    },
    "reservations": "I still have concerns about the timeline. I'd prefer a phased rollout.",
    "conditions": []
  }
}
```

The `vote` field is either `"YES"` or `"NO"`. The `conditions` array lists things
that would change the vote (useful for the Speaker to identify paths to consensus).

### SPEAKER_RULING

The Speaker makes a procedural decision.

```json
{
  "id": "msg-006",
  "type": "SPEAKER_RULING",
  "round": 2,
  "timestamp": "...",
  "from": "speaker",
  "content": {
    "ruling_type": "order",
    "ruling": "Rep. Innovatus has been speaking at length without addressing the specific concerns raised. I'm asking them to directly respond to Rep. Securitas's question about data encryption before continuing.",
    "target": "rep_2",
    "action": "redirect"
  }
}
```

Ruling types and actions:

- `"order"` + `"redirect"` — Redirect an agent to address a specific point
- `"order"` + `"quiet"` — Silence an agent for the current round
- `"order"` + `"call_vote"` — End debate and call a vote
- `"observation"` + `"deadlock_warning"` — Warn that debate is going in circles
- `"observation"` + `"progress_note"` — Note positive progress
- `"procedure"` + `"next_speaker"` — Announce who speaks next
- `"procedure"` + `"round_start"` — Announce start of a new round
- `"procedure"` + `"round_end"` — Announce end of a round

### VOTE_TALLY

The Speaker announces vote results.

```json
{
  "id": "msg-015",
  "type": "VOTE_TALLY",
  "round": 3,
  "timestamp": "...",
  "from": "speaker",
  "content": {
    "bill_version": 2,
    "yes_votes": ["rep_1", "rep_3", "rep_5"],
    "no_votes": ["rep_2", "rep_4"],
    "tally": {"yes": 3, "no": 2, "total": 5},
    "passed": true,
    "key_objections": [
      {
        "from": "rep_2",
        "concern": "Cost implications not adequately addressed"
      }
    ],
    "next_action": "advance_to_pm"
  }
}
```

### PM_DECISION

Records the Prime Minister's (user's) decision.

```json
{
  "id": "msg-016",
  "type": "PM_DECISION",
  "round": 3,
  "timestamp": "...",
  "from": "prime_minister",
  "content": {
    "decision": "veto",
    "reason": "The bill doesn't adequately address backwards compatibility. I need the representatives to add a migration strategy.",
    "guidance": "Focus on how existing users will transition to the new system."
  }
}
```

Decision values: `"approve"`, `"veto"`, `"amend_and_approve"`, `"opening_guidance"`.

---

## Agent Response Format

When spawning subagents, they should return their response as a JSON object that
matches one of the message types above (without the `id`, `round`, and `timestamp`
fields — the orchestrator fills those in).

Example of what a representative subagent returns:

```json
{
  "type": "QUESTION",
  "from": "rep_2",
  "to": "rep_1",
  "content": {
    "topic": "...",
    "question": "...",
    "motive_context": "..."
  }
}
```

The orchestrator wraps this with the metadata fields and appends to the ledger.

---

## Session State Structure

The session file (`parliament/session.json`) tracks the full state:

```json
{
  "parliament_id": "parl-20260210-001",
  "problem_statement": "...",
  "constituent_issues": ["issue1", "issue2", "..."],
  "current_round": 1,
  "max_rounds": 6,
  "bill_version": 1,
  "drafter": "rep_1",
  "status": "debate",
  "next_message_id": 15,
  "representatives": [
    {
      "agent_id": "rep_1",
      "name": "Rep. Pragmatis",
      "temperature": 42,
      "temperature_history": [{"round": 0, "temperature": 42}],
      "motives": ["cost efficiency", "time-to-market"],
      "motive_satisfaction": {
        "cost efficiency": 2,
        "time-to-market": 3
      },
      "is_quiet": false,
      "quiet_until_round": null,
      "voting_record": []
    }
  ],
  "debate_clock": {
    "max_exchanges_per_round": 10,
    "response_budget": 6,
    "exchanges_this_round": 0
  },
  "vote_history": []
}
```

Status values: `"setup"`, `"opening_statements"`, `"evaluating_statements"`,
`"drafting"`, `"debate"`, `"voting"`, `"pm_review"`, `"synthesis"`, `"complete"`.

### Debate Clock

The `debate_clock` enforces time pressure on deliberation:

- **`max_exchanges_per_round`**: Hard cap on question-answer pairs per round.
  Shrinks with convergence (round 1: 2×seats, round 6: 1×seats).
- **`response_budget`**: Maximum sentences per agent response. Shrinks as rounds
  progress (round 1: 6 sentences, round 4+: 3 sentences). Agents must be concise.
- **`exchanges_this_round`**: Running count. Reset to 0 at round start.

The Speaker enforces the clock. If an agent exceeds their budget, the Speaker
can summarize and truncate. If exchanges hit the cap, the Speaker must call a
vote or end the round.

## Bill Structure

The bill file (`parliament/bill.json`):

```json
{
  "bill_id": "BILL-001",
  "title": "...",
  "version": 1,
  "drafter": "rep_1",
  "sections": {
    "problem": "...",
    "scope": {
      "in_scope": [],
      "out_of_scope": [],
      "assumptions": [],
      "definitions": []
    },
    "solution": "...",
    "implementation": "..."
  },
  "amendments": [
    {
      "amendment_id": "amend-001",
      "proposed_by": "rep_3",
      "round": 2,
      "target_section": "solution",
      "action": "add",
      "description": "...",
      "status": "incorporated",
      "endorsements": [
        {"agent_id": "rep_1", "position": "endorse", "round": 2},
        {"agent_id": "rep_4", "position": "oppose", "round": 2}
      ]
    }
  ]
}
```

Amendment status values: `"proposed"`, `"debating"`, `"incorporated"`, `"rejected"`,
`"withdrawn"`.

### Amendment Incorporation Threshold

An amendment can be incorporated when:
- The proposer + at least 1 other representative has endorsed it, OR
- The bill's drafter explicitly endorses it (drafter acceptance)

The Speaker may call a formal amendment vote if positions are unclear after
2+ exchanges of discussion. If an amendment has more oppose positions than
endorse positions after discussion concludes, set status to `rejected`.

---

## Round Summaries

Round summaries are generated by the orchestrator at the end of each debate
round and stored in `parliament/round-summaries.json`. They are used for
context windowing — providing older-round context to agents without passing
the full message history.

```json
[
  {
    "round": 1,
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
      {"amendment_id": "amend-001", "status": "incorporated"}
    ],
    "vote_result": null,
    "open_issues": ["Migration path still unresolved"]
  }
]
```

Round summaries are NOT added to the ledger. They are a separate runtime
artifact used for context management.
