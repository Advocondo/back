# Autenticação

Login com e-mail e senha ([US02](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us02)) e redefinição de senha por e-mail ([US03](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us03)). O código fica em `src/advocondo/auth/`.

## Como funciona

1. O front envia e-mail e senha para `POST /auth/login`.
2. A API devolve um token de acesso e os dados do usuário, incluindo o `role`. O front usa o `role` para abrir o painel do perfil (US02-CA01).
3. Nas próximas requisições, o front envia o token no cabeçalho `Authorization: Bearer <token>`.

Cada login cria uma linha em `user_sessions`. A tabela guarda só o hash SHA-256 do token, então um vazamento do banco não entrega tokens válidos. Apagar a linha encerra a sessão: é o que a US03 (redefinir a senha) e a US06 (encerrar sessões em outros dispositivos) vão usar.

As senhas são guardadas com Argon2 (`PasswordHasher`, em `common/passwords.py`).

## Rotas

### `POST /auth/login`

Corpo:

```json
{ "email": "ana@example.com", "password": "...", "remember_me": false }
```

- O e-mail é comparado sem diferenciar maiúsculas e ignorando espaços nas pontas.
- `remember_me` corresponde ao "Manter conectado" da tela de login e aumenta a duração da sessão.

Resposta `200`:

```json
{
  "access_token": "…",
  "token_type": "bearer",
  "expires_at": "2026-03-02T21:00:00Z",
  "user": { "id": "…", "name": "Ana Souza", "email": "ana@example.com", "role": "operator" }
}
```

`role` é `admin`, `operator` ou `client`.

### `GET /auth/me`

Devolve o usuário do token (mesmo formato de `user` acima). Serve para o front recuperar o perfil ao recarregar a página.

### `POST /auth/password-reset`

Pede um link de redefinição de senha (US03-CA01). Corpo: `{ "email": "ana@example.com" }`.

Resposta `202`, sempre a mesma, com ou sem e-mail cadastrado:

```json
{ "detail": "Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha." }
```

Se o e-mail for de um usuário ativo, ele recebe o link `{FRONTEND_URL}/redefinir-senha?token=…`, válido por 60 minutos. Usuários inativos, convites pendentes e e-mails desconhecidos não recebem nada. Um pedido novo invalida o link anterior.

Cada usuário pode fazer até 5 pedidos por hora. A partir do sexto, a resposta é a mesma, mas nenhum e-mail é enviado, e o caso fica registrado no log como aviso.

### `POST /auth/password-reset/confirm`

Define a nova senha. Corpo:

```json
{ "token": "…", "new_password": "…" }
```

O `token` é o parâmetro `token` do link. A página `/redefinir-senha` do front lê esse parâmetro e envia junto com a nova senha.

Resposta `204`. A partir daí:

- o link deixa de valer (uso único, US03-CA02);
- todas as sessões abertas do usuário são encerradas, em todos os dispositivos, e a senha antiga para de funcionar (US03-CA03).

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| E-mail não cadastrado, senha errada, usuário inativo ou com convite pendente | `401` | `E-mail ou senha inválidos.` |
| Sem token, token desconhecido ou expirado, usuário inativado depois do login | `401` | `Sua sessão expirou. Faça login novamente.` |
| Link de redefinição desconhecido, já usado, substituído por um pedido novo, expirado, ou de usuário inativado depois do pedido | `422` | `Este link de redefinição é inválido ou expirou. Solicite um novo.` |
| Nova senha com menos de 8 caracteres | `422` | `A senha precisa ter pelo menos 8 caracteres.` |
| Corpo inválido (campo ausente, senha com mais de 128 caracteres) | `422` | erros de validação do FastAPI |

As respostas `401` trazem o cabeçalho `WWW-Authenticate: Bearer`.

## Decisões

- **Mensagem única para qualquer falha de login** (US02-CA02). Inclui o usuário inativo (US02-CA03), para não revelar quais e-mails estão cadastrados nem a situação da conta. Quando o e-mail não existe, a API verifica a senha contra um hash fixo, para a resposta levar o mesmo tempo.
- **Token opaco guardado no banco, em vez de JWT.** Um JWT continua válido até expirar; com a sessão no banco dá para encerrá-la na hora, como pedem a US03-CA03, a US06 e a US08 (o usuário inativado perde o acesso já na próxima requisição).
- **Primeiro Administrador por rota protegida por token, não por comando de terminal.** Quem faz o deploy não precisa de acesso ao terminal do container; o `SETUP_TOKEN` fecha a janela entre o deploy e o primeiro acesso, e a rota só cria usuário com o banco vazio.
- **Resposta igual para qualquer pedido de redefinição.** `POST /auth/password-reset` responde a mesma coisa para e-mail cadastrado, desconhecido ou de usuário inativo, e também quando o envio do e-mail falha (a falha vai para o log e o Sentry). Assim, a rota não serve para descobrir quais e-mails estão cadastrados.
- **Link de redefinição guardado como hash, de uso único.** Como o token de sessão, só o hash SHA-256 fica na tabela `password_reset_links`.
- **Limite de 5 pedidos por hora, contado pelos próprios links.** Um pedido novo não apaga os links anteriores: marca-os como expirados, para que continuem entrando na contagem. Quando o usuário conclui a redefinição, todos os links dele são apagados. Os links de quem pede e nunca conclui serão apagados por uma rotina periódica ([#55](https://github.com/Advocondo/back/issues/55)).
- **Token no cabeçalho `Authorization`, não em cookie**, como já previsto na configuração de CORS (`CORS_ALLOW_CREDENTIALS=false`, ver [HTTPS e CORS](https-cors.md)).

## Configuração

Todas as variáveis são obrigatórias no ambiente (ver [Variáveis de ambiente e segredos](segredos.md)). A coluna do meio mostra o valor de desenvolvimento do `.env.example`.

| Variável | Valor no `.env.example` | O que faz |
| --- | --- | --- |
| `SESSION_DURATION_HOURS` | `12` | Duração da sessão sem "Manter conectado" |
| `REMEMBERED_SESSION_DURATION_DAYS` | `30` | Duração da sessão com "Manter conectado" |
| `SETUP_TOKEN` | vazio | Token exigido por `POST /setup`; vazio desliga a rota (ver [Primeiro Administrador](#primeiro-administrador)) |
| `FRONTEND_URL` | `http://localhost:3000` | Endereço do front, usado no link de redefinição |
| `PASSWORD_RESET_LINK_MINUTES` | `60` | Validade do link de redefinição |
| `PASSWORD_RESET_MAX_REQUESTS` | `5` | Pedidos de redefinição aceitos por usuário dentro da janela |
| `PASSWORD_RESET_REQUEST_WINDOW_MINUTES` | `60` | Janela, em minutos, do limite de pedidos |
| `SMTP_HOST` | vazio | Servidor SMTP. Vazio só é aceito com `ENVIRONMENT=local`: o e-mail, com o link, é escrito no log da API |
| `SMTP_PORT` | `587` | Porta do servidor SMTP |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | vazio | Credenciais do SMTP, se o servidor exigir |
| `SMTP_USE_TLS` | `true` | Usa STARTTLS na conexão |
| `EMAIL_FROM` | vazio | Remetente dos e-mails (ex.: `Advocondo <nao-responda@dominio>`). Obrigatório quando `SMTP_HOST` está definido |

### E-mail em desenvolvimento

Sem `SMTP_HOST`, a API não envia e-mail: ela escreve o conteúdo no log. Para pegar o link de redefinição:

```bash
docker compose logs api | grep -A12 "E-mail não enviado"
```

Fora do ambiente local, a API recusa funcionar sem SMTP, para que links de redefinição nunca acabem nos logs de produção.

## Primeiro Administrador

Os usuários entram por convite (US07), e só um Administrador logado pode convidar. O primeiro usuário, portanto, é criado uma única vez, depois do primeiro deploy, pela rota `POST /setup`. Ele já nasce como Administrador ativo.

A rota exige o cabeçalho `X-Setup-Token` com o valor da variável `SETUP_TOKEN`. Sem o token, qualquer pessoa que achasse a URL entre o deploy e o primeiro acesso do escritório poderia se tornar Administrador.

1. Gere um token e configure no ambiente (Coolify → back-end → variáveis): `openssl rand -hex 32`. O mínimo é de 32 caracteres; com menos, a API não sobe.
2. Crie o Administrador:

   ```bash
   curl -X POST https://<api>/setup \
     -H "Content-Type: application/json" \
     -H "X-Setup-Token: <token>" \
     -d '{"email": "ana@example.com", "name": "Ana Souza", "password": "<senha>"}'
   ```

3. Esvazie `SETUP_TOKEN` (`SETUP_TOKEN=`). Com o token vazio, a rota responde `404`.

Resposta `201`, com `id`, `name`, `email` e `role` do usuário criado. O e-mail é gravado em minúsculas.

| Situação | Status | Mensagem |
| --- | --- | --- |
| `SETUP_TOKEN` vazio (rota desligada) | `404` | `Registro não encontrado.` |
| Cabeçalho ausente ou token diferente | `403` | `Token de configuração inválido.` |
| Já existe algum usuário no banco | `422` | `O primeiro usuário já foi criado. Os demais entram por convite.` |
| Senha com menos de 8 caracteres | `422` | `A senha precisa ter pelo menos 8 caracteres.` |
| E-mail inválido, nome vazio ou senha com mais de 128 caracteres | `422` | Erro de validação da requisição |

O token é conferido antes de qualquer outra coisa, então quem não o tem não descobre se o banco já tem usuários. Por recusar quando já há usuário, a rota não serve de porta dos fundos para criar outros administradores, mesmo que o token vaze depois. Se o e-mail sair com erro de digitação, corrija direto no banco (`UPDATE users SET email = … WHERE role = 'admin'`) e faça login com o e-mail corrigido.

## Pendências

- **Limite de tentativas de login** (proteção contra força bruta). Não está em nenhuma história; precisa ser priorizado.
- **Logout** (`POST /auth/logout`): entra com a US06.
- **Limpeza de sessões e links de redefinição expirados**: [#55](https://github.com/Advocondo/back/issues/55).
- **Tempo de resposta do pedido de redefinição**: para e-mail cadastrado, a resposta demora mais, porque grava o link e envia o e-mail. Mover o envio para segundo plano resolve; hoje a mensagem é sempre igual, mas o tempo não.
- **Provedor de e-mail de produção**: ainda não foi escolhido. Qualquer um com SMTP serve.
- **Checagem por perfil** (`require_role`): entra com a US09, a primeira história que restringe rotas por perfil.
