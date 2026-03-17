# Consensus Planning

Multi-agent consensus planning system. Spawns a panel of AI analysts with
diverse analytical perspectives to collaboratively solve problems through
structured rounds of critique, revision, and assessment.

## How It Works

1. **Discovery** — Clarifying questions to deeply understand the problem
2. **Brainstorm** — Each analyst independently analyzes the problem using
   structured brainstorming techniques (constraint analysis, risk identification,
   prior art, "how might we" framing)
3. **Draft** — A selected analyst drafts an initial proposal informed by all analyses
4. **Refine** — Up to 6 rounds of structured critique and revision. Perspective
   scores shift each round (bold early, converging later) to ensure creative
   tension followed by consensus pressure
5. **Review** — An independent review agent evaluates completeness, feasibility,
   risk coverage, and consensus quality
6. **Deliver** — Final polished document with full deliberation record

## Key Mechanics

- **Perspective scores** (0-100): Shape each analyst's analytical style from
  Bold (creative/ambitious) to Conservative (risk-averse/stability-focused).
  Assigned via stratified randomness with convergence pressure across rounds.
- **Debate clock**: Exchange count and sentence budget tighten each round,
  forcing increasingly focused discussion.
- **Dissent pressure**: Stance guards prevent early concessions. Assessment
  gating ensures all priorities get attention before any vote.
- **Independent review**: A fresh-perspective review agent catches blind spots
  after the panel finishes.

## Trigger Phrases

- "consensus plan"
- "multi-perspective analysis"
- "brainstorm from all angles"
- "structured debate"
- Any request benefiting from adversarial collaboration

## Usage

Point Claude at the skill directory. The session runs interactively — Claude
handles all orchestration, spawning analysts as subagents with independent
context windows.

Runtime files are created in a `planning/` directory and are not checked in.
