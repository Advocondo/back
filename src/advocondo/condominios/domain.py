"""Regras puras do domínio de condomínios: sem banco, sem HTTP."""

_CNPJ_WEIGHTS_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_WEIGHTS_2 = (6, *_CNPJ_WEIGHTS_1)


def _cnpj_check_digit(base: str, weights: tuple[int, ...]) -> int:
    remainder = sum(int(d) * w for d, w in zip(base, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(cnpj: str) -> bool:
    """CNPJ só com dígitos (14) e dígitos verificadores corretos."""
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False
    first = _cnpj_check_digit(cnpj[:12], _CNPJ_WEIGHTS_1)
    second = _cnpj_check_digit(cnpj[:13], _CNPJ_WEIGHTS_2)
    return cnpj[12:] == f"{first}{second}"
