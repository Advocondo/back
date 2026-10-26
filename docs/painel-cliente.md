# Painel do Cliente

Status simplificado dos acordos para o síndico ou a administradora ([US37](https://advocondo.github.io/docs/historias/ep06-painel-cliente/#us37)) as parcelas sem pagamento de cada acordo ([#89](https://github.com/Advocondo/back/issues/89)) e o histórico de pagamentos de cada morador ([US38](https://advocondo.github.io/docs/historias/ep06-painel-cliente/#us38)). O código fica em `src/advocondo/painel_cliente/`.

As rotas exigem o cabeçalho `Authorization: Bearer <token>` de um usuário **Cliente**. Administrador e Equipe Operacional recebem `403` (eles usam `/agreements`), e quem não está logado recebe `401`.

## `GET /client-panel/agreements`

Devolve a lista dos acordos **ativos** dos condomínios vinculados ao Cliente ([US10](users.md)), sem nenhum valor do escritório:

```json
[
  {
    "id": "5f0c…",
    "condominium_name": "Residencial das Flores",
    "debtor_id": "8a1d…",
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
| `debtor_id` | Id do morador, para abrir o histórico dele em `GET /client-panel/debtors/{id}/history`. |
| `status` | `atrasado` se ao menos uma parcela estiver atrasada; `em_dia` caso contrário (inclui acordo sem parcelas ou com tudo pago). |
| `overdue_installments` | Quantidade de parcelas atrasadas. |
| `next_due_date` | Menor vencimento entre as parcelas sem baixa que vencem hoje ou depois; `null` se não houver nenhuma. |

A ordem é: atrasados primeiro, depois por nome do condomínio e por nome do devedor (ordenação do PostgreSQL, a mesma das outras listagens).

## `GET /client-panel/condominiums/{condominium_id}/report`

Baixa o relatório simplificado do condomínio em PDF. A rota exige autenticação de Cliente e só localiza o condomínio pelo vínculo desse usuário. O relatório reúne os acordos ativos daquele condomínio e apresenta nome do Cliente e do condomínio, devedor/unidade, situação, parcelas vencidas/em dia/pagas, total pago, saldo em aberto e vencimento mais próximo. CNPJ pode aparecer quando cadastrado.

O PDF usa o renderer comum de documentos (`common/pdf.py`) e uma lista explícita de campos permitidos. Ele não inclui honorários, comissão, divisão da parcela entre condomínio e escritório, dados de responsáveis jurídicos, administração ou equipe, nem informações de outros condomínios. Condomínio sem vínculo responde `404`; Cliente sem acordos ativos vinculados recebe um relatório com resumo zerado e sem linhas de acordo. A resposta é `application/pdf` e usa `Cache-Control: no-store`.

## `GET /client-panel/agreements/{id}/installments`

Devolve as parcelas **sem pagamento** (em aberto ou atrasadas) de um acordo da lista acima, por número:

```json
[
  {"number": 2, "due_date": "2026-02-28", "amount": "100.00", "remaining_amount": "60.00", "status": "overdue"},
  {"number": 3, "due_date": "2026-03-31", "amount": "100.00", "remaining_amount": "100.00", "status": "open"}
]
```

| Campo | Regra |
| --- | --- |
| `amount` | Valor total da parcela, sem a divisão entre condomínio e honorários. |
| `remaining_amount` | Quanto falta pagar; menor que `amount` depois de um pagamento parcial ([US28](parcelas.md#pagamento-parcial-us28)). |
| `status` | `open` ou `overdue`, pela mesma regra das parcelas. |

O acordo precisa estar na lista do Cliente: ativo e de um condomínio vinculado a ele. Acordo de outro condomínio, cancelado ou inexistente recebe o mesmo `404`, para o Cliente não descobrir se ele existe.

## `GET /client-panel/debtors/{id}/history`

Histórico de pagamentos de um morador do condomínio ([US38](https://advocondo.github.io/docs/historias/ep06-painel-cliente/#us38)), somado por **competência**, o mês de vencimento das parcelas, do mais antigo para o mais recente:

```json
{
  "debtor_name": "José Simão",
  "debtor_unit": "Bloco B 304",
  "months": [
    {"month": "2026-01", "paid_amount": "100.00", "open_amount": "0.00", "status": "pago"},
    {"month": "2026-02", "paid_amount": "40.00", "open_amount": "60.00", "status": "atrasado"},
    {"month": "2026-03", "paid_amount": "0.00", "open_amount": "100.00", "status": "em_aberto"}
  ]
}
```

| Campo | Regra |
| --- | --- |
| `month` | Competência, `AAAA-MM`. Mês sem parcela não aparece. |
| `paid_amount` | Soma do que foi pago nas parcelas que vencem no mês, inclusive pagamentos parciais ([US28](parcelas.md#pagamento-parcial-us28)). |
| `open_amount` | Soma do que falta pagar nessas parcelas. |
| `status` | `atrasado` se alguma parcela sem pagamento do mês já venceu; `em_aberto` se ainda há parcela sem pagamento; `pago` caso contrário. |

- **Todos os acordos do morador** entram na soma, inclusive vários acordos com vencimento no mesmo mês.
- **Acordo cancelado entra só com o que foi pago.** O histórico serve para prestar contas na assembleia, então o que o morador pagou antes do cancelamento continua aparecendo. O que não foi pago saiu da cobrança ([US20](parcelas.md#acordo-cancelado-us20)) e não entra em `open_amount` nem no `status`. É a única rota do painel que considera acordo cancelado.
- O morador precisa ser de um condomínio vinculado ao Cliente: de outro condomínio ou inexistente recebe `404 Devedor não encontrado.`. Morador sem acordos recebe `months: []`.

## Notificações automáticas (US40)

O sistema envia um e-mail informativo aos usuários Cliente ativos vinculados ao condomínio quando um acordo é registrado, atualizado em dado visível ao Cliente, cancelado, quando um pagamento é registrado/estornado, quando uma parcela muda de valor ou vencimento, e quando dados de contato ou identificação do condomínio são alterados. A notificação só é disparada depois que a alteração de negócio foi confirmada no banco.

O corpo do e-mail contém uma mensagem genérica, o nome do condomínio e o endereço configurado em `FRONTEND_URL`. Não inclui honorários, divisão financeira, devedor, unidade ou dados internos. Cada entrega bem-sucedida cria uma linha em `client_notification_logs` com Cliente, condomínio, tipo do evento, mensagem, link e data/hora (`sent_at`). Uma falha de e-mail é registrada no log da aplicação e não desfaz a alteração de negócio; ela não gera linha de envio bem-sucedido.

O comando `python -m advocondo.painel_cliente.monthly_report_task` fecha o mês anterior, gera e armazena um PDF por condomínio com Clientes ativos vinculados e envia uma notificação de relatório pronto. A execução é idempotente: um relatório existente é reutilizado e um e-mail já registrado para aquele condomínio/período não é reenviado. O PDF fica acessível somente a Clientes vinculados, pelo endpoint `GET /client-panel/condominiums/{condominium_id}/reports/{year}/{month}`.

Configure o comando como *Scheduled Task* diário no Coolify, às 03:00 (`0 3 * * *`), no container da API. A rotina sempre processa o mês civil anterior no horário de Brasília e pode ser repetida com segurança. O link para a rota de relatório no frontend fica pendente da implementação da tela; até lá, o e-mail informa que o PDF está disponível no painel, sem incluir um link inválido.

## Regras

- **Só os condomínios vinculados (US37-CA01/US39).** O filtro é um `JOIN` na tabela `user_condominiums` dentro da própria consulta, então acordos de outros condomínios nunca saem do banco. Cliente sem vínculo recebe `[]` na lista e `404` ao solicitar um relatório.
- **Sem honorários nem valores (US37-CA02).** O schema de resposta é uma lista fechada de campos. `total_amount`, `fee_amount`, `fee_percentage`, `amount` e `condominium_amount` não aparecem, e um teste confere cada um.
- **Histórico só com totais (US38-CA01).** Por competência, só o total pago e o total em aberto: nada de honorários, da divisão do valor nem do detalhe de cada parcela. Lista fechada de campos, conferida em teste.
- **Parcelas só com o valor total (#89-CA02 e US38-CA01).** A lista de parcelas mostra o valor da parcela e o saldo, mas nunca `fee_amount` nem `condominium_amount`; o schema também é uma lista fechada e um teste confere os campos. Mostrar o valor total ao Cliente segue a leitura da US38 e ainda precisa da confirmação do time.
- **Status simplificado (US37-CA02).** O Cliente vê apenas `em_dia` ou `atrasado`.
- **Status calculado, nunca gravado.** Usa a mesma regra de atraso das parcelas ([Parcelas](parcelas.md)), com "hoje" na data do Brasil: uma parcela vence no fim do dia, e à noite a data UTC já é a do dia seguinte.
- **Só acordos `active`.** A consulta filtra pela situação ativa; situações novas de acordo ficam de fora até alguém decidir mostrá-las. A exceção é o histórico do morador, que mantém o que foi pago em acordo cancelado.

## Erros

| Código | Quando |
| --- | --- |
| `401` | Sem login ou sessão inválida. |
| `403` | Usuário que não é do perfil Cliente. |
| `404` | `Acordo não encontrado.`: acordo de outro condomínio, cancelado ou inexistente, na lista de parcelas. `Devedor não encontrado.`: morador de outro condomínio ou inexistente, no histórico. |

## Pendências

- E-mail de atraso (US40).
- Filtros, busca e paginação: o volume por condomínio é pequeno.
