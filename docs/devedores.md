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

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Condomínio ou devedor inexistente | `404` | `Condomínio não encontrado.` / `Devedor não encontrado.` |
| Devedor parecido no mesmo condomínio, sem `confirm_duplicate` | `409` | alerta acima, com `similar_debtors` |
| Sem telefone e sem e-mail | `422` | `Informe o telefone ou o e-mail do devedor.` |
| Nome ou unidade ausentes, telefone ou e-mail inválidos, campo desconhecido ou edição sem nenhum campo | `422` | erros de validação do FastAPI |
