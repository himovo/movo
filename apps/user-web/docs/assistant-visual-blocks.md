# Assistant visual blocks

The chat renderer accepts standard Markdown and an optional fenced `movo-visual` block. The fence body is JSON. It is parsed into a fixed set of Vue components; it is never treated as HTML. Invalid blocks remain visible as code.

Supported `kind` values:

| Kind | Intended use |
| --- | --- |
| `metrics` | Small numeric comparisons |
| `priorities` | Ranked recommendations |
| `flow` | A short sequence or layered relationship |
| `timeline` | Milestones or phases |
| `insights` | Distinct conclusions |
| `checklist` | Items to review or complete |

Example:

````markdown
```movo-visual
{
  "kind": "metrics",
  "title": "Runtime capacity",
  "items": [
    { "label": "Personal runtimes", "value": "1,000", "detail": "One logical runtime per user", "tone": "blue" },
    { "label": "Sandboxes", "value": "On demand", "detail": "Created for tasks that need execution", "tone": "green" }
  ],
  "note": "Illustrative architecture, not a capacity benchmark."
}
```
````

Each block needs one to twelve items. Every item needs `label` and may include `value`, `detail`, `tone` (`blue`, `green`, `amber`, or `purple`), and `checked` for checklists. `title` and `note` are optional. If `kind` is missing, the renderer can infer it from a recognizable title or the preceding heading in Chinese or English. Include `kind` whenever possible; an unrecognized block remains visible as code. Keep cards selective; regular prose is preferable for most answers. Source cards are outside this contract.
