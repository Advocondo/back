"""Ponto único de autenticação/autorização das rotas.

O login (US02) ainda não existe: `require_user` é um no-op. Quando ele chegar,
basta implementá-lo aqui; as rotas já o declaram como dependência e não mudam.
"""


def require_user() -> None:
    """Exige um usuário autenticado (ainda não aplicado; ver US02)."""
