# Parcelas

Plano de parcelas de cada acordo ([US17](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us17)). O código fica em `src/advocondo/parcelas/`; as regras de valores e datas são funções puras em `parcelas/plan.py`.

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`.

## Geração (US17-CA01 e CA02)

As parcelas são geradas junto com o acordo, em `POST /agreements`, a partir de `installment_count` (1 a 120) e `first_due_date` (ver [Acordos](acordos.md)):

- **Valores:** o total é dividido em parcelas iguais, em centavos; os centavos que sobram vão para a **última** parcela. A soma das parcelas é sempre igual ao valor total do acordo. Ex.: R$ 100,00 em 3 vezes = 33,33 + 33,33 + 33,34. Cada parcela precisa ter pelo menos R$ 0,01.
- **Vencimentos:** uma parcela por mês, no mesmo dia do primeiro vencimento. Em meses sem esse dia, a parcela vence no último dia do mês. Ex.: começando em 31/01: 31/01, 28/02, 31/03, 30/04.

- **Honorários (US16):** cada parcela é dividida entre `condominium_amount` (repasse ao condomínio) e `fee_amount` (honorários), proporcionalmente ao valor dela. A divisão é acumulada: cada parcela recebe os honorários arredondados de tudo até ela, menos os das anteriores. Assim nenhum centavo se perde: os honorários das parcelas somam exatamente os honorários do acordo, e em cada parcela `condominium_amount + fee_amount = amount` (US16-CA02), o que o banco também garante com uma `CHECK`. Ex.: 10% sobre R$ 100,00 em 3 vezes = honorários de 3,33 + 3,34 + 3,33.

Cada parcela tem `number` (1, 2, 3…), `due_date`, `amount` e `payment_date`, que fica vazia até a baixa ([US26](https://advocondo.github.io/docs/historias/ep04-parcelas/#us26)). A situação "Em aberto", "Pago" ou "Atrasado" é calculada a partir dessas datas ([US27](https://advocondo.github.io/docs/historias/ep04-parcelas/#us27)), nunca gravada.

## Situação da parcela (US27)

Cada parcela traz `status`, calculado a cada consulta a partir de `due_date`, `payment_date` e da data de hoje no Brasil. Nada é gravado, então o status nunca fica desatualizado.

| `status` | Quando |
| --- | --- |
| `paid` | A parcela tem `payment_date`, mesmo que o pagamento tenha sido depois do vencimento. |
| `open` | Sem `payment_date` e com vencimento hoje ou no futuro. |
| `overdue` | Sem `payment_date` e com vencimento anterior a hoje: atrasa no dia seguinte ao vencimento. |

## Faturas do mês (US25)

A equipe vê as parcelas que vencem no mês, de todos os acordos, para saber o que conferir e dar baixa ([US25](https://advocondo.github.io/docs/historias/ep04-parcelas/#us25)):

- **Mês:** por padrão, o mês atual no Brasil. `year` e `month` escolhem outro mês.
- **O que aparece:** cada parcela traz, além dos campos acima, o devedor (`debtor`, com nome e unidade) e o condomínio (`condominium`) do acordo (US25-CA01).
- **Filtros (US25-CA02):** `condominium_id`, `responsible_lawyer_id` (o advogado responsável pelo acordo, [US18](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us18)) e `status` (`open`, `paid` ou `overdue`). O filtro de status usa a mesma regra da [situação da parcela](#situacao-da-parcela-us27), aplicada no banco.
- **Ordem:** pelo vencimento, do mais antigo para o mais novo.
- Parcelas atrasadas de meses anteriores não aparecem no mês atual, porque a lista é das parcelas com vencimento no mês. Para vê-las, consulte o mês delas.

## Baixa da parcela (US26)

A baixa registra que a parcela foi paga, com a data do pagamento ([US26](https://advocondo.github.io/docs/historias/ep04-parcelas/#us26)):

- **Dar baixa (US26-CA01):** Equipe Operacional e Administrador informam a data do pagamento, e a parcela passa a `paid`. O pagamento pode ser antes do vencimento, mas a data não pode ser futura.
- **Corrigir ou estornar (US26-CA02):** só o **Administrador**. Corrigir troca a data da baixa, que é a do pagamento que quitou a parcela; estornar apaga todos os pagamentos da parcela, inclusive os parciais, e ela volta a `open`, ou a `overdue` se já venceu.
- Uma parcela paga não pode receber outra baixa: para mudar a data, o caminho é corrigir.
- **Comissão:** a baixa não grava comissão. Ela será calculada sobre os honorários (`fee_amount`) das parcelas pagas, na [US32](https://advocondo.github.io/docs/historias/ep05-comissoes-metas/#us32), então já considera cada baixa, correção ou estorno.

## Acordo cancelado (US20)

Quando o acordo é cancelado ([Acordos](acordos.md)), nenhuma parcela é apagada, mas as que ainda **não foram pagas** saem da cobrança:

- somem de `GET /installments`, a listagem do mês (US25). O acordo inteiro, pagas incluídas, também sai do painel do Cliente ([Painel do Cliente](painel-cliente.md));
- não aceitam baixa nem edição (`422`, `Acordo cancelado não aceita esta operação.`);
- continuam no plano do acordo, em `GET /agreements/{id}/installments`, junto com as pagas, e as pagas continuam na listagem do mês (US20-CA02). O plano mantém o `status` calculado de cada parcela (`open` ou `overdue`, no caso das sem pagamento): quem o exibe deve olhar o `status` do acordo para não mostrar como dívida cobrada o que está fora da cobrança.

A correção da data e o estorno de uma baixa seguem permitidos ao Administrador mesmo depois do cancelamento: como não há como reativar o acordo, é o único jeito de consertar um pagamento lançado por engano. Uma parcela estornada nesse caso volta a ser uma parcela sem pagamento de acordo cancelado.

## Pagamento parcial (US28)

Um pagamento pode cobrir só parte da parcela ([US28](https://advocondo.github.io/docs/historias/ep04-parcelas/#us28)):

- **Saldo em aberto (US28-CA01):** com um `amount` menor que o saldo, o pagamento é registrado e a parcela continua sem `payment_date`, com o status calculado como antes (`open` ou `overdue`). `remaining_amount` mostra quanto falta. Quando os pagamentos somam o valor da parcela, ela passa a `paid`, com `payment_date` igual à data do pagamento que quitou o saldo.
- **Histórico (US28-CA02):** cada pagamento fica guardado, com valor e data, na ordem em que foi registrado.
- Sem `amount`, o pagamento quita o saldo restante, que é a baixa da [US26](https://advocondo.github.io/docs/historias/ep04-parcelas/#us26). O valor não pode passar do saldo.
- O banco garante as regras: a soma paga (`paid_amount`) fica entre zero e o valor da parcela, e a parcela tem `payment_date` só quando a soma paga é igual ao valor.
- **Plano de parcelas:** uma parcela com pagamento parcial não pode ser editada nem absorver a diferença de outra parcela editada (US17-CA03), porque o valor dela poderia ficar abaixo do que já foi pago.

## Nota fiscal (US29)

A nota fiscal emitida para uma parcela paga fica registrada nela ([US29](https://advocondo.github.io/docs/historias/ep04-parcelas/#us29)):

- **Registro (US29-CA01):** número e data de emissão, só em parcela **paga** (quitada; pagamento parcial não basta). Registrar de novo troca a nota, para corrigir um número ou uma data digitados errado.
- **Número:** de 1 a 15 dígitos, guardado como texto para manter os zeros à esquerda. O número da NFS-e, a nota de serviço que o escritório emite, tem 15 dígitos (ano com 4 dígitos e sequencial com 11).
- A data de emissão não pode ser futura.
- **Pendências (US29-CA02):** a lista de parcelas pagas que ainda não têm nota, da baixa mais antiga para a mais recente.
- O estorno do pagamento não apaga a nota: ela já foi emitida. Uma parcela estornada sai da lista de pendências, porque não está mais paga.

## Rotas

### `GET /installments`

Lista as faturas do mês. Parâmetros, todos opcionais:

| Parâmetro | Padrão | Descrição |
| --- | --- | --- |
| `year` | ano atual | Ano do vencimento |
| `month` | mês atual | Mês do vencimento, de 1 a 12 |
| `condominium_id` | — | Só as parcelas de acordos deste condomínio |
| `responsible_lawyer_id` | — | Só as parcelas de acordos deste advogado responsável |
| `status` | — | `open`, `paid` ou `overdue` |
| `limit` | 50 | Quantas parcelas devolver, até 200 |
| `offset` | 0 | Quantas parcelas pular, para paginar |

```json
[
  {"id": "…", "agreement_id": "…", "number": 2, "due_date": "2026-03-10", "amount": "100.00", "condominium_amount": "90.00", "fee_amount": "10.00", "payment_date": null, "remaining_amount": "100.00", "invoice_number": null, "invoice_date": null, "status": "open", "condominium": {"id": "…", "name": "Residencial Mirante"}, "debtor": {"id": "…", "name": "José Simão", "unit": "Bloco B 304"}}
]
```

### `GET /installments/paid-without-invoice`

Lista as parcelas pagas que ainda não têm nota fiscal, no mesmo formato de `GET /installments`, com `limit` (50 por padrão, até 200) e `offset`.

### `PUT /installments/{id}/invoice`

Registra a nota fiscal da parcela paga, ou troca a que já existe:

```json
{"number": "202600000000042", "issue_date": "2026-01-12"}
```

A resposta é a parcela, com `invoice_number` e `invoice_date`.

### `GET /agreements/{id}/installments`

Devolve as parcelas do acordo, em ordem:

```json
[
  {"id": "…", "agreement_id": "…", "number": 1, "due_date": "2026-01-31", "amount": "33.33", "condominium_amount": "30.00", "fee_amount": "3.33", "payment_date": null, "remaining_amount": "33.33", "invoice_number": null, "invoice_date": null, "status": "open"}
]
```

### `PATCH /installments/{id}`

Edita o vencimento ou o valor de uma parcela **antes da baixa** (US17-CA03). Só os campos enviados mudam:

```json
{"due_date": "2026-02-05", "amount": "130.00"}
```

- **Vencimento:** troca só a data da parcela.
- **Valor:** a diferença é dividida igualmente entre as **parcelas seguintes ainda em aberto** (os centavos que sobram vão para a última), para o plano continuar somando o valor total do acordo. Ex.: 4 × R$ 100,00 e a 2ª passa para R$ 130,00: a 3ª e a 4ª ficam com R$ 85,00 cada.
- Os honorários que ainda faltam receber são divididos de novo entre as parcelas em aberto, com a mesma regra; as parcelas pagas não mudam.
- Se não houver parcela seguinte sem pagamento, como na última parcela, o valor não muda: para mudar o total, o caminho é editar o acordo ([US19](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us19)).

A resposta é o plano inteiro do acordo, já atualizado, porque a mudança de valor altera outras parcelas.

### `POST /installments/{id}/payment`

Registra um pagamento da parcela em aberto. `amount` é opcional: sem ele, o pagamento quita o saldo (baixa); com um valor menor que o saldo, é um pagamento parcial.

```json
{"payment_date": "2026-02-12", "amount": "40.00"}
```

A resposta é a parcela, com `remaining_amount` atualizado e, se o saldo zerou, com `payment_date` e `status: "paid"`.

### `PUT /installments/{id}/payment`

Corrige a data da baixa de uma parcela paga. Só o Administrador. O corpo tem só `payment_date`.

### `DELETE /installments/{id}/payment`

Estorna todos os pagamentos da parcela, parciais ou não. Só o Administrador. A resposta é a parcela, com `payment_date: null`, `remaining_amount` igual ao valor e o `status` recalculado.

### `GET /installments/{id}/payments`

Histórico dos pagamentos da parcela, na ordem em que foram registrados:

```json
[
  {"id": "…", "amount": "40.00", "payment_date": "2026-02-20", "created_at": "2026-02-20T14:03:11.402Z"},
  {"id": "…", "amount": "60.00", "payment_date": "2026-03-01", "created_at": "2026-03-01T10:15:42.118Z"}
]
```

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente; Equipe Operacional corrigindo ou estornando uma baixa | `403` | `Você não tem permissão para esta operação.` |
| Acordo ou parcela inexistente | `404` | `Acordo não encontrado.` / `Parcela não encontrada.` |
| Baixa ou edição de parcela de acordo cancelado | `422` | `Acordo cancelado não aceita esta operação.` |
| Parcela já paga | `422` | `Parcela já paga não pode ser editada.` |
| Novo valor na última parcela, ou sem parcela seguinte sem pagamento | `422` | `Não há parcela seguinte sem pagamento para absorver a diferença de valor. Para mudar o total, edite o acordo.` |
| Diferença maior que o valor das parcelas seguintes | `422` | `A diferença deixaria alguma parcela seguinte sem valor.` |
| Parcelas abaixo de R$ 0,01 no cadastro | `422` | `Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas.` |
| Edição sem campos, valor zero, negativo ou com fração de centavo, campo desconhecido | `422` | erros de validação do FastAPI |
| Listagem com `month` fora de 1 a 12, `status` desconhecido ou `limit` acima de 200 | `422` | erros de validação do FastAPI |
| Baixa em parcela já paga | `422` | `Parcela já paga. Para mudar a data do pagamento, corrija a baixa.` |
| Pagamento maior que o saldo em aberto | `422` | `O valor pago é maior que o saldo em aberto da parcela.` |
| Edição de parcela com pagamento parcial | `422` | `Parcela com pagamento parcial não pode ser editada.` |
| Nota fiscal de parcela que não está quitada | `422` | `A parcela ainda não foi paga.` |
| Data de emissão da nota fiscal futura | `422` | `A data de emissão da nota fiscal não pode ser futura.` |
| Nota fiscal sem data, com número vazio, com algo além de dígitos, com mais de 15 dígitos ou com campo desconhecido | `422` | erros de validação do FastAPI |
| Correção de parcela ainda não quitada; estorno de parcela sem nenhum pagamento | `422` | `A parcela ainda não foi paga.` |
| Data do pagamento futura | `422` | `A data do pagamento não pode ser futura.` |
| Pagamento sem data, com data fora do formato `AAAA-MM-DD`, `amount` zero, negativo ou com fração de centavo, ou campo desconhecido | `422` | erros de validação do FastAPI |
