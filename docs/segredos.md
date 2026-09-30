# Variáveis de ambiente e segredos

Credenciais de banco, chaves de APIs externas e qualquer outro segredo **nunca** são versionados. Cada ambiente guarda os seus próprios valores, fora do repositório.

## Onde fica cada coisa

| Ambiente | Onde ficam as variáveis | Quem tem acesso |
| --- | --- | --- |
| Local | Arquivo `.env`, copiado do `.env.example` | Cada desenvolvedor, na própria máquina |
| Staging | Variáveis de ambiente do recurso no Coolify | Quem administra o Coolify |
| Produção | Variáveis de ambiente do recurso no Coolify | Quem administra o Coolify |

Staging ainda não existe (ver a issue de CD, #41). Quando existir, deve ser um recurso separado no Coolify, com credenciais próprias e diferentes das de produção.

## O que está no repositório

- **`.env.example`**: lista todas as variáveis que o back-end usa, com comentários e apenas valores de desenvolvimento local. Toda variável nova entra aqui no mesmo PR que passa a usá-la.
- **`.gitignore`**: ignora `.env` e `.env.*`, exceto o `.env.example`.
- **`.dockerignore`**: ignora os mesmos arquivos, então nenhum `.env` vai parar dentro da imagem Docker.
- **CI**: o workflow roda o [gitleaks](https://github.com/gitleaks/gitleaks) em todo push e PR, e falha se encontrar algo que pareça um segredo (senha, token, chave privada) no histórico.

## Staging e produção (Coolify)

As variáveis são definidas no painel do Coolify, em cada recurso (**Environment Variables**):

- **API**: `DATABASE_URL`, `SENTRY_DSN`, `CORS_ALLOW_ORIGINS` e as demais variáveis do `.env.example` que se aplicam a produção (ver [Observabilidade](observabilidade.md)).
- **PostgreSQL**: usuário, senha e banco são definidos pelo próprio Coolify ao criar o recurso. A `DATABASE_URL` da API usa a URL interna que o Coolify mostra na página do banco.

Regras:

- Gere senhas fortes e únicas por ambiente, por exemplo com `openssl rand -base64 32`.
- Não reaproveite em produção os valores do `.env.example`.
- Não copie segredos para issues, PRs, chats ou logs. Se precisar compartilhar, use um gerenciador de senhas.

## Rotação de credenciais

**Quando rotacionar:**

- imediatamente, se houver suspeita de vazamento (inclusive se um segredo for commitado, mesmo que o commit seja removido depois);
- quando alguém com acesso ao Coolify sai da equipe;
- periodicamente, a cada 6 meses.

### Senha do PostgreSQL

A imagem do Postgres só lê `POSTGRES_PASSWORD` na primeira inicialização. Por isso, mudar a variável no Coolify **não** muda a senha de um banco que já existe: é preciso alterá-la dentro do banco.

1. Gere a nova senha: `openssl rand -base64 32`.
2. No Coolify, abra o terminal do recurso PostgreSQL e rode:

   ```bash
   psql -U <usuario> -d <banco> -c "ALTER USER <usuario> WITH PASSWORD '<nova-senha>';"
   ```

3. Atualize a senha nas variáveis do recurso PostgreSQL no Coolify, para que a configuração continue igual à do banco.
4. Atualize a `DATABASE_URL` da API no Coolify com a nova senha e faça o redeploy da API.
5. Confira se a API consegue falar com o banco (`GET /health/ready`).

Entre os passos 2 e 4, conexões novas da API falham. Por isso, faça os passos em sequência, em um horário de pouco uso.

### Chaves de APIs externas

1. Gere uma nova chave no painel do serviço externo, sem revogar a antiga ainda.
2. Atualize a variável no Coolify e faça o redeploy da API.
3. Confira se a integração funciona.
4. Revogue a chave antiga no serviço externo.

### Se um segredo for commitado

1. Rotacione o segredo na hora, seguindo os passos acima. Remover o commit não basta, porque o valor continua no histórico e em clones e forks.
2. Remova o valor do código e mova-o para uma variável de ambiente.
3. Registre o ocorrido na issue ou PR correspondente, sem colar o segredo.
