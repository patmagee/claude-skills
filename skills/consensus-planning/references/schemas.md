# Message Schemas

All communication flows through a central **log** (`planning/log.json`).
Agents return messages without `id`, `round`, or `timestamp` — the
orchestrator fills those in via `scripts/append_to_log.py`.

## Log Structure

```json
{
  "session_id": "session-20260210-001",
  "problem_statement": "...",
  "messages": []
}
```

## Base Message

```json
{
  "id": "msg-001",
  "type": "<TYPE>",
  "round": 1,
  "timestamp": "2026-02-10T14:30:00Z",
  "from": "<agent_id>"
}
```

## Message Types

**INITIAL_ANALYSIS** — Analyst's opening technical analysis (round 0).

**PROPOSAL_DRAFT** — Analyst drafts or updates the proposal.

**CRITIQUE** — Analyst questions another analyst. Fields: `to`, `content.topic`,
`content.question`, `content.priority_context`. Optional top-level `request`.

**RESPONSE** — Reply to a critique. Fields: `to`, `in_reply_to`,
`content.answer`, `content.concessions`, `content.stance`, `content.priority_scores`.
Optional `content.revision_position` and top-level `request`.

Stance values: `maintain`, `soften`, `concede`, `challenge`.

**REVISION** — Proposed change to the proposal. Fields: `content.revision_id`,
`content.target_section`, `content.action` (add/modify/remove/replace),
`content.description`, `content.rationale`, `content.proposed_text`.

**REQUEST** — Procedural request (extracted from critique/response attachments).
Types: `call_assessment`, `table_discussion`, `request_revision`, `request_compromise`.

**ASSESSMENT** — Analyst's YES/NO vote. Fields: `content.vote`, `content.reasoning`,
`content.priority_scores`, `content.reservations`, `content.conditions`.

**FACILITATOR_RULING** — Procedural decision. Fields: `content.ruling_type`
(order/observation/procedure), `content.action`, `content.ruling`, `content.target`.

**ASSESSMENT_TALLY** — Facilitator announces results. Fields: `content.version`,
`content.yes_votes`, `content.no_votes`, `content.tally`, `content.passed`,
`content.key_objections`, `content.next_action`.

**USER_DECISION** — User's decision. Fields: `content.decision`
(approve/reject/amend_and_approve/guidance), `content.reason`, `content.guidance`.

**REVIEW** — Review agent's evaluation of the final proposal.

## Session State (`planning/session.json`)

```json
{
  "session_id": "...",
  "problem_statement": "...",
  "focus_areas": [],
  "current_round": 1,
  "max_rounds": 6,
  "proposal_version": 1,
  "drafter": "analyst_1",
  "status": "refinement",
  "next_message_id": 15,
  "analysts": [
    {
      "agent_id": "analyst_1",
      "name": "Security Analyst",
      "perspective": 42,
      "perspective_history": [{"round": 0, "perspective": 42}],
      "priorities": ["security", "compliance"],
      "priority_satisfaction": {"security": 2, "compliance": 3},
      "is_quiet": false,
      "voting_record": []
    }
  ],
  "debate_clock": {
    "max_exchanges_per_round": 10,
    "response_budget": 6,
    "exchanges_this_round": 0
  },
  "assessment_history": []
}
```

Status values: `setup`, `analyzing`, `evaluating`, `drafting`, `refinement`,
`assessing`, `review`, `synthesis`, `complete`.

## Proposal (`planning/proposal.json`)

```json
{
  "proposal_id": "PROP-001",
  "title": "...",
  "version": 1,
  "drafter": "analyst_1",
  "sections": {
    "problem": "...",
    "scope": {"in_scope": [], "out_of_scope": [], "assumptions": []},
    "solution": "...",
    "implementation": "..."
  },
  "revisions": [
    {
      "revision_id": "rev-001",
      "proposed_by": "analyst_3",
      "round": 2,
      "target_section": "solution",
      "action": "add",
      "description": "...",
      "status": "incorporated",
      "endorsements": [
        {"agent_id": "analyst_1", "position": "endorse", "round": 2}
      ]
    }
  ]
}
```

Revision status: `proposed`, `debating`, `incorporated`, `rejected`, `withdrawn`.

## Round Summaries (`planning/round-summaries.json`)

```json
[
  {
    "round": 1,
    "summary": "Narrative of what happened",
    "positions": {
      "analyst_1": {"lean": "YES", "key_concern": "..."}
    },
    "key_shifts": [],
    "revisions_actioned": [],
    "assessment_result": null,
    "open_issues": []
  }
]
```
