# Usuários

Edição dos próprios dados pelo usuário logado ([US05](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us05)) e vínculo dos Clientes aos condomínios, feito pelo Administrador ([US10](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us10)). O código fica em `src/advocondo/users/`. A criação do primeiro Administrador (`POST /setup`) está em [Autenticação](auth.md#primeiro-administrador).

## Rotas

### `PATCH /users/me`

O usuário logado altera o próprio nome, e-mail ou senha, sem depender de um Administrador (US05-CA01). Exige o cabeçalho `Authorization: Bearer <token>`. Só os campos enviados mudam:

```json
{
  "name": "Ana Lima",
  "email": "ana.lima@example.com",
  "new_password": "…",
  "current_password": "…"
}
```

- `name`: sem espaços nas pontas, de 1 a 200 caracteres.
- `email`: gravado em minúsculas. Enviar o mesmo e-mail de hoje, com outras maiúsculas, não conta como troca.
- `new_password`: de 8 a 128 caracteres.
- `current_password`: obrigatória para trocar o e-mail ou a senha (US05-CA02). Para trocar só o nome, não é preciso enviá-la.

Qualquer outro campo, como `role` ou `status`, é recusado com `422`, e nada é alterado. O perfil e a situação do usuário só mudam pelas mãos de um Administrador (US08, US09); a rota não serve para ninguém se tornar Administrador.

Resposta `200`, com `id`, `name`, `email` e `role` do usuário já atualizados.

Ao trocar a senha, as sessões em outros dispositivos são encerradas e precisam de login com a senha nova; o dispositivo que fez a troca continua logado. Trocar o nome ou o e-mail não encerra sessões.

### Condomínios de um Cliente

Um Cliente só deve ver dados dos condomínios vinculados a ele; sem nenhum vínculo, não vê nada (US10-CA02). Os vínculos ficam na tabela `user_condominiums`, e o filtro das consultas de acordos é aplicado pela US37. As duas rotas abaixo exigem um Administrador e respondem `200` com `[{"id": "…", "name": "…"}]`, ordenado por nome.

#### `PUT /users/{user_id}/condominiums`

Substitui a lista inteira de condomínios do Cliente (US10-CA01). Corpo: `{"condominium_ids": ["…", "…"]}`, com até 500 IDs. Uma lista vazia remove todos os vínculos. IDs repetidos contam uma vez. Se algum condomínio da lista não existe, nada é alterado.

#### `GET /users/{user_id}/condominiums`

Mostra os condomínios vinculados ao Cliente. Um Cliente sem vínculo recebe `[]`.

Só usuários com perfil Cliente têm vínculos (em qualquer situação: ativo, inativo ou com convite pendente); as duas rotas respondem `422` para os demais perfis. Quando o perfil de um Cliente muda para outro (US09), os vínculos dele são apagados, para que o acesso antigo não volte se ele for feito Cliente de novo. Manter o perfil Cliente não mexe nos vínculos.

Para filtrar dados do Cliente, use `UserCondominiumRepository.condominium_ids_of(user_id)` (em `users/repository.py`), que devolve o conjunto de IDs; vazio significa "nenhum condomínio".

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Troca de e-mail ou senha sem `current_password` | `422` | `Informe a senha atual para alterar o e-mail ou a senha.` |
| `current_password` errada | `422` | `A senha atual está incorreta.` |
| Nova senha com menos de 8 caracteres | `422` | `A senha precisa ter pelo menos 8 caracteres.` |
| E-mail já usado por outro usuário | `409` | `Este e-mail já está em uso por outro usuário.` |
| Vínculo de condomínios: lista com mais de 500 IDs, ID que não é UUID, `condominium_ids` ausente ou campo extra | `422` | erros de validação do FastAPI |
| Vínculo de condomínios (`PUT` ou `GET`): usuário não é Cliente | `422` | `Somente usuários com perfil Cliente têm condomínios vinculados.` |
| Vínculo de condomínios: condomínio inexistente | `422` | `Condomínios inexistentes na lista: <ids>.` |
| Vínculo de condomínios: usuário inexistente | `404` | `Usuário não encontrado.` |
| Vínculo de condomínios sem ser Administrador | `403` | mensagem de acesso negado |
| Nada para alterar, nome vazio, e-mail inválido, senha com mais de 128 caracteres ou campo fora do perfil (`role`, `status`…) | `422` | erros de validação do FastAPI |

## Decisões

- **Campos fora do perfil são recusados, não ignorados.** Enviar `role` ou `status` responde `422` em vez de ser descartado em silêncio: uma tentativa de se promover a Administrador falha de forma visível, e um teste garante que o perfil continua o mesmo.
- **Senha atual conferida antes de procurar o e-mail novo.** Assim, quem não sabe a senha não descobre, pela resposta `409`, quais e-mails estão cadastrados.
- **Trocar a senha encerra as outras sessões, mas não a atual.** Segue a US03-CA03 (a senha antiga deixa de valer em todo lugar) sem obrigar quem acabou de trocar a fazer login de novo.
- **O `PUT` de condomínios substitui a lista inteira.** Fica simples para um campo de seleção múltipla no front, é idempotente e a lista vazia cobre "sem acesso" sem outra rota. O custo é que dois Administradores editando o mesmo Cliente ao mesmo tempo não se mesclam: vale a última gravação. Uma trava na linha do usuário serializa essas gravações, para que nenhuma falhe por vínculo duplicado.
- **Mudar o perfil de um Cliente apaga os vínculos, sem entrar no histórico.** A alternativa de manter as linhas faria o acesso antigo reaparecer se o usuário voltasse a ser Cliente. O apagamento não vira linha da US11: o registro da troca de perfil já existe e os vínculos podem ser refeitos pelo Administrador.
- **Condomínio inexistente na lista responde `422`, não `404`.** O recurso da rota é o usuário, que existe; o erro está no corpo enviado.
- **O vínculo não depende da situação do usuário.** Um Cliente inativo ou pendente mantém seus condomínios, que voltam a valer ao reativá-lo (US08).
- **E-mail novo sem confirmação por link.** A história pede só a senha atual; confirmar o endereço novo exigiria uma tabela de pedidos de troca e o envio de e-mail. Um e-mail digitado errado pode ser corrigido pelo próprio usuário enquanto ele estiver logado.

## Pendências

- **Limite de tentativas da senha atual**: como no login (ver as pendências em [Autenticação](auth.md)), a rota não limita tentativas erradas.
