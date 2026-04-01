from fastapi import HTTPException

from models.user import User
from schemas.skill import SubscribeRequest
from services.skill import skill_exists, create_skill


def subscribe_to_skill(user: User, payload: SubscribeRequest):
    if skill_exists(user.email, payload.skill):
        raise HTTPException(status_code=409, detail=f"Already subscribed to '{payload.skill}'")

    user_id = str(user.id)
    skill_id = create_skill(user_id, user.email, payload.skill, payload.days, payload.hours)
    if skill_id is None:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {"status": "success", "message": f"Subscribed to '{payload.skill}'", "user_id": user_id}
