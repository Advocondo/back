# Usuários

Gestão de usuários: edição dos próprios dados pelo usuário logado ([US05](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us05)), convites ([US07](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us07)), inativação ([US08](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us08)), perfil ([US09](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us09)), vínculo dos Clientes aos condomínios ([US10](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us10)) e histórico das ações ([US11](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us11)). O código fica em `src/advocondo/users/`. A criação do primeiro Administrador (`POST /setup`) está em [Autenticação](auth.md#primeiro-administrador).

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

### Convites (US07)

Os usuários, fora o primeiro Administrador, entram por convite. As rotas de gestão (`POST /users/invites`, `/users/{user_id}/…`) exigem um **Administrador** (US07-CA02); a Equipe Operacional e o Cliente recebem `403`. Só `POST /users/invites/accept` é pública.

#### `POST /users/invites`

```json
{"email": "bruno@example.com", "name": "Bruno Lima", "role": "operator", "is_lawyer": true, "oab_number": "DF123456"}
```

- Cria o usuário com situação `pending`, sem senha (US07-CA01), e envia por e-mail um link para `<FRONTEND_URL>/convite?token=…`, válido por `INVITE_LINK_MINUTES` (padrão 24 horas). O token é guardado só como hash.
- `role`: `operator` ou `client`. Não se convida outro Administrador; para isso, convide e depois mude o perfil (US09).
- `email` repetido, inclusive de convite pendente, recebe `409` (US07-CA03). É gravado em minúsculas.
- `is_lawyer` e `oab_number` (US07-CA04): o advogado precisa da OAB (8 a 12 caracteres), e só o advogado pode tê-la. A marcação independe do perfil e alimenta a lista de responsáveis pelos acordos (US18).
- Grava uma linha `invited` no histórico (US11). Resposta `201` com o usuário.

#### `POST /users/invites/accept`

Sem login. Corpo `{"token": "…", "password": "…"}`. Define a senha (mínimo 8 caracteres) e muda a situação para `active`; a partir daí o usuário faz login normalmente. Token desconhecido, expirado ou de convite já aceito recebe `422`.

### `GET /users/lawyers`

Para a Equipe Operacional e o Administrador escolherem o advogado responsável por um acordo (US18). Lista os usuários **ativos** marcados como advogado, por nome, com `id`, `name` e `oab_number`.

### `PATCH /users/{user_id}/status` (US08)

Corpo `{"status": "inactive"}` ou `{"status": "active"}`. A mudança vale na hora (US08-CA01): o usuário inativo não faz login e as sessões que ele já tinha abertas passam a receber `401` (US08-CA02). Reativar devolve o acesso com a mesma senha (US08-CA03).

- Usuário com convite pendente recebe `422`: ele ainda não tem acesso para inativar.
- O Administrador não pode inativar o próprio acesso (`422`), para o escritório não ficar sem Administrador por engano.
- `pending` no corpo recebe `422`: usuário pendente só nasce do convite.
- Cada mudança grava uma linha `status_changed` no histórico; enviar a situação atual não grava nada.

### `PATCH /users/{user_id}/role` (US09)

Corpo `{"role": "admin" | "operator" | "client"}`. As permissões seguem o perfil novo já na próxima requisição, inclusive nas sessões abertas, porque o perfil é lido do banco a cada chamada (US09-CA01). Só o Administrador muda perfis (US09-CA02) e ele não pode mudar o próprio (`422`). Cada mudança grava uma linha `role_changed` no histórico; tirar o perfil Cliente apaga os vínculos com condomínios (ver abaixo).

### `GET /users/{user_id}/history` (US11)

Só para o Administrador (US11-CA02). Responde `{"logs": [...]}`, da ação mais recente para a mais antiga. Cada linha traz `created_at`, `action` (`invited`, `status_changed`, `role_changed` ou `condominiums_changed`), o autor em `actor` (`{id, name}`), `old_value` e `new_value` (US11-CA01), além de `added_condominiums` e `removed_condominiums`, preenchidas só nas mudanças de vínculo.

### `PATCH /users/{user_id}/monthly-goal`

Corpo `{"monthly_goal": "5000.00"}`, de zero para cima. Só o Administrador chama a rota, e o usuário alvo precisa ser da Equipe Operacional (`422` para os outros perfis). É o valor que o painel da Equipe Operacional mostra como meta ([Painéis financeiros](paineis-financeiros.md)).

Esta meta duplica a meta mensal da [US36](metas.md), gravada em outra tabela e por mês (ver Pendências).

### Condomínios de um Cliente

Um Cliente só deve ver dados dos condomínios vinculados a ele; sem nenhum vínculo, não vê nada (US10-CA02). Os vínculos ficam na tabela `user_condominiums`, e o filtro das consultas de acordos é aplicado pela US37. As duas rotas abaixo exigem um Administrador e respondem `200` com `[{"id": "…", "name": "…"}]`, ordenado por nome.

#### `PUT /users/{user_id}/condominiums`

Substitui a lista inteira de condomínios do Cliente (US10-CA01). Corpo: `{"condominium_ids": ["…", "…"]}`, com até 500 IDs. Uma lista vazia remove todos os vínculos. IDs repetidos contam uma vez. Se algum condomínio da lista não existe, nada é alterado.

Cada `PUT` que muda o conjunto grava uma linha `condominiums_changed` no histórico da [US11](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us11) (`GET /users/{user_id}/history`, só para o Administrador), com o autor, a data e a diferença: `added_condominiums` e `removed_condominiums`, cada item com o `id` e o `name` que o condomínio tinha na data da ação. Nessas linhas `old_value` e `new_value` vêm `null`; nas demais ações, as duas listas vêm vazias. Reenviar o mesmo conjunto, em qualquer ordem, não grava nada.

#### `GET /users/{user_id}/condominiums`

Mostra os condomínios vinculados ao Cliente. Um Cliente sem vínculo recebe `[]`.

Só usuários com perfil Cliente têm vínculos (em qualquer situação: ativo, inativo ou com convite pendente); as duas rotas respondem `422` para os demais perfis. Quando o perfil de um Cliente muda para outro (US09), os vínculos dele são apagados, para que o acesso antigo não volte se ele for feito Cliente de novo. O apagamento entra no histórico como uma linha `condominiums_changed` própria, logo depois da linha `role_changed`, com todos os vínculos em `removed_condominiums`; se o Cliente não tinha vínculos, só a troca de perfil é registrada. Manter o perfil Cliente não mexe nos vínculos.

Para filtrar dados do Cliente, use `UserCondominiumRepository.condominium_ids_of(user_id)` (em `users/repository.py`), que devolve o conjunto de IDs; vazio significa "nenhum condomínio".

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Troca de e-mail ou senha sem `current_password` | `422` | `Informe a senha atual para alterar o e-mail ou a senha.` |
| `current_password` errada | `422` | `A senha atual está incorreta.` |
| Nova senha com menos de 8 caracteres | `422` | `A senha precisa ter pelo menos 8 caracteres.` |
| E-mail já usado por outro usuário (perfil ou convite) | `409` | `Este e-mail já está em uso por outro usuário.` |
| Convite para Administrador | `422` | `Não é possível convidar outro Administrador.` |
| Convite de advogado sem OAB | `422` | `Informe o número da OAB para marcar o usuário como advogado.` |
| Convite com OAB de quem não é advogado | `422` | `O número da OAB só pode ser informado para advogados.` |
| Aceite com token desconhecido, expirado ou já usado | `422` | `O convite é inválido ou já expirou.` |
| Situação de usuário com convite pendente | `422` | `Usuário com convite pendente precisa aceitar o convite antes.` |
| Administrador inativando o próprio acesso | `422` | `Você não pode inativar o seu próprio acesso.` |
| Administrador mudando o próprio perfil | `422` | `Você não pode alterar o seu próprio perfil.` |
| Meta mensal de quem não é da Equipe Operacional | `422` | `A meta financeira só pode ser configurada para usuários Operacionais.` |
| Usuário inexistente (situação, perfil, histórico, meta) | `404` | `Usuário não encontrado.` |
| Rotas de gestão sem ser Administrador | `403` | `Você não tem permissão para esta operação.` |
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
- **O `PUT` de condomínios substitui a lista inteira.** Fica simples para um campo de seleção múltipla no front, é idempotente e a lista vazia cobre "sem acesso" sem outra rota. O custo é que dois Administradores editando o mesmo Cliente ao mesmo tempo não se mesclam: vale a última gravação. Uma trava na linha do usuário serializa essas gravações, para que nenhuma falhe por vínculo duplicado; a troca de perfil (US09) usa a mesma trava.
- **Mudar o perfil de um Cliente apaga os vínculos, numa linha própria do histórico.** A alternativa de manter as linhas faria o acesso antigo reaparecer se o usuário voltasse a ser Cliente. O apagamento vira uma linha `condominiums_changed` separada da `role_changed`, e não um detalhe dela: assim `role_changed` continua guardando só o perfil antigo e o novo, e a pergunta "quando este Cliente perdeu acesso ao condomínio X?" se responde olhando um único tipo de ação, venha a perda de um `PUT` ou de uma troca de perfil.
- **A diferença dos vínculos fica numa coluna JSONB (`details`), com o nome do condomínio na data da ação.** `old_value` e `new_value` têm 255 caracteres, o que cabe uns 6 UUIDs, e o `PUT` aceita até 500. Uma linha por condomínio encheria o histórico numa única ação, e uma tabela filha exigiria outro modelo e carregamento só para ler a lista. Guardar o nome evita que renomear o condomínio depois mude o que o histórico mostra.
- **Condomínio inexistente na lista responde `422`, não `404`.** O recurso da rota é o usuário, que existe; o erro está no corpo enviado.
- **O vínculo não depende da situação do usuário.** Um Cliente inativo ou pendente mantém seus condomínios, que voltam a valer ao reativá-lo (US08).
- **E-mail novo sem confirmação por link.** A história pede só a senha atual; confirmar o endereço novo exigiria uma tabela de pedidos de troca e o envio de e-mail. Um e-mail digitado errado pode ser corrigido pelo próprio usuário enquanto ele estiver logado.

## Pendências

- **Meta mensal em dois lugares**: `users.monthly_goal` (`PATCH /users/{user_id}/monthly-goal`) e a tabela `goals` da [US36](metas.md). O painel da Equipe Operacional lê a primeira; o plano é ficar só com a da US36 (risco R1 do repositório `docs`).
- **Limite de tentativas da senha atual**: como no login (ver as pendências em [Autenticação](auth.md)), a rota não limita tentativas erradas.
