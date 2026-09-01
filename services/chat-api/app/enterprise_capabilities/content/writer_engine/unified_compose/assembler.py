from typing import Any, Dict, List

class ContractPromptAssembler:
    """Lightweight assembler to compile prompt blocks from the normalized output_spec/contract.
    
    Produces 4 blocks:
    - identity_block (Identity & Stance & Formatting)
    - objective_block
    - must_include_block
    - evidence_usage_block
    - fewshot_block (Style Reference)
    """

    @staticmethod
    def assemble_blocks(contract_context: Dict[str, Any]) -> Dict[str, str]:
        ctx = contract_context or {}
        prompt_contract = ctx.get("prompt_contract") or {}
        evidence_policy = ctx.get("evidence_policy") or {}
        subject_resolution = ctx.get("subject_resolution") or {}
        content_task_spec = ctx.get("content_task_spec") if isinstance(ctx.get("content_task_spec"), dict) else {}
        publish_narrative = content_task_spec.get("publish_narrative") if isinstance(content_task_spec.get("publish_narrative"), dict) else {}
        
        # 1. Identity & Forbidden Patterns
        identity = str(prompt_contract.get("identity") or "").strip()
        forbidden_patterns = prompt_contract.get("forbidden_patterns") or []
        forbidden_patterns = [str(x).strip() for x in forbidden_patterns if str(x).strip()]
        forbidden_patterns = list(dict.fromkeys(forbidden_patterns))
        format_rules = prompt_contract.get("formatting_rules") or {}
        anti_patterns = prompt_contract.get("anti_patterns") or {}
        
        identity_lines = []
        if identity:
            identity_lines.append(f"## Role & Identity\n{identity}\n")
            
        if forbidden_patterns:
            bp = "\n".join(f"- {p}" for p in forbidden_patterns)
            identity_lines.append(f"## Forbidden Patterns (🔴 CRITICAL: STRICTLY AVOID)\n{bp}\n")
        if bool(anti_patterns.get("meta_discourse_banned")):
            identity_lines.append("## Meta Discourse Rule\n- Do not narrate writing process (e.g., '接下来我们将...').\n")
            
        if format_rules:
            fr = "\n".join(f"- {k}: {v}" for k, v in format_rules.items())
            identity_lines.append(f"## Formatting Rules\n{fr}\n")
            
        identity_block = "\n".join(identity_lines).strip()

        # 2. Section Objective (This will be dynamically filled by the SectionWriter, but assembler can provide the container)
        # Note: Section objective is usually handled inside components.py via the user prompt. We don't hardcode it here.
        objective_block = ""
        publish_narrative_block = ""
        if publish_narrative:
            lines = ["## Publish Narrative Contract"]
            reader_problem = str(publish_narrative.get("reader_problem") or "").strip()
            narrative_goal = str(publish_narrative.get("narrative_goal") or "").strip()
            opening_intent = str(publish_narrative.get("opening_intent") or "").strip()
            closing_intent = str(publish_narrative.get("closing_intent") or "").strip()
            stance = str(publish_narrative.get("stance") or "").strip()
            if reader_problem:
                lines.append(f"- Write to help the intended reader resolve this concrete problem: {reader_problem}")
            if narrative_goal:
                lines.append(f"- Narrative goal: {narrative_goal}")
            if opening_intent:
                lines.append(f"- Opening intent: {opening_intent}")
            if closing_intent:
                lines.append(f"- Closing intent: {closing_intent}")
            if stance:
                lines.append(f"- Voice and stance: {stance}")
            publish_narrative_block = "\n".join(lines).strip()
        
        # 3. Must Include
        must_include = prompt_contract.get("must_include") or []
        must_include = [str(x).strip() for x in must_include if str(x).strip()]
        must_include = list(dict.fromkeys(must_include))
        if must_include:
            mi = "\n".join(f"- {m}" for m in must_include)
            must_include_block = f"## Required Elements (🔴 CRITICAL: MUST BE COVERED)\n{mi}\n"
        else:
            must_include_block = ""

        evidence_usage_block = ""
        evidence_lines = [
            "## Evidence Usage Contract",
            "- Use evidence selectively.",
            "- Use evidence when it is necessary to identify or disambiguate the subject, support a key factual claim, justify a comparison or recommendation, or avoid making an uncertain claim sound definite.",
            "- Do not force evidence into the body when it only adds noise, repeats common knowledge, or weakens readability without improving correctness.",
            "- If evidence is insufficient to uniquely identify the subject, do not fabricate certainty. Reframe the piece as a disambiguation or candidate-based explanation instead of a definitive introduction.",
            "- Include source references only when they materially help the reader understand or verify an important claim.",
        ]
        if bool(evidence_policy.get("citation_required")):
            evidence_lines.append("- Citation support is required for claims that materially depend on external evidence.")
        status = str(subject_resolution.get("status") or "").strip()
        hint = str(subject_resolution.get("article_goal_hint") or "").strip()
        if status:
            evidence_lines.append(f"- Current subject-resolution status: {status}.")
        if hint:
            evidence_lines.append(f"- Follow this subject-binding guidance: {hint}")
        evidence_usage_block = "\n".join(evidence_lines).strip()
            
        # 4. Few-shot Style References (Placed at the end)
        style_ref = prompt_contract.get("style_reference") or {}
        positive = str(style_ref.get("positive") or "").strip()
        negative = str(style_ref.get("negative") or "").strip()
        
        fewshot_lines = []
        if positive or negative:
            fewshot_lines.append("## Style Reference & Few-Shot Examples (Follow closely!)")
        if positive:
            fewshot_lines.append(f"### Positive Guidance:\n{positive}")
        if negative:
            fewshot_lines.append(f"### Negative Guidance (Do not write like this):\n{negative}")
            
        fewshot_block = "\n\n".join(fewshot_lines).strip()
        
        return {
            "identity_block": identity_block,
            "publish_narrative_block": publish_narrative_block,
            "must_include_block": must_include_block,
            "evidence_usage_block": evidence_usage_block,
            "fewshot_block": fewshot_block,
        }

    @staticmethod
    def assemble_outline_blocks(contract_context: Dict[str, Any]) -> Dict[str, str]:
        """Lightweight contract blocks for outline planning only.

        Keep this intentionally compact to prevent prompt overloading in the outline stage.
        """
        ctx = contract_context or {}
        prompt_contract = ctx.get("prompt_contract") or {}
        structure_contract = ctx.get("structure_contract") or {}

        identity = str(prompt_contract.get("identity") or "").strip()
        role_block = f"## Role & Identity\n{identity}\n" if identity else ""

        required_blocks = [
            str(x).strip()
            for x in (
                (prompt_contract.get("structure_axes") or {}).get("required_blocks")
                or structure_contract.get("required_blocks")
                or []
            )
            if str(x).strip()
        ]
        required_blocks = list(dict.fromkeys(required_blocks))
        anchors_block = ""
        if required_blocks:
            anchors_block = "## Required Section Anchors (STRICT)\n" + "\n".join(f"- {x}" for x in required_blocks) + "\n"

        must_include = [str(x).strip() for x in (prompt_contract.get("must_include") or []) if str(x).strip()]
        must_include = list(dict.fromkeys(must_include))
        must_include_block = ""
        if must_include:
            must_include_block = "## Coverage Checklist\n" + "\n".join(f"- {x}" for x in must_include) + "\n"

        evidence_block = (
            "## Evidence Usage Contract\n"
            "- Use evidence selectively.\n"
            "- Use evidence when it is necessary to bind the subject, support a key claim, or prevent false certainty.\n"
            "- If evidence is insufficient to uniquely identify the subject, do not force a definitive outline; keep it disambiguation-oriented.\n"
        )

        style_ref = prompt_contract.get("style_reference") or {}
        positive = str(style_ref.get("positive") or "").strip()
        fewshot_block = f"## Style Reference\n{positive}\n" if positive else ""

        return {
            "role_block": role_block.strip(),
            "anchors_block": anchors_block.strip(),
            "must_include_block": must_include_block.strip(),
            "evidence_block": evidence_block.strip(),
            "fewshot_block": fewshot_block.strip(),
        }
