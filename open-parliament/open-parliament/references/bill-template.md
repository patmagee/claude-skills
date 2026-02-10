# Bill Template

This is the markdown template for the final bill output. The synthesizing agent
should follow this structure exactly when producing the final document.

---

## Template

```markdown
# [Bill Title]

> **Parliament ID**: [parliament_id]
> **Drafted by**: [drafter name]
> **Rounds of Debate**: [N]
> **Final Vote**: [X] YES / [Y] NO
> **Status**: [Approved | Approved with Amendments | Forced to PM with Dissent]

---

## 1. Problem Statement

[A clear, 2-4 paragraph description of the problem being addressed. This should
cover:]

- What the problem is
- Why it matters (impact of NOT addressing it)
- Who is affected
- What makes this problem difficult or contentious

---

## 2. Scope

### In Scope

[Bulleted list of what this bill covers — the specific aspects of the problem
that the proposed solution addresses.]

### Out of Scope

[Bulleted list of what this bill explicitly does NOT cover. This is important for
setting expectations and preventing scope creep.]

### Assumptions

[Bulleted list of assumptions the solution is built on. If any of these prove
false, the solution may need revisiting.]

### Key Definitions

[If the problem domain has ambiguous or technical terms, define them here so all
stakeholders share a common understanding.]

---

## 3. Proposed Solution

[The core of the bill. This is the solution in its final, agreed-upon form. It
should be specific enough to act on. Structure this section however makes sense
for the problem — it might be a technical architecture, a process, a policy,
a strategy, etc.]

[For complex solutions, use subsections:]

### 3.1 [Component/Phase/Aspect 1]

[Details...]

### 3.2 [Component/Phase/Aspect 2]

[Details...]

---

## 4. Implementation Considerations

[Practical guidance for executing the solution. This might include:]

- Phasing or sequencing
- Resource requirements
- Dependencies
- Risk factors and mitigations
- Success criteria / how to know it's working

---

## 5. Deliberation Record

### Key Debates

[Summary of the most significant debates that shaped the final bill. For each:]

- **Topic**: What was debated
- **Positions**: Who argued what
- **Resolution**: How it was resolved (compromise, concession, amendment, etc.)

### Amendments Incorporated

[List of amendments that were adopted, who proposed them, and why.]

| Amendment | Proposed By | Summary | Round |
|-----------|------------|---------|-------|
| [ID] | [Rep Name] | [Brief description] | [N] |

### Compromises

[Explicit documentation of trade-offs that were made. This transparency helps
stakeholders understand why the solution looks the way it does.]

---

## 6. Dissenting Opinions

[Representatives who voted NO get their objections recorded here. This is a
feature, not a bug — it preserves minority viewpoints for future reference.]

### [Rep Name] — Voted NO

**Core Objection**: [What they disagreed with]

**Unaddressed Concern**: [What motive of theirs was not adequately served]

**Conditions for Support**: [What would need to change for them to vote YES]

---

## 7. Vote Record

| Representative | Vote | Temperature | Reasoning |
|---------------|------|-------------|-----------|
| [Name] | YES/NO | [N] | [Brief reasoning] |

**Final Tally**: [X] YES, [Y] NO ([Z]% approval)
```

---

## Usage Notes

The synthesizing agent should:

1. Fill in ALL sections, even if brief. Empty sections signal incompleteness.
2. Use the actual debate content from the ledger — don't fabricate or generalize.
3. Keep the tone professional and neutral, even when summarizing heated exchanges.
4. Credit specific representatives by name when noting their contributions.
5. Make the Dissenting Opinions section respectful and substantive — these are
   legitimate concerns, not sour grapes.
6. Include enough detail in the Proposed Solution that someone who wasn't in the
   deliberation could understand and act on it.
