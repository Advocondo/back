# Trilha de auditoria

Uma lista só com as ações registradas em acordos, parcelas e usuários, para o Administrador ([front#72](https://github.com/Advocondo/front/issues/72)). Ela mostra o protótipo [Trilha de auditoria](https://advocondo.github.io/docs/prototipos/trilha-de-auditoria/). O código fica em `src/advocondo/auditoria/`.

Ainda não há história de usuário para esta tela. Os critérios abaixo são os propostos na issue.

A rota não grava nada: ela lê os três registros que já existem.

| Registro | Tabela | O que guarda | Tipo |
| --- | --- | --- | --- |
| Movimentações de parcela ([US31](https://advocondo.github.io/docs/historias/ep04-parcelas/#us31)) | `installment_change_logs` | Baixa, correção, estorno e edição de vencimento ou valor | `financial` |
| Alterações do acordo ([US19](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us19)) | `agreement_edit_logs` | Devedor, valor total e honorários | `financial` |
| Gestão de usuários ([US11](https://advocondo.github.io/docs/historias/ep02-usuarios-perfis/#us11)) | `user_audit_logs` | Convite, ativação e desativação, perfil e condomínios do Cliente | `users` |

Cancelamentos e reativações de acordo ([US20](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us20)) ficam de fora, porque não guardam quem fez a ação.

## `GET /audit`

Só o Administrador (CA03). Outros perfis recebem `403`, e sem login a resposta é `401`.

As ações vêm da mais recente para a mais antiga (CA01), com paginação por `limit` (50 por padrão, até 200) e `offset`. `total` conta todas as ações que atendem aos filtros, não só as da página.

Os filtros se combinam (CA02):

| Parâmetro | O que faz |
| --- | --- |
| `actor_id` | Só as ações desse usuário |
| `date_from`, `date_to` | Período em dias, no horário de Brasília, com os dois dias incluídos. Um dos dois pode faltar. Início depois do fim dá `422` |
| `category` | `financial` (parcelas e acordos) ou `users` |

```json
{
  "total": 2,
  "entries": [
    {
      "id": "…",
      "occurred_at": "2026-03-04T12:00:00Z",
      "category": "users",
      "action": "condominiums_changed",
      "actor": { "id": "…", "name": "Carla Admin" },
      "old_value": null,
      "new_value": null,
      "agreement": null,
      "installment_number": null,
      "field": null,
      "target_user": { "id": "…", "name": "Paulo Síndico" },
      "added_condominiums": [{ "id": "…", "name": "Residencial Mirante" }],
      "removed_condominiums": []
    },
    {
      "id": "…",
      "occurred_at": "2026-03-02T15:00:00Z",
      "category": "financial",
      "action": "payment_recorded",
      "actor": { "id": "…", "name": "Marina Dias" },
      "old_value": null,
      "new_value": "150.00",
      "agreement": {
        "id": "…",
        "debtor": { "id": "…", "name": "José Simão", "unit": "101" },
        "condominium": { "id": "…", "name": "Residencial Mirante" }
      },
      "installment_number": 1,
      "field": null,
      "target_user": null,
      "added_condominiums": [],
      "removed_condominiums": []
    }
  ]
}
```

- `action` traz os mesmos valores das rotas de histórico de cada registro: as movimentações de parcela de `/agreements/{id}/financial-history`, `agreement_edited` para as alterações do acordo, e as ações de `/users/{id}/history`.
- Nas ações financeiras vem `agreement`. `installment_number` vem nas movimentações de parcela, e `field` nas alterações do acordo.
- Nas ações sobre usuários vem `target_user`. `added_condominiums` e `removed_condominiums` só vêm preenchidos em `condominiums_changed`.
- `old_value` e `new_value` seguem o formato de cada registro: datas em `AAAA-MM-DD` e dinheiro com duas casas.
- `actor` vem `null` numa ação de usuário cujo autor foi removido.
