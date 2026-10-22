import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from advocondo.auth.dependencies import CurrentUser
from advocondo.metas.dependencies import get_goal_service
from advocondo.metas.schemas import GoalProgressResponse, GoalRequest, GoalResponse
from advocondo.metas.service import GoalService
from advocondo.users.dependencies import require_admin

MIN_YEAR = 2000
MAX_YEAR = 2100

router = APIRouter(tags=["goals"])

GoalServiceDependency = Annotated[GoalService, Depends(get_goal_service)]


@router.put(
    "/users/{user_id}/goals/{year}/{month}",
    dependencies=[Depends(require_admin)],
)
def define_goal(
    user_id: uuid.UUID,
    year: Annotated[int, Path(ge=MIN_YEAR, le=MAX_YEAR)],
    month: Annotated[int, Path(ge=1, le=12)],
    request: GoalRequest,
    goal_service: GoalServiceDependency,
) -> GoalResponse:
    goal = goal_service.define(user_id, year, month, request)
    return GoalResponse.model_validate(goal)


@router.get("/goals/me")
def get_own_goal(
    current_user: CurrentUser,
    goal_service: GoalServiceDependency,
    year: Annotated[int, Query(ge=MIN_YEAR, le=MAX_YEAR)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> GoalProgressResponse:
    progress = goal_service.get_own_progress(current_user.id, year, month)
    return GoalProgressResponse.from_progress(progress)
