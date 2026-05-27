from openai import OpenAI


class SambaNova(OpenAI):
    def __init__(self, api_key, base_url="https://api.sambanova.ai/v1", **kwargs):
        if not api_key:
            api_key = "placeholder"
        super().__init__(api_key=api_key, base_url=base_url, **kwargs)
