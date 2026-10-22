# Documentos (PDF do acordo)

Geração e consulta do PDF de cada acordo ([US24](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us24)). O código fica em `src/advocondo/documentos/`. As peças reaproveitáveis ficam em `src/advocondo/common/`: `pdf.py` monta o PDF e `storage.py` guarda os bytes. Elas são a base do relatório do Cliente (US39) e do link por e-mail (US40).

Todas as rotas exigem o cabeçalho `Authorization: Bearer <token>`.

## Quem pode o quê

| Perfil | Gerar | Listar e baixar |
| --- | --- | --- |
| Administrador e Equipe Operacional | Sim | Os PDFs de qualquer acordo |
| Cliente | Não (`403`) | Só os PDFs dos acordos que ele vê no [painel](painel-cliente.md): acordos **ativos** dos condomínios vinculados a ele ([US10](users.md)). Para os outros, a resposta é `404 Acordo não encontrado.`, como se o acordo não existisse (US24-CA03). |

A regra do Cliente é a mesma consulta do painel (`client_agreements_query`), então os dois nunca divergem. O PDF só é encontrado pelo acordo dele: `GET /agreements/{outro}/pdfs/{id}` responde `404`, mesmo que o Cliente veja o outro acordo.

## O que vai no PDF (US24-CA01)

- **Condomínio:** nome, CNPJ e endereço, quando cadastrados.
- **Devedor:** nome e unidade.
- **Acordo:** situação, data do cadastro, valor total, número de parcelas, total pago, saldo em aberto e advogado responsável.
- **Parcelas:** número, vencimento, valor, data do pagamento e situação (`Em aberto`, `Pago` ou `Atrasado`, calculada com a data de hoje no Brasil, como em [Parcelas](parcelas.md)), com o total no fim.
- **Sem honorários.** O mesmo arquivo é baixado pelo Cliente, que nunca vê os valores do escritório ([US16](https://advocondo.github.io/docs/historias/ep03-cadastro-acordos/#us16) e EP06). Por isso o PDF não traz `fee_amount`, `fee_percentage` nem a divisão `condominium_amount` das parcelas. Um teste confere isso.

O PDF é uma foto do acordo no momento da geração e não muda depois. Para ver o estado atual, gere outro: cada geração cria um PDF novo e os anteriores continuam disponíveis.

## Rotas

### `POST /agreements/{id}/pdfs`

Gera o PDF com os dados atuais do acordo e o guarda. Resposta `201`:

```json
{
  "id": "…",
  "agreement_id": "…",
  "file_name": "acordo-20260302-060000.pdf",
  "content_type": "application/pdf",
  "size_bytes": 2817,
  "generated_by": {"id": "…", "name": "Ana Souza"},
  "generated_at": "2026-03-02T09:00:00Z",
  "download_url": "/agreements/…/pdfs/…"
}
```

O `file_name` usa a data e a hora da geração no horário de Brasília.

### `GET /agreements/{id}/pdfs`

Lista os PDFs do acordo, do mais recente para o mais antigo, com os mesmos campos acima.

### `GET /agreements/{id}/pdfs/{pdf_id}`

Baixa o arquivo (`application/pdf`, `Content-Disposition: attachment`, `Cache-Control: no-store`). É o link de acesso (`download_url`, US24-CA02): uma rota da API, que pede login e confere a permissão do acordo a cada download. O front baixa com o token e oferece o arquivo ao usuário.

## Onde os arquivos ficam

Cada PDF tem uma linha na tabela `agreement_pdfs`, com o acordo, quem gerou, quando, o tipo e o tamanho. Os bytes ficam em um de dois lugares:

| Configuração | Onde ficam os bytes | Coluna preenchida |
| --- | --- | --- |
| Variáveis `S3_` vazias (padrão) | Na própria linha, em `content` (`bytea`) | `content` |
| `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` e `S3_SECRET_ACCESS_KEY` definidas | Em um bucket S3-compatível (Amazon S3, Cloudflare R2, Backblaze B2), na chave `agreements/{acordo}/pdfs/{pdf}.pdf` | `storage_key` |

- Uma `CHECK` garante que só uma das duas colunas está preenchida.
- **Configuração pela metade derruba a API na subida**, com a lista do que falta. Assim a API nunca volta a guardar no banco sem ninguém perceber. `S3_ENDPOINT_URL` fica vazia só no Amazon S3; no R2 e no B2 ela é obrigatória. Os valores de cada serviço estão no `.env.example`.
- **O bucket não precisa ser público.** A API lê o objeto e o entrega ela mesma, em vez de usar link público ou pré-assinado, para que a permissão do acordo valha sempre. A chave de acesso precisa ler e gravar só nesse bucket.
- **Ligar o bucket depois não quebra nada:** a leitura olha a linha, não a configuração. PDFs antigos, com `content`, continuam sendo servidos do banco. O contrário não funciona: se o bucket for desligado, os PDFs que estão nele dão erro até ele ser configurado de novo.
- O objeto é gravado no bucket antes do commit da linha. Se o commit falhar, sobra um objeto órfão no bucket, o que não causa problema.

Para usar em outra história: o modelo herda `StoredFileMixin`, o service recebe um `FileStorage` (`get_file_storage`) e chama `storage.save(linha, chave, bytes, tipo)` e `storage.load(linha)`. O conteúdo do PDF é descrito com `PdfDocument` (seções de rótulo e valor e tabelas) e gerado com `render_pdf`.

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Sem token, token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Cliente tentando gerar | `403` | `Você não tem permissão para esta operação.` |
| Acordo inexistente, ou que o Cliente não vê | `404` | `Acordo não encontrado.` |
| PDF inexistente, ou de outro acordo | `404` | `PDF não encontrado.` |

## Testes

`tests/support/pdf.py` (`pdf_text`) extrai o texto do PDF gerado, para os testes conferirem o conteúdo. O armazenamento no bucket é testado com um cliente S3 falso, em memória (`tests/support/storage.py`), sem rede.
