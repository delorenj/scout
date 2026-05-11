"""
Scout Settings
==============

Environment and runtime objects shared across agents.
"""

import os

from agno.models.openai import OpenAIChat, OpenAIResponses

from db import get_postgres_db

agent_db = get_postgres_db()

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-5.4")


def default_model() -> OpenAIChat | OpenAIResponses:
    """Fresh model instance per agent — avoids shared-state footguns.

    When OPENAI_BASE_URL is set (e.g. OpenRouter), use OpenAIChat — third-party
    OpenAI-compatible endpoints implement /chat/completions, not /responses.
    """
    if OPENAI_BASE_URL:
        return OpenAIChat(
            id=OPENAI_MODEL_ID,
            base_url=OPENAI_BASE_URL,
            api_key=OPENAI_API_KEY,
        )
    return OpenAIResponses(id=OPENAI_MODEL_ID)
