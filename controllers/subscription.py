import uuid

from fastapi import HTTPException

from schemas.skill import SubscribeRequest
from services.skill import skill_exists, create_skill


def subscribe_to_skill(payload: SubscribeRequest):
    if skill_exists(payload.email, payload.skill):
        raise HTTPException(status_code=409, detail=f"Already subscribed to '{payload.skill}'")

    user_id = str(uuid.uuid4())
    skill_id = create_skill(user_id, payload.email, payload.skill, payload.days, payload.hours)
    if skill_id is None:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {"status": "success", "message": f"Subscribed to '{payload.skill}'", "user_id": user_id}
