from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.deps import CurrentUser
from app.tools.registry import TOOLS, _llm_schema

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolOut(BaseModel):
    name: str
    title: str
    description: str
    roles: list[str]
    needs_class: bool
    parameters: dict


@router.get("", response_model=list[ToolOut])
async def list_tools(_: CurrentUser) -> list[ToolOut]:
    return [
        ToolOut(
            name=tool.name,
            title=tool.title,
            description=tool.description,
            roles=sorted(tool.roles),
            needs_class=tool.needs_class,
            parameters=_llm_schema(tool.args),
        )
        for tool in TOOLS.values()
    ]
