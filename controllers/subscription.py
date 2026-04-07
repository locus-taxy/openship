from fastapi import HTTPException
from models.user import User
from schemas.skill import SubscribeRequest
from services.skill import skill_exists, create_skill

def subscribe_to_skill(payload: SubscribeRequest, current_user: User):
    if skill_exists(current_user.email, payload.skill):
        raise HTTPException(status_code=409, detail=f"Already subscribed to '{payload.skill}'")

    skill_id = create_skill(
        str(current_user.id), current_user.email, payload.skill, payload.days, payload.hours
    )
    if skill_id is None:
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    return {"status": "success", "message": f"Subscribed to '{payload.skill}'"}
