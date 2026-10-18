# Acordos

Cadastro e consulta dos acordos extrajudiciais ([US15](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us15)). O código fica em `src/advocondo/acordos/`.

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`; a visão deles é o painel do Cliente (US37), sem dados financeiros do escritório.

## Campos

| Campo | Regra |
| --- | --- |
| `condominium_id` | Obrigatório. O condomínio precisa estar cadastrado (US12-CA01); o acordo fica vinculado a ele (US15-CA03). |
| `debtor_id` | Obrigatório. O devedor precisa estar cadastrado e ser **do mesmo condomínio**. |
| `total_amount` | Valor total da dívida, obrigatório, maior que zero, com no máximo 2 casas decimais. |
| `installment_count` | Número de parcelas, obrigatório, de 1 a 120. |
| `first_due_date` | Vencimento da primeira parcela (`AAAA-MM-DD`), obrigatório. As parcelas são geradas com o acordo; ver [Parcelas](parcelas.md). |
| `status` | Definido pelo sistema: todo acordo nasce `active`. O cancelamento é a US20. |

Valores em dinheiro são gravados como `NUMERIC(12, 2)`, nunca como ponto flutuante, e voltam na resposta como texto com duas casas (`"5500.00"`), para não perder centavos. O front formata como `R$ 5.500,00`.

O advogado responsável (US18) ainda não faz parte do cadastro: ele depende da marcação de advogado no convite de usuário (US07).

## Rotas

### `POST /agreements`

Cadastra o acordo e gera as parcelas (US17-CA01). O acordo passa a aparecer na lista de ativos (US15-CA01). Resposta `201`:

```json
{
  "id": "…",
  "status": "active",
  "total_amount": "5500.00",
  "installment_count": 10,
  "condominium": {"id": "…", "name": "Residencial Mirante"},
  "debtor": {"id": "…", "name": "José Simão", "unit": "Bloco B 304"}
}
```

### `GET /agreements`

Lista os acordos, do mais recente para o mais antigo. Filtros opcionais e combináveis: `status` (`active`), `condominium_id`, `debtor_id`; paginação com `limit` (padrão 50, máximo 200) e `offset`.

### `GET /agreements/{id}`

Devolve um acordo.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Condomínio, devedor ou acordo inexistente | `404` | `Condomínio não encontrado.` / `Devedor não encontrado.` / `Acordo não encontrado.` |
| Devedor de outro condomínio | `422` | `O devedor informado não pertence a este condomínio.` |
| Parcelas abaixo de R$ 0,01 | `422` | `Cada parcela precisa ter pelo menos R$ 0,01. Diminua o número de parcelas.` |
| Campo obrigatório ausente (US15-CA02), valor zero, negativo ou com fração de centavo, campo desconhecido ou `status` inválido | `422` | erros de validação do FastAPI |
