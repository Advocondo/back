"""Exceções de negócio do módulo. O router as converte em respostas HTTP."""


class CondominioNotFoundError(Exception):
    pass


class CnpjAlreadyRegisteredError(Exception):
    pass
