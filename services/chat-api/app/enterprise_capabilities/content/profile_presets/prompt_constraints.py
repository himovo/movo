"""Shared semantic boundaries for profile and content-review prompts."""

VISUAL_BODY_SEPARATION_CONSTRAINT = (
    "VISUAL DELIVERY VS. READER-FACING BODY:\n"
    "When the user asks to generate, include, or insert images, illustrations, a cover, "
    "or other visuals alongside written content, treat that as a visual production "
    "requirement, not as a request for reader-facing sections about visual production. "
    "Do not turn it into body sections such as image suggestions, cover suggestions, "
    "layout suggestions, visual plans, shot lists, illustration prompts, or equivalent "
    "wording in any language. The reader-facing required_blocks must describe only the "
    "written deliverable. Record visual requirements in visual_contract when that field "
    "is available; downstream visual planning will create and insert the actual assets "
    "after the written body is accepted. Only include visual advice in the written body "
    "when the user explicitly asks for advice, a plan, prompts, or specifications instead "
    "of asking for actual visuals. This semantic boundary overrides an inferred visual "
    "section, but it must not remove an explicitly requested reader-facing visual-advice "
    "section."
)


CONTENT_REVIEW_VISUAL_BOUNDARY = (
    "When written content also requires actual generated visuals, do not create standards "
    "requiring the body to contain image suggestions, cover suggestions, layout advice, "
    "visual plans, illustration prompts, or other production notes. Those are not a textual "
    "substitute for the requested assets and are handled by downstream visual production. "
    "Only evaluate such advice as body content when the user explicitly asks for advice, "
    "a plan, prompts, or specifications rather than actual visuals."
)
