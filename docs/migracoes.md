# Migrations do banco de dados

O schema do PostgreSQL é versionado com o [Alembic](https://alembic.sqlalchemy.org/). Cada mudança na estrutura do banco (tabela, coluna, índice, constraint) vira um arquivo em `migrations/versions/`, versionado no git, e cada ambiente aplica só as migrations que ainda não tem.

## Por que não `create_all`

`Base.metadata.create_all()` só cria tabelas que ainda não existem: nunca altera uma tabela que já tem dados. Depois do primeiro deploy, qualquer coluna nova exigiria SQL manual em cada ambiente. As migrations fazem essa evolução de forma repetível e reversível.

## Comandos

Todos leem a conexão de `DATABASE_URL` (no `.env` em desenvolvimento).

```bash
uv run alembic upgrade head        # aplica as migrations pendentes
uv run alembic current             # mostra a migration aplicada no banco
uv run alembic history             # lista todas as migrations
uv run alembic downgrade -1        # desfaz a última migration
```

## Criando uma migration

1. Altere ou crie o modelo em `src/advocondo/<modulo>/models.py`.
2. Se o módulo for novo, importe os modelos dele em `src/advocondo/models.py`. Sem isso, o Alembic não enxerga as tabelas.
3. Com o banco local atualizado (`alembic upgrade head`), gere a migration:

   ```bash
   uv run alembic revision --autogenerate -m "create users table"
   ```

4. **Revise o arquivo gerado.** O autogenerate não detecta tudo: renomear uma coluna aparece como remover uma e criar outra, o que apagaria os dados. Ajuste à mão quando for o caso e confira o `downgrade()`.
5. Aplique e teste: `uv run alembic upgrade head`, depois `uv run alembic downgrade -1` e `upgrade head` de novo.
6. Faça o commit da migration junto com a mudança do modelo.

Os arquivos são formatados com ruff automaticamente ao serem gerados, e o nome segue o padrão `AAAA_MM_DD_HHMM-<revisão>_<descrição>.py`.

## Duas heads

Cada migration aponta para a anterior pelo `down_revision`. Se duas branches criam migrations a partir da mesma head e as duas chegam à `main`, o Alembic fica com duas heads e o `alembic upgrade head` do deploy falha com `Multiple head revisions are present`. Foi o que aconteceu na #74.

`test_app_unit.py` (`TestMigrationHeads`) falha quando há mais de uma head e mostra quais são. Esse teste não usa banco. Para conferir à mão:

```bash
uv run alembic heads   # precisa listar uma head só
```

Para corrigir, atualize a branch com a `main` (`git merge origin/main`) e mude o `down_revision` da sua migration para a head atual da `main`. Se a `main` ganhar outra migration antes do merge, repita.

## Nomes de constraints

`Base.metadata` usa uma convenção de nomes (`src/advocondo/db.py`), então toda constraint tem um nome previsível: `pk_users`, `uq_users_email`, `fk_sessions_user_id_users`, `ck_users_<nome>`. Isso permite que migrations futuras removam ou alterem uma constraint pelo nome, igual em todos os ambientes.

## Testes

- A suíte de testes cria o schema direto dos modelos (`create_all`), por ser mais rápido.
- `src/advocondo/test_app_integration.py` garante que os dois caminhos chegam ao mesmo lugar: aplica todas as migrations num banco próprio (`advocondo_migrations_test`), compara o resultado com os modelos e confere que o `downgrade` remove tudo. Se alguém mudar um modelo e esquecer a migration, esse teste falha no CI.

## Deploy

Em produção, **o próprio container aplica as migrations ao subir**. O comando da imagem (`Dockerfile.prod`) é:

```bash
alembic upgrade head && exec python -m advocondo
```

- A migration roda com o código novo, antes de a API aceitar requisições.
- Se ela falhar, o container sai com erro e a API não sobe; com o health check, o Coolify mantém o container anterior no ar. O erro aparece no log do deploy.
- Sem migration pendente, o `alembic upgrade head` não faz nada, então reiniciar o container é seguro.

**Deixe vazios os campos *Pre-deployment* e *Post-deployment* do Coolify.** O *Pre-deployment* roda no container **antigo**, que ainda não tem os arquivos das migrations novas (e é pulado no primeiro deploy); o *Post-deployment* roda no novo, mas só depois de o deploy ser dado como concluído, e uma falha ali não falha o deploy ([documentação do Coolify](https://coolify.io/docs/applications/build-packs/dockerfile)).

Durante a troca, por alguns segundos, o container antigo ainda atende com o schema novo. Por isso, escreva migrations compatíveis com a versão anterior da API (ex.: coluna nova com valor padrão ou opcional), o que também permite voltar um deploy com problema sem desfazer o banco. A API roda com uma réplica; com mais de uma, as migrations precisariam de uma trava para não rodarem ao mesmo tempo.

Para conferir em que migration o banco está, rode no terminal do container, no Coolify: `alembic current`.
