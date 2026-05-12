from llm.default_plugins.openai_models import Chat


class DeepSeekChat(Chat):
    """Custom chat handler for DeepSeek API."""

    needs_key = "deepseek"
    key_env_var = "DEEPSEEK_API_KEY"

    def build_kwargs(self, prompt, stream):
        kwargs = super().build_kwargs(prompt, stream)
        kwargs.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
        return kwargs

    def __init__(self, model_name):
        super().__init__(
            model_name=model_name,
            model_id=model_name,
            api_base="https://api.deepseek.com",
        )
