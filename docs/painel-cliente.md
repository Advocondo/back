# Painel do Cliente

Status simplificado dos acordos para o síndico ou a administradora ([US37](https://advocondo.github.io/docs/historias/ep06-painel-cliente/#us37)). O código fica em `src/advocondo/painel_cliente/`.

A rota exige o cabeçalho `Authorization: Bearer <token>` de um usuário **Cliente**. Administrador e Equipe Operacional recebem `403` (eles usam `/agreements`), e quem não está logado recebe `401`.

## `GET /client-panel/agreements`

Devolve a lista dos acordos **ativos** dos condomínios vinculados ao Cliente ([US10](users.md)), sem nenhum valor do escritório:

```json
[
  {
    "id": "5f0c…",
    "condominium_name": "Residencial das Flores",
    "debtor_name": "Maria Souza",
    "debtor_unit": "Bloco B, 302",
    "status": "atrasado",
    "overdue_installments": 2,
    "next_due_date": "2026-11-10"
  }
]
```

| Campo | Regra |
| --- | --- |
| `status` | `atrasado` se ao menos uma parcela estiver atrasada; `em_dia` caso contrário (inclui acordo sem parcelas ou com tudo pago). |
| `overdue_installments` | Quantidade de parcelas atrasadas. |
| `next_due_date` | Menor vencimento entre as parcelas sem baixa que vencem hoje ou depois; `null` se não houver nenhuma. |

A ordem é: atrasados primeiro, depois por nome do condomínio e por nome do devedor (ordenação do PostgreSQL, a mesma das outras listagens).

## Regras

- **Só os condomínios vinculados (US37-CA01).** O filtro é um `JOIN` na tabela `user_condominiums` dentro da própria consulta, então acordos de outros condomínios nunca saem do banco. Cliente sem vínculo recebe `[]` (US10-CA02).
- **Sem honorários nem valores (US37-CA02).** O schema de resposta é uma lista fechada de campos. `total_amount`, `fee_amount`, `fee_percentage`, `amount` e `condominium_amount` não aparecem, e um teste confere cada um.
- **Status simplificado (US37-CA02).** O Cliente vê apenas `em_dia` ou `atrasado`.
- **Status calculado, nunca gravado.** Usa a mesma regra de atraso das parcelas ([Parcelas](parcelas.md)), com "hoje" na data do Brasil: uma parcela vence no fim do dia, e à noite a data UTC já é a do dia seguinte.
- **Só acordos `active`.** A consulta filtra pela situação ativa; situações novas de acordo ficam de fora até alguém decidir mostrá-las.

## Erros

| Código | Quando |
| --- | --- |
| `401` | Sem login ou sessão inválida. |
| `403` | Usuário que não é do perfil Cliente. |

## Pendências

- Detalhe de um acordo (US38), relatório para download (US39) e e-mail de atraso (US40).
- Filtros, busca e paginação: o volume por condomínio é pequeno.
