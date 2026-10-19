# Metas

Definição das metas mensais dos membros da Equipe Operacional ([US36](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us36)). O código fica em `src/advocondo/metas/`. O cálculo do percentual de atingimento depende das comissões da baixa de parcelas (US26) e entra numa próxima etapa.

## Regras

| Campo | Regra |
| --- | --- |
| `target_amount` | Valor da meta em reais de comissão no mês. Maior que zero, com até 2 casas decimais e 12 dígitos. |
| `year`, `month` | Mês da meta. Ano de 2000 a 2100, mês de 1 a 12. |

- Há uma meta por colaborador e mês. Definir de novo o mesmo mês altera o valor.
- Só um usuário da Equipe Operacional pode ter meta.
- Qualquer campo fora da lista é recusado com `422`.

## Rotas

### `PUT /users/{user_id}/goals/{year}/{month}`

Só o **Administrador**. Corpo: `{"target_amount": "5000.00"}`. Define a meta do colaborador no mês, ou altera a que já existe. Resposta `200` com a meta (`id`, `user_id`, `year`, `month`, `target_amount`).

### `GET /goals/me?year=2026&month=3`

Qualquer usuário logado. Devolve a meta do **próprio** usuário no mês. Ninguém vê a meta de outro colaborador (US36-CA02).

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Quem define a meta não é Administrador | `403` | `Você não tem permissão para esta operação.` |
| Colaborador inexistente | `404` | `Colaborador não encontrado.` |
| Sem meta no mês consultado | `404` | `Meta não encontrada.` |
| O usuário não é da Equipe Operacional | `422` | `Só membros da Equipe Operacional podem ter meta.` |
| Valor, ano, mês ou campo inválido | `422` | erros de validação do FastAPI |