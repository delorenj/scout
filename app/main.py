"""
AgentOS Entrypoint
==================
"""

from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path

from agno.os import AgentOS
from agno.os.config import AuthorizationConfig

from app.router import create_router
from db import get_postgres_db
from scout.agent import scout, scout_slack
from scout.contexts import close_context_providers, setup_context_providers

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
runtime_env = getenv("RUNTIME_ENV", "prd")
scheduler_base_url = getenv("AGENTOS_URL", "http://127.0.0.1:8000")
jwt_jwks_file = getenv("JWT_JWKS_FILE", "").strip()

# Build the AuthorizationConfig only when prod auth is on AND we have a JWKS
# file to read. agno verifies inbound RS256 tokens against the keys in the
# JWKS — no PEM conversion, no multi-line env var. Mount the file at the
# path JWT_JWKS_FILE points to.
authorization_config: AuthorizationConfig | None = None
if runtime_env == "prd" and jwt_jwks_file:
    authorization_config = AuthorizationConfig(jwks_file=jwt_jwks_file)

# ---------------------------------------------------------------------------
# Interfaces — Slack lights up when both env vars are set
# ---------------------------------------------------------------------------
SLACK_BOT_TOKEN = getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = getenv("SLACK_SIGNING_SECRET", "")

interfaces: list = []
if SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET:
    from agno.os.interfaces.slack import Slack

    # Slack uses the scoped variant — personal contexts (33god Plane, etc.)
    # stay out of business conversations. See SLACK_HIDDEN_PROVIDER_IDS in
    # scout/contexts.py to adjust the allowlist.
    interfaces.append(
        Slack(
            agent=scout_slack,
            streaming=True,
            token=SLACK_BOT_TOKEN,
            signing_secret=SLACK_SIGNING_SECRET,
            resolve_user_identity=True,
        )
    )


# ---------------------------------------------------------------------------
# Lifespan — Create tables and wire up contexts
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):  # type: ignore[no-untyped-def]
    from db.tables import create_tables

    create_tables()
    await setup_context_providers()
    try:
        yield
    finally:
        await close_context_providers()


# ---------------------------------------------------------------------------
# Create AgentOS
# ---------------------------------------------------------------------------
agent_os = AgentOS(
    name="Scout",
    tracing=True,
    scheduler=True,
    scheduler_base_url=scheduler_base_url,
    authorization=runtime_env == "prd",
    authorization_config=authorization_config,
    lifespan=lifespan,
    db=get_postgres_db(),
    agents=[scout, scout_slack],
    interfaces=interfaces,
    config=str(Path(__file__).parent / "config.yaml"),
)

app = agent_os.get_app()
app.include_router(create_router(agent_os.settings))


if __name__ == "__main__":
    agent_os.serve(
        app="app.main:app",
        reload=runtime_env == "dev",
    )
