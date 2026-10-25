# Acordos

Cadastro e consulta dos acordos extrajudiciais ([US15](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us15)). O código fica em `src/advocondo/acordos/`.

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`; a visão deles é o painel do Cliente (US37), que não pode mostrar honorários.

O PDF do acordo (US24) fica em `/agreements/{id}/pdfs`, onde o Cliente também baixa os PDFs dos acordos dos seus condomínios. Veja [Documentos](documentos.md).

## Campos

| Campo | Regra |
| --- | --- |
| `condominium_id` | Obrigatório. O condomínio precisa estar cadastrado (US12-CA01); o acordo fica vinculado a ele (US15-CA03). |
| `debtor_id` | Obrigatório. O devedor precisa estar cadastrado e ser **do mesmo condomínio**. |
| `total_amount` | Valor total da dívida, obrigatório, maior que zero, com no máximo 2 casas decimais. |
| `fee_percentage` ou `fee_amount` | Honorários do escritório ([US16](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us16)), em **um** dos dois formatos: percentual do total (0 a 100, até 2 casas) ou valor em reais (de 0 até o valor total). Com o percentual, o valor é calculado e arredondado ao centavo (US16-CA01); o percentual só é guardado quando foi informado. |
| `installment_count` | Número de parcelas, obrigatório, de 1 a 120. |
| `first_due_date` | Vencimento da primeira parcela (`AAAA-MM-DD`), obrigatório. As parcelas são geradas com o acordo; ver [Parcelas](parcelas.md). |
| `status` | Definido pelo sistema: todo acordo nasce `active` e passa a `cancelled` no cancelamento ([US20](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us20)). |
| `cancelled_at` e `cancellation_reason` | Preenchidos no cancelamento: o momento e o motivo, que é opcional (até 500 caracteres). Vêm `null` num acordo ativo. |

Valores em dinheiro são gravados como `NUMERIC(12, 2)`, nunca como ponto flutuante, e voltam na resposta como texto com duas casas (`"5500.00"`), para não perder centavos. O front formata como `R$ 5.500,00`.

O advogado responsável (US18) não é informado no cadastro: o acordo nasce sem responsável e um Administrador ou membro da Equipe Operacional o atribui depois. Só vale usuário **ativo, marcado como advogado no convite (US07) e com OAB**. A lista de candidatos vem de `GET /users/lawyers`.

## Rotas

### `POST /agreements`

Cadastra o acordo e gera as parcelas (US17-CA01). O acordo passa a aparecer na lista de ativos (US15-CA01). Resposta `201`:

```json
{
  "id": "…",
  "status": "active",
  "total_amount": "5500.00",
  "fee_amount": "550.00",
  "fee_percentage": "10.00",
  "installment_count": 10,
  "condominium": {"id": "…", "name": "Residencial Mirante"},
  "debtor": {"id": "…", "name": "José Simão", "unit": "Bloco B 304"}
}
```

### `GET /agreements`

Lista os acordos, do mais recente para o mais antigo. Sem filtro de `status`, vêm todos, ativos e cancelados; a lista de ativos é `?status=active`. Filtros opcionais e combináveis (US22-CA02): `status` (`active` ou `cancelled`), `condominium_id`, `debtor_id`, `responsible_lawyer_id` e `search`; paginação com `limit` (padrão 50, máximo 200) e `offset`.

`search` é a busca da US22: traz os acordos em que o nome do devedor, do condomínio ou do advogado responsável contém o texto, sem diferenciar maiúsculas (`?search=sim` e `?search=JOSÉ` encontram "José Simão", US22-CA01). O acento precisa ser digitado: `?search=jose` não encontra "José", como nas buscas de devedores e condomínios. `%` e `_` são procurados como caracteres comuns.

### `GET /agreements/{id}`

Devolve um acordo.

### `PATCH /agreements/{id}`

Equipe Operacional e Administrador corrigem ou renegociam o acordo. Só os campos enviados mudam, e é preciso enviar pelo menos um:

```json
{"total_amount": "4000.00", "confirm_paid_installments": false}
```

- **Campos:** `debtor_id` (do mesmo condomínio), `total_amount`, e `fee_percentage` ou `fee_amount` (nunca os dois).
- **Honorários sem valor novo:** seguem o percentual digitado antes, sobre o novo total. Se o percentual nunca foi digitado, o valor em reais não muda.
- **Recálculo:** se o total ou os honorários mudam, as parcelas **em aberto** são recalculadas em partes iguais com o que falta receber. As parcelas pagas nunca mudam. Número e datas das parcelas continuam sendo editados em `PATCH /installments/{id}`.
- **Confirmação extra (US19-CA01):** com parcela paga, o pedido só vale com `"confirm_paid_installments": true`. Sem isso, a resposta é `409`, e o front mostra a confirmação e reenvia.
- **Registro (US19-CA02):** cada campo alterado gera uma linha em `agreement_edit_logs`, com quem alterou, quando, o valor antigo e o novo, e se o acordo já tinha parcela paga. A consulta desse registro é da US31.
- Se nada muda de verdade, nada é gravado e nenhuma confirmação é pedida.

### `PUT /agreements/{id}/responsible-lawyer`

Atribui o acordo a um advogado ou troca o responsável. Corpo: `{"lawyer_id": "…"}`. Resposta `200` com o acordo, que passa a trazer `responsible_lawyer` (`id`, `name`, `oab_number`). Toda troca vai para o histórico, e escolher o advogado que já é o responsável não muda nada (US18-CA01).

### `GET /agreements/{id}/lawyer-history`

Lista as atribuições do acordo, da mais antiga para a mais recente. Cada item traz `previous_lawyer` (vazio na primeira atribuição), `new_lawyer`, `assigned_by` e `assigned_at` (US18-CA02).

### `POST /agreements/{id}/cancel`

Cancela o acordo ([US20](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us20)). Ele sai da lista de ativos e do painel do Cliente, e nada é apagado: o histórico fica consultável.

```json
{"reason": "Devedor quebrou o acordo", "confirm_open_installments": true}
```

- `reason` é opcional.
- `confirm_open_installments` (padrão `false`) precisa ser `true` quando o acordo ainda tem parcelas **sem pagamento**, em aberto ou em atraso. Sem isso a API não cancela e responde `409` com quantas são e quanto somam, por exemplo: `Há 3 parcelas sem pagamento, somando R$ 1.234,56. Confirme para cancelar o acordo.` Um acordo sem parcelas pendentes cancela sem confirmação.
- A resposta é o acordo, já com `status: "cancelled"`, `cancelled_at` e `cancellation_reason`.

O que muda para as parcelas está em [Parcelas](parcelas.md#acordo-cancelado-us20). Um acordo cancelado também não troca de advogado responsável nem é editado em `PATCH /agreements/{id}`. Reativar um acordo cancelado ainda não existe; quem cancelou e o histórico completo ficam para o log de alterações financeiras (US31).

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Acordo com parcelas sem pagamento, sem `confirm_open_installments` | `409` | `Há N parcelas sem pagamento, somando R$ …. Confirme para cancelar o acordo.` |
| Acordo já cancelado (cancelar de novo) | `422` | `O acordo já está cancelado.` |
| Edição ou troca de advogado de acordo cancelado | `422` | `Acordo cancelado não aceita esta operação.` |
| Condomínio, devedor ou acordo inexistente | `404` | `Condomínio não encontrado.` / `Devedor não encontrado.` / `Acordo não encontrado.` |
| Devedor de outro condomínio | `422` | `O devedor informado não pertence a este condomínio.` |
| Honorários maiores que o valor total | `422` | `Os honorários não podem ser maiores que o valor total do acordo.` |
| Acordo com parcela paga, sem confirmação | `409` | `Este acordo já tem parcelas pagas. Confirme a alteração para continuar.` |
| Novo total menor ou igual ao já pago | `422` | `O novo valor total precisa ser maior que o valor das parcelas já pagas.` |
| Honorários incompatíveis com o que já foi pago | `422` | `Os honorários não são compatíveis com as parcelas já pagas.` |
| Todas as parcelas já pagas | `422` | `Todas as parcelas já foram pagas: não há parcela em aberto para recalcular.` |
| Parcelas abaixo de R$ 0,01 | `422` | `Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas.` |
| Honorários ausentes ou informados nos dois formatos, campo obrigatório ausente (US15-CA02), valor zero, negativo ou com fração de centavo, campo desconhecido ou `status` inválido | `422` | erros de validação do FastAPI |
| Advogado inexistente | `404` | `Advogado não encontrado.` |
| Responsável que não é advogado ativo com OAB | `422` | `O responsável precisa ser um advogado ativo, com OAB cadastrada.` |
