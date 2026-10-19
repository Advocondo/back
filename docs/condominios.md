# Condomínios

Cadastro e edição dos condomínios que o escritório representa ([US12](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us12)). O código fica em `src/advocondo/condominios/`. O condomínio é a base de devedores (US13), acordos (US15) e do vínculo com usuários Cliente (US10).

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Administrador** ou **Equipe Operacional**. Usuários Cliente recebem `403`.

## Campos

| Campo | Regra |
| --- | --- |
| `name` | Obrigatório, de 1 a 200 caracteres, sem espaços nas pontas. |
| `cnpj` | Opcional. Aceita com ou sem máscara (`14.447.918/0001-98`) e é gravado só com os 14 dígitos. Os dígitos verificadores são conferidos. Dois condomínios não podem ter o mesmo CNPJ. |
| `zip_code` | CEP, 8 dígitos, com ou sem máscara. |
| `street`, `neighborhood`, `city` | Logradouro, bairro e cidade, até 200 caracteres. |
| `state` | UF com 2 letras; gravada em maiúsculas. |
| `manager_name`, `manager_email`, `manager_phone` | Síndico ou administradora. Telefone com DDD, 10 ou 11 dígitos, com ou sem máscara. |
| `contract_start_date`, `contract_renewal_date` | Datas do contrato de prestação de serviço (`AAAA-MM-DD`). A renovação não pode ser anterior ao início. O acompanhamento da renovação é a US23. |

Qualquer campo fora desta lista é recusado com `422`.

## Rotas

### `POST /condominiums`

Cadastra um condomínio. Só `name` é obrigatório. Resposta `201` com o condomínio e o `id` gerado.

### `GET /condominiums`

Lista os condomínios em ordem de nome. Parâmetros opcionais:

- `search`: parte do nome do condomínio ou do síndico, sem diferenciar maiúsculas. `%` e `_` são buscados como texto.
- `limit` (padrão 50, máximo 200) e `offset` (padrão 0), para paginar.

### `GET /condominiums/{id}`

Devolve um condomínio.

### `PATCH /condominiums/{id}`

Edita um condomínio já cadastrado, por exemplo na troca de administradora (US12-CA02). Só os campos enviados mudam; um campo opcional enviado como `null` é apagado. O nome não pode ser removido. A regra das datas considera o que já está gravado: enviar só a renovação compara com o início salvo.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Usuário Cliente | `403` | `Você não tem permissão para esta operação.` |
| Condomínio inexistente | `404` | `Condomínio não encontrado.` |
| CNPJ já usado por outro condomínio | `409` | `Já existe um condomínio com este CNPJ.` |
| Renovação anterior ao início do contrato | `422` | `A data de renovação não pode ser anterior ao início do contrato.` |
| Nome ausente, CNPJ, CEP, UF, e-mail ou telefone inválidos, campo desconhecido ou edição sem nenhum campo | `422` | erros de validação do FastAPI |
