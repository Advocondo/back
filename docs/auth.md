# Autenticação

Login com e-mail e senha ([US02](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us02)). O código fica em `src/advocondo/auth/`.

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

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| E-mail não cadastrado, senha errada, usuário inativo ou com convite pendente | `401` | `E-mail ou senha inválidos.` |
| Sem token, token desconhecido ou expirado, usuário inativado depois do login | `401` | `Sua sessão expirou. Faça login novamente.` |
| Corpo inválido (campo ausente, senha com mais de 128 caracteres) | `422` | erros de validação do FastAPI |

As respostas `401` trazem o cabeçalho `WWW-Authenticate: Bearer`.

## Decisões

- **Mensagem única para qualquer falha de login** (US02-CA02). Inclui o usuário inativo (US02-CA03), para não revelar quais e-mails estão cadastrados nem a situação da conta. Quando o e-mail não existe, a API verifica a senha contra um hash fixo, para a resposta levar o mesmo tempo.
- **Token opaco guardado no banco, em vez de JWT.** Um JWT continua válido até expirar; com a sessão no banco dá para encerrá-la na hora, como pedem a US03-CA03, a US06 e a US08 (o usuário inativado perde o acesso já na próxima requisição).
- **Token no cabeçalho `Authorization`, não em cookie**, como já previsto na configuração de CORS (`CORS_ALLOW_CREDENTIALS=false`, ver [HTTPS e CORS](https-cors.md)).

## Configuração

| Variável | Padrão | O que faz |
| --- | --- | --- |
| `SESSION_DURATION_HOURS` | `12` | Duração da sessão sem "Manter conectado" |
| `REMEMBERED_SESSION_DURATION_DAYS` | `30` | Duração da sessão com "Manter conectado" |

## Primeiro Administrador

Os usuários entram por convite (US07), e só um Administrador logado pode convidar. O primeiro usuário, portanto, é criado por um comando, uma única vez, depois do primeiro deploy. Ele já nasce como Administrador ativo.

Em produção, no terminal do container da API (Coolify → back-end → *Terminal*):

```bash
python -m advocondo.users.create_admin --email ana@example.com --name "Ana Souza"
```

Localmente, prefixe com `uv run`. A senha é digitada no terminal, duas vezes, e não aparece no histórico do shell.

O comando recusa:

| Situação | Mensagem |
| --- | --- |
| Já existe algum usuário no banco | `O primeiro usuário já foi criado. Os demais entram por convite.` |
| E-mail em formato inválido | `E-mail inválido: …` |
| Senha com menos de 8 caracteres | `A senha precisa ter pelo menos 8 caracteres.` |
| Confirmação diferente da senha | `As senhas não conferem.` |

Por recusar quando já há usuário, o comando não serve de porta dos fundos para criar outros administradores. Se o e-mail sair com erro de digitação, corrija direto no banco (`UPDATE users SET email = … WHERE role = 'admin'`) e faça login com o e-mail corrigido.

## Pendências

- **Limite de tentativas de login** (proteção contra força bruta). Não está em nenhuma história; precisa ser priorizado.
- **Logout** (`POST /auth/logout`) e **limpeza de sessões expiradas**: entram com a US06.
- **Checagem por perfil** (`require_role`): entra com a US09, a primeira história que restringe rotas por perfil.
