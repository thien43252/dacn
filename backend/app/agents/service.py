"""Which agents a user may talk to, and the platform agents synced from seed/agents."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manifest import FALLBACK_SLUG, AgentManifest, builtin_manifests
from app.agents.models import Agent, AgentVersion, Installation
from app.auth.models import User
from app.classes.models import ClassRoom

SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "agents"


@dataclass
class ResolvedAgent:
    agent_id: str
    version_id: str
    version: int
    manifest: AgentManifest
    # "platform" (always-on fallback), "class" or "personal".
    source: str
    certification_status: str
    installation_id: str | None = None

    @property
    def slug(self) -> str:
        return self.manifest.slug


async def latest_version(db: AsyncSession, agent_id: str) -> AgentVersion | None:
    return await db.scalar(
        select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version.desc()).limit(1)
    )


async def sync_platform_agents(db: AsyncSession, seed_dir: Path = SEED_DIR) -> list[str]:
    """Creates or updates platform agents from YAML. A changed manifest becomes a new version; returns changed slugs."""
    changed = []
    for slug, manifest in builtin_manifests(seed_dir).items():
        data = manifest.model_dump(mode="json")
        agent = await db.scalar(select(Agent).where(Agent.slug == slug))
        if agent is None:
            agent = Agent(slug=slug, is_platform=True, visibility="public", draft_manifest=data)
            db.add(agent)
            await db.flush()
        latest = await latest_version(db, agent.id)
        if latest is None or latest.manifest != data:
            # Platform manifests are reviewed in the repo; the certification pipeline re-checks them in week 9.
            db.add(
                AgentVersion(
                    agent_id=agent.id,
                    version=(latest.version + 1) if latest else 1,
                    manifest=data,
                    certification_status="certified",
                )
            )
            agent.draft_manifest = data
            changed.append(slug)
    await db.commit()
    return changed


def _resolved(agent: Agent, version: AgentVersion, source: str, installation: Installation | None) -> ResolvedAgent:
    return ResolvedAgent(
        agent_id=agent.id,
        version_id=version.id,
        version=version.version,
        manifest=AgentManifest.model_validate(version.manifest),
        source=source,
        certification_status=version.certification_status,
        installation_id=installation.id if installation else None,
    )


async def available_agents(db: AsyncSession, user: User, room: ClassRoom | None, role: str) -> list[ResolvedAgent]:
    """Agents this user may talk to in this context, fallback first. `role` is the user's role in the class
    (or their account role outside a class). Agents whose manifest does not target that role are left out."""
    found: dict[str, ResolvedAgent] = {}

    fallback = await db.scalar(select(Agent).where(Agent.slug == FALLBACK_SLUG))
    if fallback is not None:
        version = await latest_version(db, fallback.id)
        if version is not None:
            found[FALLBACK_SLUG] = _resolved(fallback, version, "platform", None)

    conditions = [(Installation.scope == "personal") & (Installation.user_id == user.id)]
    if room is not None:
        conditions.append((Installation.scope == "class") & (Installation.class_id == room.id))
    rows = await db.execute(
        select(Installation, Agent, AgentVersion)
        .join(Agent, Agent.id == Installation.agent_id)
        .join(AgentVersion, AgentVersion.id == Installation.agent_version_id)
        .where(
            Installation.enabled.is_(True), conditions[0] if len(conditions) == 1 else (conditions[0] | conditions[1])
        )
        .order_by(Installation.scope, Installation.created_at)
    )
    allow_personal = room is None or bool((room.policy or {}).get("allow_personal_agents", True))
    for installation, agent, version in rows:
        if installation.scope == "personal" and not allow_personal:
            continue
        # Only certified versions reach students and parents; teachers can use their own drafts in their class.
        if role in ("student", "parent") and version.certification_status != "certified":
            continue
        resolved = _resolved(agent, version, installation.scope, installation)
        if role not in resolved.manifest.target_roles or resolved.slug in found:
            continue
        found[resolved.slug] = resolved
    return list(found.values())


async def installed_count(db: AsyncSession, agent_id: str) -> int:
    return await db.scalar(select(func.count()).where(Installation.agent_id == agent_id)) or 0
