from datetime import date

# Antecedência padrão, em dias, a partir da qual o contrato passa a ser sinalizado.

DEFAULT_RENEWAL_WARNING_DAYS = 60

def is_near_renewal(
    renewal_date: date,
    today: date,
    warning_days: int = DEFAULT_RENEWAL_WARNING_DAYS,
) -> bool:
    """Diz se o contrato deve ser sinalizado como "próximo da renovação".
    O contrato é sinalizado quando faltam `warning_days` dias ou menos para a
    data de renovação. Se a data já passou, o contrato continua sinalizado,
    porque o prazo de renegociação ainda exige uma ação.
    """
    days_until_renewal = (renewal_date - today).days

    return days_until_renewal <= warning_days