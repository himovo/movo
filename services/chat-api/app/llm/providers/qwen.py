from app.llm.providers.default_openai import DefaultOpenAIClient

class QwenClient(DefaultOpenAIClient):
    """
    Qwen specific overrides or specialized structure support if needed.
    For now, it behaves identically to DefaultOpenAIClient since Qwen 
    offers an OpenAI compatible API endpoint.
    """
    pass
