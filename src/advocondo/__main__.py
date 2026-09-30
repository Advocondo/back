"""Entrypoint de produção: `python -m advocondo`.

Sobe o uvicorn sem a configuração de log dele (`log_config=None`), para que
todos os logs, inclusive os do uvicorn, saiam no formato JSON da aplicação.
"""

import uvicorn

from advocondo.main import app


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
