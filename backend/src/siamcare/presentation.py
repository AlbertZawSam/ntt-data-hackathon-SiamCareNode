"""JSON presentation shared by CLI commands, without leaking into services."""

import json

from pydantic import BaseModel


def render_json(result: BaseModel | tuple[BaseModel, ...]) -> str:
    payload = (
        result.model_dump(mode="json")
        if isinstance(result, BaseModel)
        else [item.model_dump(mode="json") for item in result]
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)
