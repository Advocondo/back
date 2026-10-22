# Devedores

Cadastro dos moradores inadimplentes ([US13](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us13)). O devedor é cadastrado uma vez, dentro de um condomínio, e reaproveitado em todos os acordos com ele. O código fica em `src/advocondo/devedores/`.

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`.

## Campos

| Campo | Regra |
| --- | --- |
| `condominium_id` | Obrigatório no cadastro: o condomínio precisa existir. Não muda depois. |
| `name` | Obrigatório, de 1 a 200 caracteres. |
| `unit` | Unidade, obrigatória, até 50 caracteres, em texto livre (`Bloco B 304`), porque cada condomínio nomeia as unidades do seu jeito. |
| `phone`, `email` | Contato: é preciso ter ao menos um dos dois. Telefone com DDD, 10 ou 11 dígitos, com ou sem máscara. |

## Rotas

### `POST /debtors`

Cadastra um devedor. Resposta `201` com o devedor.

**Alerta de duplicidade (US13-CA01).** Antes de cadastrar, a API procura devedores parecidos **no mesmo condomínio**: mesmo nome (sem diferenciar acentos, maiúsculas e espaços) **ou** mesma unidade (sem diferenciar maiúsculas, espaços e pontuação, então `Bloco B - 304` e `bloco b 304` são iguais). Se encontrar, não cadastra e responde `409`:

```json
{
  "detail": "Já existe devedor com dados parecidos neste condomínio. Confira a lista e confirme se quiser cadastrar mesmo assim.",
  "similar_debtors": [{"id": "…", "condominium_id": "…", "name": "Jose Simao", "unit": "Torre A 101", "phone": "61912345678", "email": null}]
}
```

É um alerta, não um bloqueio: depois de conferir, o front reenvia o mesmo cadastro com `"confirm_duplicate": true`, e o devedor é cadastrado.

### `GET /debtors`

Lista os devedores em ordem de nome. Parâmetros opcionais: `condominium_id`, `search` (parte do nome ou da unidade, sem diferenciar maiúsculas), `limit` (padrão 50, máximo 200) e `offset`.

### `GET /debtors/{id}`

Devolve um devedor.

### `PATCH /debtors/{id}`

Edita nome, unidade, telefone ou e-mail. Só os campos enviados mudam; telefone ou e-mail enviados como `null` são apagados, desde que o devedor continue com algum contato.

## Importação em lote

Os devedores de um condomínio também podem vir da planilha de inadimplentes que o condomínio envia ([US14](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us14)). O código da leitura fica em `src/advocondo/devedores/spreadsheet.py`.

### `GET /debtors/import/template`

Baixa o modelo `modelo-inadimplentes.xlsx`, com as colunas que a importação lê.

### A planilha

- Só arquivos `.xlsx`, de até 1 MB e 1000 devedores. Vale a primeira aba.
- A primeira linha traz os cabeçalhos, em qualquer ordem, sem diferenciar maiúsculas, acentos e pontuação (`E-mail`, `EMAIL`):

| Coluna | Obrigatória | Regra |
| --- | --- | --- |
| `Nome` | Sim | As mesmas regras do cadastro unitário (ver [Campos](#campos)). |
| `Unidade` | Sim | Idem. |
| `Telefone` | Não | Com ou sem máscara. A linha precisa de telefone ou de e-mail. |
| `E-mail` | Não | Idem. |

- Linhas totalmente vazias são ignoradas.

### `POST /debtors/import`

Envio `multipart/form-data` com `condominium_id`, `file` (a planilha) e `confirm`. O fluxo tem dois passos, sem nada guardado no servidor entre eles:

1. **Prévia** (`confirm=false`, o padrão): valida todas as linhas e **não grava nada** (US14-CA01).
2. **Confirmação** (`confirm=true`): o front reenvia o mesmo arquivo, e a API grava, de uma vez, só as linhas válidas. Os devedores ficam disponíveis para novos acordos (US14-CA02).

Cada linha volta com o número dela no Excel e um `status`:

| `status` | Significado | Na confirmação |
| --- | --- | --- |
| `valid` | Pronta para cadastrar. | Entra. |
| `invalid` | Tem erros, listados em `errors`. | Fica de fora. |
| `similar` | Parecida com devedor já cadastrado no condomínio (`similar_debtors`), pela mesma regra do [alerta de duplicidade](#post-debtors), ou com uma linha anterior da planilha (`repeats_row`). | Fica de fora. Se for outra pessoa, cadastre pelo `POST /debtors` com `confirm_duplicate`. |

```json
{
  "confirmed": false,
  "imported": 0,
  "rows": [
    {"number": 2, "status": "valid", "values": {"name": "José Simão", "unit": "Bloco B 304", "phone": "(61) 91234-5678", "email": null}, "errors": [], "similar_debtors": [], "repeats_row": null},
    {"number": 3, "status": "invalid", "values": {"name": "Maria Souza", "unit": "Torre A 101", "phone": null, "email": null}, "errors": ["Informe o telefone ou o e-mail do devedor."], "similar_debtors": [], "repeats_row": null}
  ]
}
```

`imported` é o número de devedores gravados, sempre `0` na prévia.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Condomínio ou devedor inexistente | `404` | `Condomínio não encontrado.` / `Devedor não encontrado.` |
| Devedor parecido no mesmo condomínio, sem `confirm_duplicate` | `409` | alerta acima, com `similar_debtors` |
| Sem telefone e sem e-mail | `422` | `Informe o telefone ou o e-mail do devedor.` |
| Nome ou unidade ausentes, telefone ou e-mail inválidos, campo desconhecido ou edição sem nenhum campo | `422` | erros de validação do FastAPI |
| Planilha que não é `.xlsx`, maior que 1 MB, com mais de 1000 linhas, sem devedores ou sem as colunas `Nome` e `Unidade` | `422` | o motivo, por exemplo `Faltam colunas na planilha: Unidade. Use o modelo de planilha.` |
