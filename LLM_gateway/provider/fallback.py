import os
import yaml
from dotenv import load_dotenv
from pathlib import Path
from .groq_llm import get_model
load_dotenv()


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "APP/core/config.yml"

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

models = config["llm_provider"]["models"]

def get_next_model(current_model: str):
    try:
        index = models.index(current_model)

        if index + 1 < len(models):
            return models[index + 1]

    except ValueError:
        pass

    return None