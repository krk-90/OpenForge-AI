from llm_gateway.provider.groq_llm import get_model
from llm_gateway.provider.fallback import get_next_model


class ModelRouter:

    def __init__(self, primary_model):
        self.current_model = primary_model

    def get_llm(self):
        while self.current_model:
            try:
                return get_model(self.current_model)

            except Exception:
                self.current_model = get_next_model(
                    self.current_model
                )

        raise RuntimeError("All models failed")