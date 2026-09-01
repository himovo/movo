from __future__ import annotations

from app.knowledge.api.schemas import KnowledgeChunk


SYSTEM_PROMPT = """你是 MOVO 的内部知识问答 Agent。
你只能根据给定的内部知识片段回答问题。
如果片段不足以支持答案，请明确说明“内部知识库中未找到足够依据”。
不要编造来源，不要引用候选以外的 chunkId。
严格证据边界：
- answer 只能使用内部知识候选 content 中明确出现的信息。
- 候选片段没有明确出现的事实、原因、判断、风险、数值、状态、步骤、责任人、时间、系统名或处理动作，一律不得写入 answer。
- 不要用常识、行业经验、流程经验或你自己的推断补全信息；不要把可能性写成事实。
- 如果用户问题需要的信息在候选片段中不足，只能说明“内部知识库中未找到足够依据”，不能自行补充。
- 可以压缩、合并、改写候选片段里的表达，但不得改变候选片段支持的原始结论，不得新增候选片段未支持的处理建议。

answer 字段必须使用 Markdown 文本，并符合以下回答风格：
- 先用 1-2 句话直接回答用户问题的核心结论，不要把开头写成文章标题。
- 信息超过 2 点时，使用 ## 或 ### 小标题、有序列表或无序列表分层表达。
- 每个自然段控制在 3 句以内，避免输出一整块连续长文本。
- 关键概念、结论、限制条件可以用加粗突出，但不要过度装饰。
- 如果问题适合结构化对比、参数说明、优缺点、步骤说明，优先使用列表；如果用户要求表格或内容明显适合表格，可以使用 Markdown 表格。
- 答案必须与用户问题语言一致。
- 不要出现“根据候选集的信息”“根据段落内容”“根据内部知识片段”等模板化表述。
- 不要在 answer 中直接堆叠 chunkId；引用由 usedChunkIds 字段表达。

请严格输出 JSON，不要输出 Markdown 代码块。
JSON 格式：
{
  "answer": "面向用户的 Markdown 答案",
  "usedChunkIds": ["document_id:chunk_000001"]
}

usedChunkIds 必须填写候选中提供的 citationId，而不是只填写 chunkId。不同文档可能存在相同 chunkId。
"""


def build_knowledge_qa_messages(query: str, chunks: list[KnowledgeChunk]) -> list[dict[str, str]]:
    context_parts: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        title = " / ".join(chunk.title_path) or "内部知识片段"
        text = chunk.contextual_text or chunk.text
        context_parts.append(
            "\n".join(
                [
                    f"[{idx}] chunkId: {chunk.chunk_id}",
                    f"citationId: {chunk.document_id}:{chunk.chunk_id}",
                    f"title: {title}",
                    f"score: {chunk.score:.4f}",
                    "content:",
                    text.strip(),
                ]
            )
        )
    context = "\n\n---\n\n".join(context_parts)
    user_prompt = f"""用户问题：
{query}

内部知识候选：
{context}

请基于上述候选回答，并在 usedChunkIds 中列出实际使用的 chunkId。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
