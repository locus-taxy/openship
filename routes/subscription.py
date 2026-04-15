from fastapi import APIRouter, Request
from schemas.skill import SubscribeRequest
from controllers import subscription as subscription_controller

router = APIRouter(tags=["subscription"])

@router.post("/subscribe")
def subscribe(payload: SubscribeRequest, request: Request):
    return subscription_controller.subscribe_to_skill(payload, request.state.user)
