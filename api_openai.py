import logging
from openai import OpenAI

# Get the logger that was configured in main.py
LOGGER = logging.getLogger(__name__)

# Get list of OpenAI available models
def get_available_models():
    client = OpenAI()
    models = client.models.list()

    for model in models:
        LOGGER.info(model.id)
    
    return models
