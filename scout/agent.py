"""
Scout — Enterprise Context Agent
================================

A single ``agno.Agent`` with N ``ContextProvider``s. Exposes
``query_<id>`` + ``update_<id>`` tools per registered provider, plus
``list_contexts``. One LLM hop per turn.
"""

from __future__ import annotations

from agno.agent import Agent

from scout.contexts import (
    SLACK_HIDDEN_PROVIDER_IDS,
    context_providers_summary,
    get_context_providers,
    list_contexts,
)
from scout.instructions import SCOUT_INSTRUCTIONS
from scout.settings import agent_db, default_model


def scout_tools() -> list:
    """Build Scout's tool list from the active context providers.

    We use a callable (not a resolved list) so agno re-resolves per run —
    lets eval fixtures swap providers via ``update_context_providers`` and
    see the new tool set immediately, without Scout holding a stale closure.
    """
    tools: list = []
    for ctx in get_context_providers():
        tools.extend(ctx.get_tools())
    tools.append(list_contexts)
    return tools


def scout_slack_tools() -> list:
    """Slack-scoped tool surface.

    Same registry as scout_tools, minus providers in SLACK_HIDDEN_PROVIDER_IDS.
    Used by the Slack-bound agent variant so personal contexts (33god Plane,
    etc.) don't leak into business conversations.
    """
    tools: list = []
    for ctx in get_context_providers():
        if ctx.id in SLACK_HIDDEN_PROVIDER_IDS:
            continue
        tools.extend(ctx.get_tools())
    tools.append(list_contexts)
    return tools


scout = Agent(
    id="scout",
    name="Scout",
    model=default_model(),
    db=agent_db,
    instructions=SCOUT_INSTRUCTIONS,
    tools=scout_tools,
    # Sentinel user_id when a caller (eval runner, unauthenticated script)
    # invokes Scout without identifying the user. Keeps the CRM sub-agent's
    # `{user_id}` prompt template from surviving as a literal into SQL.
    # Production surfaces (UI, Slack) always override this with a real id.
    user_id="anon",
    cache_callables=False,
    # Resolved per run by agno: `{context_providers}` in SCOUT_INSTRUCTIONS
    # gets the live list of registered providers — re-evaluated when eval
    # fixtures swap them.
    dependencies={"context_providers": context_providers_summary},
    enable_agentic_memory=True,
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    markdown=True,
)


# Slack-bound variant. Same instructions, db, and memory as `scout`, so
# sessions and CRM rows cohere across surfaces — only the tool surface is
# scoped (no personal Plane workspace, no future personal contexts that
# join SLACK_HIDDEN_PROVIDER_IDS).
scout_slack = Agent(
    id="scout_slack",
    name="Scout (Slack)",
    model=default_model(),
    db=agent_db,
    instructions=SCOUT_INSTRUCTIONS,
    tools=scout_slack_tools,
    user_id="anon",
    cache_callables=False,
    dependencies={"context_providers": context_providers_summary},
    enable_agentic_memory=True,
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    markdown=True,
)
