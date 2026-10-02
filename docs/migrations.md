# Migrations do banco de dados

O schema é versionado com o [Alembic](https://alembic.sqlalchemy.org/). Os modelos ficam em `src/advocondo/<dominio>/models.py`, são registrados em `src/advocondo/models.py` e as migrations em `migrations/versions/`.

## Fluxo de uma mudança de schema

1. Altere o modelo e registre-o em `src/advocondo/models.py` se for novo.
2. Gere a migration com o banco de dev no ar (`docker compose up -d db`):

   ```bash
   uv run alembic revision --autogenerate -m "descrição curta"
   ```

3. **Revise o arquivo gerado**: o autogenerate não detecta renomeações (vira remover + criar) nem tudo o que importa para dados já existentes.
4. Aplique e teste o caminho de volta:

   ```bash
   uv run alembic upgrade head
   uv run alembic downgrade -1 && uv run alembic upgrade head
   ```

5. Commite o modelo e a migration juntos.

## Garantias nos testes

- A fixture `db_engine` monta o banco de teste rodando `alembic upgrade head`, então toda migration é exercitada em cada execução da suíte.
- `tests/integration/test_migrations.py` falha se os modelos e as migrations divergirem (modelo alterado sem migration).

## Produção (Coolify)

A imagem de produção já inclui `alembic.ini` e `migrations/`, mas **as migrations não rodam sozinhas ao subir a API**. No Coolify, configure o comando de pré-implantação (*Pre-deployment command*) do back-end:

```bash
alembic upgrade head
```

Assim o schema é atualizado antes de a nova versão receber tráfego, e um deploy com migration quebrada falha em vez de subir a API com o banco desatualizado.

## Regras

- Nunca edite uma migration já mergeada; crie outra.
- Migrations devem ser compatíveis com a versão anterior da API quando possível (adicione colunas como opcionais antes de torná-las obrigatórias).
