# Metas

Definição das metas mensais dos membros da Equipe Operacional ([US36](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us36)). O código fica em `src/advocondo/metas/`. O atingimento da meta é calculado a cada consulta, a partir das parcelas pagas.

## Regras

| Campo | Regra |
| --- | --- |
| `target_amount` | Valor da meta em reais de comissão no mês. Maior que zero, com até 2 casas decimais e 12 dígitos. |
| `year`, `month` | Mês da meta. Ano de 2000 a 2100, mês de 1 a 12. |

- Há uma meta por colaborador e mês. Definir de novo o mesmo mês altera o valor.
- Só um usuário da Equipe Operacional pode ter meta.
- Qualquer campo fora da lista é recusado com `422`.

## Atingimento da meta (US36-CA01)

`GET /goals/me` traz também:

| Campo | Significado |
| --- | --- |
| `achieved_amount` | Soma dos honorários (`fee_amount`) das parcelas pagas no mês, dos acordos que o colaborador fechou (quem cadastrou o acordo). Dar baixa, corrigir ou estornar muda o valor na hora, porque nada é gravado. |
| `attainment_percentage` | `achieved_amount ÷ target_amount × 100`, com 2 casas. Passa de 100 quando a meta é superada. |

O mês de uma parcela é o da data de pagamento. A base é o honorário recebido, e não a comissão, porque o percentual da comissão é da [US32](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us32). Acordos cadastrados antes de o sistema guardar quem os fechou não entram na conta de ninguém.

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