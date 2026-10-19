"""CNPJ check digits, as defined by the Receita Federal."""

FIRST_DIGIT_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
SECOND_DIGIT_WEIGHTS = (6, *FIRST_DIGIT_WEIGHTS)


def is_valid_cnpj(cnpj: str) -> bool:
    """True for 14 digits whose two last ones are the right check digits."""
    if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
        return False
    first_check_digit = _check_digit(cnpj[:12], FIRST_DIGIT_WEIGHTS)
    second_check_digit = _check_digit(cnpj[:13], SECOND_DIGIT_WEIGHTS)
    return cnpj[12:] == f"{first_check_digit}{second_check_digit}"


def _check_digit(digits: str, weights: tuple[int, ...]) -> int:
    remainder = (
        sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True))
        % 11
    )
    return 0 if remainder < 2 else 11 - remainder
