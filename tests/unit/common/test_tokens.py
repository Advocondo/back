from advocondo.common.tokens import generate_opaque_token, hash_token


def test_generated_tokens_are_unique() -> None:
    assert generate_opaque_token() != generate_opaque_token()


def test_hash_is_stable_and_does_not_contain_the_token() -> None:
    token = generate_opaque_token()

    assert hash_token(token) == hash_token(token)
    assert token not in hash_token(token)
