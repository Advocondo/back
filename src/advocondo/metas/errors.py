from advocondo.common.errors import BusinessRuleError, NotFoundError


class CollaboratorNotFoundError(NotFoundError):
    message = "Colaborador não encontrado."


class GoalNotFoundError(NotFoundError):
    message = "Meta não encontrada."


class GoalOnlyForOperatorsError(BusinessRuleError):
    message = "Só membros da Equipe Operacional podem ter meta."
