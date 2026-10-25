from decimal import Decimal


def format_brl(amount: Decimal) -> str:
    """Escreve um valor em reais como "R$ 1.234,56".

    Não usa o módulo `locale`: o resultado dependeria da configuração do sistema
    operacional e mudaria de uma máquina para outra.
    """
    integer_and_cents = f"{amount:,.2f}"
    return "R$ " + integer_and_cents.translate(str.maketrans(",.", ".,"))
