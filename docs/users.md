# Usuários

Edição dos próprios dados pelo usuário logado ([US05](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us05)). O código fica em `src/advocondo/users/`. A criação do primeiro Administrador (`POST /setup`) está em [Autenticação](auth.md#primeiro-administrador).

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

O Administrador define a quais condomínios um usuário com perfil Cliente tem acesso ([US10](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us10)). Um Cliente só deve ver dados dos condomínios vinculados a ele; sem nenhum vínculo, não vê nada (US10-CA02). Os vínculos ficam na tabela `user_condominiums`, e o filtro das consultas de acordos é aplicado pela US37.

- `PUT /users/{user_id}/condominiums` substitui a lista inteira. Corpo: `{"condominium_ids": ["…", "…"]}`. Uma lista vazia remove todos os vínculos. IDs repetidos contam uma vez.
- `GET /users/{user_id}/condominiums` mostra os condomínios vinculados.

Ambas exigem um Administrador e respondem `200` com `[{"id": "…", "name": "…"}]`, ordenado por nome. Só usuários com perfil Cliente podem ser vinculados (em qualquer situação: ativo, inativo ou com convite pendente). Se algum condomínio da lista não existe, nada é alterado.

Para filtrar dados do Cliente, use `UserCondominiumRepository.condominium_ids_of(user_id)` (em `users/repository.py`), que devolve o conjunto de IDs; vazio significa "nenhum condomínio".

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Troca de e-mail ou senha sem `current_password` | `422` | `Informe a senha atual para alterar o e-mail ou a senha.` |
| `current_password` errada | `422` | `A senha atual está incorreta.` |
| Nova senha com menos de 8 caracteres | `422` | `A senha precisa ter pelo menos 8 caracteres.` |
| E-mail já usado por outro usuário | `409` | `Este e-mail já está em uso por outro usuário.` |
| Vínculo de condomínios: usuário não é Cliente | `422` | `Só é possível vincular condomínios a usuários com perfil Cliente.` |
| Vínculo de condomínios: condomínio inexistente | `422` | `Condomínio não encontrado: <ids>.` |
| Vínculo de condomínios: usuário inexistente | `404` | `Usuário não encontrado.` |
| Vínculo de condomínios sem ser Administrador | `403` | mensagem de acesso negado |
| Nada para alterar, nome vazio, e-mail inválido, senha com mais de 128 caracteres ou campo fora do perfil (`role`, `status`…) | `422` | erros de validação do FastAPI |

## Decisões

- **Campos fora do perfil são recusados, não ignorados.** Enviar `role` ou `status` responde `422` em vez de ser descartado em silêncio: uma tentativa de se promover a Administrador falha de forma visível, e um teste garante que o perfil continua o mesmo.
- **Senha atual conferida antes de procurar o e-mail novo.** Assim, quem não sabe a senha não descobre, pela resposta `409`, quais e-mails estão cadastrados.
- **Trocar a senha encerra as outras sessões, mas não a atual.** Segue a US03-CA03 (a senha antiga deixa de valer em todo lugar) sem obrigar quem acabou de trocar a fazer login de novo.
- **E-mail novo sem confirmação por link.** A história pede só a senha atual; confirmar o endereço novo exigiria uma tabela de pedidos de troca e o envio de e-mail. Um e-mail digitado errado pode ser corrigido pelo próprio usuário enquanto ele estiver logado.

## Pendências

- **Limite de tentativas da senha atual**: como no login (ver as pendências em [Autenticação](auth.md)), a rota não limita tentativas erradas.
