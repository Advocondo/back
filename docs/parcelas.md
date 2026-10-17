# Parcelas

Plano de parcelas de cada acordo ([US17](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us17)). O código fica em `src/advocondo/parcelas/`; as regras de valores e datas são funções puras em `parcelas/plan.py`.

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`.

## Geração (US17-CA01 e CA02)

As parcelas são geradas junto com o acordo, em `POST /agreements`, a partir de `installment_count` (1 a 120) e `first_due_date` (ver [Acordos](acordos.md)):

- **Valores:** o total é dividido em parcelas iguais, em centavos; os centavos que sobram vão para a **última** parcela. A soma das parcelas é sempre igual ao valor total do acordo. Ex.: R$ 100,00 em 3 vezes = 33,33 + 33,33 + 33,34. Cada parcela precisa ter pelo menos R$ 0,01.
- **Vencimentos:** uma parcela por mês, no mesmo dia do primeiro vencimento. Em meses sem esse dia, a parcela vence no último dia do mês. Ex.: começando em 31/01: 31/01, 28/02, 31/03, 30/04.

- **Honorários (US16):** cada parcela é dividida entre `condominium_amount` (repasse ao condomínio) e `fee_amount` (honorários), proporcionalmente ao valor dela. A divisão é acumulada: cada parcela recebe os honorários arredondados de tudo até ela, menos os das anteriores. Assim nenhum centavo se perde: os honorários das parcelas somam exatamente os honorários do acordo, e em cada parcela `condominium_amount + fee_amount = amount` (US16-CA02), o que o banco também garante com uma `CHECK`. Ex.: 10% sobre R$ 100,00 em 3 vezes = honorários de 3,33 + 3,34 + 3,33.

Cada parcela tem `number` (1, 2, 3…), `due_date`, `amount` e `payment_date`, que fica vazia até a baixa ([US26](https://advocondo.github.io/docs/historias/ep04-parcelas/#us26)). A situação "Em aberto", "Pago" ou "Atrasado" é calculada a partir dessas datas ([US27](https://advocondo.github.io/docs/historias/ep04-parcelas/#us27)), nunca gravada.

## Rotas

### `GET /agreements/{id}/installments`

Devolve as parcelas do acordo, em ordem:

```json
[
  {"id": "…", "agreement_id": "…", "number": 1, "due_date": "2026-01-31", "amount": "33.33", "condominium_amount": "30.00", "fee_amount": "3.33", "payment_date": null}
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
- Se não houver parcela seguinte em aberto, como na última parcela, o valor não muda: para mudar o total, o caminho é editar o acordo ([US19](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us19)).

A resposta é o plano inteiro do acordo, já atualizado, porque a mudança de valor altera outras parcelas.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Acordo ou parcela inexistente | `404` | `Acordo não encontrado.` / `Parcela não encontrada.` |
| Parcela já paga | `422` | `Parcela já paga não pode ser editada.` |
| Novo valor na última parcela em aberto | `422` | `Não há parcela seguinte em aberto para absorver a diferença de valor. Para mudar o total, edite o acordo.` |
| Diferença maior que o valor das parcelas seguintes | `422` | `A diferença deixaria alguma parcela seguinte sem valor.` |
| Parcelas abaixo de R$ 0,01 no cadastro | `422` | `Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas.` |
| Edição sem campos, valor zero, negativo ou com fração de centavo, campo desconhecido | `422` | erros de validação do FastAPI |
