# Observabilidade

A API tem três peças de observabilidade: health checks, logs estruturados e rastreamento de erros com o [Sentry](https://sentry.io). O objetivo é que uma falha em produção seja percebida pela equipe antes de um usuário reclamar.

## Health checks

| Endpoint | Para que serve | Verifica | Resposta |
| --- | --- | --- | --- |
| `GET /health` | *Liveness*: o processo está de pé | Nada além da própria API | Sempre `200` enquanto a API responde |
| `GET /health/ready` | *Readiness*: a API consegue trabalhar | Banco de dados e demais dependências externas | `200` se tudo está ok, `503` se algo falhou |

Exemplo de resposta com o banco fora do ar:

```json
{"status": "error", "checks": {"database": "error"}}
```

- O motivo da falha vai só para o log (nível `ERROR`, com o traceback). A resposta pública não expõe detalhes internos.
- O **health check do container no Coolify** deve usar `/health`. Se usasse `/health/ready`, uma queda do banco faria o Coolify reiniciar a API, o que não resolve nada.
- O **monitoramento externo** (uptime) deve usar `/health/ready`, porque é ele que mostra se o sistema está funcionando de fato.
- Para verificar uma nova dependência externa (ex.: serviço de e-mail), adicione uma função em `get_health_checks`, em `src/advocondo/health.py`.

## Logs estruturados

Em produção, cada log é uma linha JSON no stdout, que o Coolify coleta e exibe na aba de logs do recurso:

```json
{"timestamp": "2026-09-30T12:11:44.333050+00:00", "level": "INFO", "logger": "advocondo.requests", "message": "request", "method": "GET", "path": "/acordos", "status_code": 200, "duration_ms": 12.4, "request_id": "cfd7828f12334c15a6545e9a32ecd6c5"}
```

- **Campos fixos:** `timestamp` (UTC), `level`, `logger`, `message`. Logs de erro trazem também `exception`, com o traceback.
- **Uma linha por requisição**, com método, caminho, status e duração. Requisições aos health checks ficam em `DEBUG`, para não poluir os logs, e respostas `5xx` ficam em `ERROR`.
- **`request_id`:** toda requisição recebe um identificador, devolvido no header `X-Request-ID` e presente em todos os logs e no evento do Sentry daquela requisição. Se o proxy já mandar um `X-Request-ID` válido, ele é reaproveitado. Para investigar um erro, basta buscar o `request_id` nos logs.
- **Níveis:** `DEBUG` para detalhes de diagnóstico, `INFO` para o funcionamento normal, `WARNING` para algo inesperado que não impediu a operação, `ERROR` para falhas que precisam de atenção e `CRITICAL` para quando a API não consegue funcionar.
- **Informação extra:** use `extra=`, que vira campo no JSON: `logger.info("acordo criado", extra={"acordo_id": acordo.id})`.
- **Não registre dados pessoais** (nome, CPF, contato de devedores) nem segredos nos logs. Use identificadores.

Em desenvolvimento, `LOG_FORMAT=console` troca o JSON por texto legível.

## Rastreamento de erros (Sentry)

O Sentry só é ligado quando `SENTRY_DSN` está definida, então fica desligado em desenvolvimento e nos testes. Com ele ligado:

- exceções não tratadas e respostas `5xx` viram eventos no Sentry;
- logs de nível `ERROR` também viram eventos (ex.: falha de um health check);
- cada evento traz `environment`, `release` e o `request_id` como tag;
- **nenhum dado pessoal é enviado** (`send_default_pii=False`): nem IP, nem cookies, nem headers de autenticação.

### Configuração em produção

1. No Sentry, crie um projeto **FastAPI** para o back-end. A issue de monitoramento do front (Advocondo/front#43) pode usar a mesma organização, com um projeto separado.
2. No Coolify, nas variáveis de ambiente da API, defina:

   | Variável | Valor |
   | --- | --- |
   | `SENTRY_DSN` | DSN do projeto (Settings → Client Keys) |
   | `ENVIRONMENT` | `producao` (ou `staging`) |
   | `RELEASE` | versão ou hash do commit, se disponível |
   | `LOG_LEVEL` | `INFO` |
   | `LOG_FORMAT` | `json` |

3. Faça o redeploy da API.

## Alertas

Os alertas são configurados no painel do Sentry, e não no código. Configure pelo menos estes, filtrando por `environment:producao`:

1. **Erro novo:** em *Alerts → Create Alert → Issues*, com a condição "A new issue is created". Avisa na primeira vez que um erro aparece.
2. **Pico de erros:** um alerta de issues com a condição "The issue is seen more than 10 times in 1 hour" (ajuste o limite ao volume real). Avisa quando um erro conhecido dispara.
3. **API ou banco fora do ar:** um monitor de uptime apontando para `https://<dominio-da-api>/health/ready`, que alerta quando a resposta não for `200`. Pode ser o *Uptime Monitoring* do Sentry, se o plano tiver, ou um serviço externo gratuito, como o UptimeRobot.

Em todos, a ação deve notificar um canal que a equipe acompanhe (e-mail da equipe, Slack ou Discord). Depois de configurar, teste: derrube o banco de staging ou gere um erro de propósito e confira se o alerta chega.

O Coolify também pode avisar quando um container para ou um deploy falha, pelas notificações da instância (e-mail, Discord, Telegram etc.). Vale ligar essas notificações também, mas elas não substituem os alertas acima.
