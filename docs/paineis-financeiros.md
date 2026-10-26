# Painéis financeiros

Comissões, faturamento, indicadores e exportação da equipe ([US32](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us32) a [US35](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us35)). O código fica em `src/advocondo/painel_operacional/` (Equipe Operacional) e `src/advocondo/painel_admin/` (Administrador). Nada é gravado: tudo é calculado a cada consulta, a partir das parcelas.

## Regras comuns

- **Comissão** é a soma dos honorários (`fee_amount`) das parcelas **quitadas** no período, dos acordos em que o membro é o advogado responsável ([US18](acordos.md)). Pagamento parcial ([US28](parcelas.md#pagamento-parcial-us28)) só conta quando quita a parcela. Por enquanto a comissão é 100% dos honorários: a regra de cada membro ainda não foi definida.
- **O mês de uma parcela paga é o da data de pagamento.** O mês "atual" é o do Brasil.
- Valores em dinheiro voltam como texto com duas casas (`"30.00"`).

## Equipe Operacional

### `GET /operator-panel/financial` (US32)

Só para a Equipe Operacional; Administrador e Cliente recebem `403`. Traz só os dados de quem consulta (US32-CA01):

```json
{"goal": "100.00", "accumulated_commission": "20.00", "remaining_to_goal": "80.00", "period": {"month": 3, "year": 2026}}
```

| Campo | Regra |
| --- | --- |
| `goal` | Meta mensal gravada em `users.monthly_goal` (ver Pendências). |
| `accumulated_commission` | Comissão do mês atual. |
| `remaining_to_goal` | Quanto falta para a meta; nunca negativo. |

Não há faturamento do escritório nem dado de outros membros (US32-CA02); um teste confere o conjunto exato de campos.

## Administrador

As três rotas são só do Administrador: Equipe Operacional e Cliente recebem `403` (US33-CA02).

### `GET /admin-panel/financial` (US33)

```json
{
  "office_total_revenue": "30.00",
  "team_commissions": [
    {"user_id": "…", "user_name": "Ana", "commission": "10.00"},
    {"user_id": "…", "user_name": "Carla", "commission": "0.00"}
  ],
  "period": {"month": 3, "year": 2026}
}
```

- `office_total_revenue`: honorários recebidos no mês atual, inclusive de acordos sem responsável.
- `team_commissions`: um item por membro da Equipe Operacional, por nome, inclusive quem tem comissão zero no mês.

### `GET /admin-panel/dashboard?year=&month=` (US34)

Indicadores de um mês (US34-CA02). `year` e `month` são obrigatórios; mês fora de 1 a 12 recebe `422`.

| Campo | Regra |
| --- | --- |
| `active_agreements` | Acordos ativos hoje (cancelados ficam de fora). Não depende do mês. |
| `installments_due` | Parcelas que vencem no mês. |
| `overdue_installments` | Dessas, as que estavam atrasadas no último dia do mês: sem pagamento ou pagas depois dele. |
| `monthly_default_rate` | `overdue_installments ÷ installments_due × 100`, com 2 casas; `0` sem parcelas no mês. |
| `paid_commissions` | Honorários recebidos no mês. |

### `GET /admin-panel/reports/export?year=&month=` (US35)

Planilha `.xlsx` (`acompanhamento_AAAA_MM.xlsx`) com as parcelas que vencem no mês, uma por linha: condomínio, devedor, unidade, acordo, número, vencimento, pagamento, status, valor, honorários e responsável.

- **Filtros (US35-CA01):** `condominium_id`, `responsible_lawyer_id` e `status` (`open`, `overdue` ou `paid`), combináveis. O status é calculado na data de hoje.
- **Formato (US35-CA02):** valores são números com formato `#,##0.00` e datas são datas com `dd/mm/yyyy`, então o Excel soma e ordena. Nomes e identificadores ficam sempre como texto: um nome que começa com `=` não vira fórmula.
- Mês sem parcelas gera a planilha só com o cabeçalho.

## Erros

| Código | Quando |
| --- | --- |
| `401` | Sem login ou sessão inválida. |
| `403` | Perfil sem acesso à rota. |
| `422` | `year` ou `month` ausente ou inválido. |

## Pendências

Encontradas ao escrever os testes; o comportamento atual está descrito acima e ainda não foi mudado.

- **Meta em dois lugares.** O painel lê `users.monthly_goal` (`PATCH /users/{id}/monthly-goal`), mas a meta da [US36](metas.md) fica na tabela `goals`, por mês. Uma meta definida pela US36 não aparece aqui (risco R1 do repositório `docs`).
- **Atraso do mês atual.** O dashboard mede o atraso no último dia do mês. Para o mês atual, isso conta como atrasada uma parcela que ainda não venceu (vence no dia 20, consulta no dia 10).
- **Administrador responsável por acordo.** `team_commissions` lista só a Equipe Operacional. A comissão de um Administrador que é o advogado responsável entra em `office_total_revenue`, mas não aparece para ninguém.
- **Quem recebe o mérito.** A comissão daqui conta os acordos do advogado **responsável**; o atingimento da meta da [US36](metas.md) conta os acordos que o membro **cadastrou**. Os dois números podem não bater para a mesma pessoa.
