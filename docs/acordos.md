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
| `status` | Definido pelo sistema: todo acordo nasce `active`. O cancelamento é a US20. |

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

Lista os acordos, do mais recente para o mais antigo. Filtros opcionais e combináveis: `status` (`active`), `condominium_id`, `debtor_id`, `responsible_lawyer_id`; paginação com `limit` (padrão 50, máximo 200) e `offset`.

### `GET /agreements/{id}`

Devolve um acordo.

### `PUT /agreements/{id}/responsible-lawyer`

Atribui o acordo a um advogado ou troca o responsável. Corpo: `{"lawyer_id": "…"}`. Resposta `200` com o acordo, que passa a trazer `responsible_lawyer` (`id`, `name`, `oab_number`). Toda troca vai para o histórico, e escolher o advogado que já é o responsável não muda nada (US18-CA01).

### `GET /agreements/{id}/lawyer-history`

Lista as atribuições do acordo, da mais antiga para a mais recente. Cada item traz `previous_lawyer` (vazio na primeira atribuição), `new_lawyer`, `assigned_by` e `assigned_at` (US18-CA02).

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Condomínio, devedor ou acordo inexistente | `404` | `Condomínio não encontrado.` / `Devedor não encontrado.` / `Acordo não encontrado.` |
| Devedor de outro condomínio | `422` | `O devedor informado não pertence a este condomínio.` |
| Honorários maiores que o valor total | `422` | `Os honorários não podem ser maiores que o valor total do acordo.` |
| Parcelas abaixo de R$ 0,01 | `422` | `Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas.` |
| Honorários ausentes ou informados nos dois formatos, campo obrigatório ausente (US15-CA02), valor zero, negativo ou com fração de centavo, campo desconhecido ou `status` inválido | `422` | erros de validação do FastAPI |
| Advogado inexistente | `404` | `Advogado não encontrado.` |
| Responsável que não é advogado ativo com OAB | `422` | `O responsável precisa ser um advogado ativo, com OAB cadastrada.` |
