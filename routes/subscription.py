from fastapi import APIRouter, Depends
from models.user import User
from schemas.skill import SubscribeRequest
from dependencies.auth import get_current_user
from controllers import subscription as subscription_controller

router = APIRouter(tags=["subscription"])

@router.post("/subscribe")
def subscribe(payload: SubscribeRequest, current_user: User = Depends(get_current_user)):
    return subscription_controller.subscribe_to_skill(payload, current_user)
