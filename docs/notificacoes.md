# Notificações

Aviso interno, no sino, de que uma parcela ficou em atraso ([US30](https://advocondo.github.io/docs/historias/ep04-parcelas/#us30)). O código fica em `src/advocondo/notificacoes/`. O envio de e-mail ao Cliente é outra história ([US40](https://advocondo.github.io/docs/historias/ep06-painel-cliente/#us40)).

## Quando uma notificação é criada (US30-CA01)

A situação "Atrasado" é calculada a cada consulta e nunca gravada ([US27](https://advocondo.github.io/docs/historias/ep04-parcelas/#us27)), então nada no sistema percebe sozinho o momento em que uma parcela atrasa. Um comando diário procura as parcelas atrasadas que ainda não geraram notificação e cria uma para cada destinatário:

- **Parcela atrasada:** sem `payment_date` e com vencimento antes de hoje no Brasil, a mesma regra da US27. Uma parcela paga só em parte continua atrasada ([US28](https://advocondo.github.io/docs/historias/ep04-parcelas/#us28)). As parcelas de acordo cancelado ficam de fora, porque saem da cobrança ([US20](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us20)).
- **Destinatários:** o advogado responsável pelo acordo ([US18](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us18)), se estiver ativo, e todos os Administradores ativos. Quem é as duas coisas recebe uma notificação só. Um acordo sem responsável notifica só os Administradores.
- **Uma notificação por parcela e usuário**, garantida pelo banco (`uq_notifications_user_id_installment_id`). Rodar o comando de novo não repete avisos. Se a parcela for paga, estornada e atrasar de novo, ninguém é avisado outra vez.
- Os destinatários são os do dia em que a parcela atrasou. Trocar o responsável depois não move notificações já criadas.
- Na primeira execução, todas as parcelas que já estão atrasadas geram notificação. Elas podem ser marcadas como lidas de uma vez.

## Comando diário

O comando roda uma vez por dia, como *Scheduled Task* do back-end no Coolify, logo depois da meia-noite de Brasília (frequência `5 3 * * *`, em UTC, no container da API), para a parcela que venceu ontem já entrar no aviso da manhã:

```bash
python -m advocondo.notificacoes.overdue
```

Ao terminar, ele mostra quantas notificações criou (ex.: `4 notificações de parcela em atraso criadas.`). Para rodar em desenvolvimento:

```bash
docker compose exec api uv run python -m advocondo.notificacoes.overdue
```

## Rotas

Todas exigem o cabeçalho `Authorization: Bearer <token>`, de qualquer perfil, e cada usuário vê e marca só as próprias notificações.

### `GET /notifications`

Notificações do usuário, da mais recente para a mais antiga, com `limit` (50 por padrão, até 200) e `offset`. `unread_count` é o contador do sino: conta todas as não lidas, não só as da página. Cada notificação traz o que a central mostra e os ids para abrir a parcela ou o acordo ao clicar (US30-CA02):

```json
{
  "unread_count": 1,
  "notifications": [
    {
      "id": "…",
      "created_at": "2026-03-02T03:05:00Z",
      "read_at": null,
      "installment": {
        "id": "…",
        "agreement_id": "…",
        "number": 5,
        "installment_count": 6,
        "due_date": "2026-03-01",
        "remaining_amount": "1237.50",
        "debtor": {"id": "…", "name": "Rosângela Prado", "unit": "Bloco A 101"}
      }
    }
  ]
}
```

### `POST /notifications/{id}/read`

Marca a notificação como lida, quando o usuário a abre. A resposta é a notificação, com `read_at`. Marcar de novo mantém a data da primeira leitura.

### `POST /notifications/read`

Marca todas as notificações do usuário como lidas ("Marcar todas como lidas"). Responde `204`.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Notificação inexistente ou de outro usuário | `404` | `Notificação não encontrada.` |
| `limit` fora de 1 a 200, `offset` negativo | `422` | erros de validação do FastAPI |
