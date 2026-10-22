from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.db import get_session
from advocondo.metas.repository import GoalRepository
from advocondo.metas.service import GoalService
from advocondo.users.repository import UserRepository


def get_goal_service(
    session: Annotated[Session, Depends(get_session)],
) -> GoalService:
    return GoalService(session, GoalRepository(session), UserRepository(session))
