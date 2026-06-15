from fastapi import APIRouter, Request

from controllers import execute as execute_controller
from schemas.execute import ExecuteRequest, ExecuteResponse

router = APIRouter(prefix="/execute", tags=["execute"])

@router.get("/runtimes")
def get_runtimes():
    return execute_controller.get_available_runtimes()

@router.post("", response_model=ExecuteResponse)
def run_code(payload: ExecuteRequest, request: Request):
    return execute_controller.run_code(payload, request.state.user)
