import argon2

MIN_PASSWORD_LENGTH = 8
# Long enough for any passphrase; the cap keeps hashing cost bounded.
MAX_PASSWORD_LENGTH = 128


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = argon2.PasswordHasher()
        # Checked when the e-mail is unknown, so that the response takes as long as
        # for a known one and does not reveal which e-mails are registered.
        self._unknown_user_hash = self._hasher.hash("unknown-user")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except argon2.exceptions.VerificationError:
            return False

    def simulate_verify(self, password: str) -> None:
        self.verify(self._unknown_user_hash, password)


def get_password_hasher() -> PasswordHasher:
    return _password_hasher


_password_hasher = PasswordHasher()
