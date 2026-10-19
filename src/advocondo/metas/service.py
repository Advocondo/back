from advocondo.metas.errors import GoalOnlyForOperatorsError
from advocondo.users.models import Role


def ensure_role_can_have_goal(role: Role) -> None:
    """Só a Equipe Operacional tem meta: o Cliente não vê esses dados."""
    if role != Role.OPERATOR:
        raise GoalOnlyForOperatorsError()