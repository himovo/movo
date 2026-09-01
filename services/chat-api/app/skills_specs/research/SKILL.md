name: research
version: 1.0.0
description: General research skill with web search and summarization.
inputs:
  - topic
  - output_spec (optional)
outputs:
  - report.md
tools:
  - search_web
when_to_use:
  - intent == "research"
steps:
  - collect_sources
  - summarize_findings
  - compose_report
validation:
  required_sections:
    - Summary
    - Sources
resources:
  - templates/report.md
  - validation.yaml
