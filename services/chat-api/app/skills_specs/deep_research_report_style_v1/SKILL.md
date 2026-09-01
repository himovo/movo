---
name: deep_research_report_style_v1
description: Analyst-grade long report writing style with 15 quality constraints.
category: style
role: style
tags:
  - style
  - research
  - report
  - quality
when_to_use:
  - Use when the user asks for deep analysis, trend reports, market reports, or long-form research writing.
  - Use as writing constraints together with an execution skill.

style_contract:
  structure:
    max_heading_depth: 4
    max_separators: 0
    paragraph_first: false
  visual_policy:
    min_infographics: 0
    image_render_enabled: false
    include_infographic_blocks: false
  defaults:
    opening_style: analytical_overview
    tone: third_party_analyst
    conclusion_style: concise_judgment
  length:
    min_words: 2000
    max_words: 10000
  anti_patterns:
    - "由模型自动生成"
    - "由AI生成"
---

# Purpose
- Provide a reusable writing-style contract for analyst-grade long reports.
- Improve consistency, evidence discipline, and decision usefulness.

# LLM Writing Guidelines

## Role & Tone
Write as an external third-party analyst, not as company management.
Avoid promotional/emotional wording and keep factual tone.
Separate facts from judgments in different sentences or paragraphs.

## Structure
Organize by section objective and keep logic coherent.

## Judgment & Phrasing
Use explicit analytical phrasing (e.g., "it is likely", "this indicates", "under current evidence", "subject to assumptions").

## Forecast Rule
Any forecast must include explicit assumptions.

## Uncertainty Disclosure
When evidence is weak, state uncertainty or data insufficiency explicitly.

## Ending
Conclude with a concise overall judgment, without hype.

## Professionalism
Assume expert readers; avoid basic concept explanations.

## Decision Usefulness
When multiple paths exist, identify dominant path, secondary paths, and deprioritized paths with reasons.

## Counter-consensus
Include at least one potentially non-mainstream judgment when evidence supports it.
Do not be contrarian for its own sake; divergence must be evidence-based.

## Weighting
State relative importance of major drivers; avoid treating all factors equally.

## Opportunity Cost
State what is not worth prioritizing under current assumptions.

## Evidence Hierarchy
Differentiate hard data, secondary sources, expert inference, and scenario reasoning.

## Validity Boundary
State conditions under which the core conclusion no longer holds.

# Output Expectations
- Keep output in the user language.
- Keep section structure clear and stable.
- Keep claims traceable to evidence whenever possible.
