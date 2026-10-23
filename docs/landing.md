# Página institucional

Conteúdo editável da landing page do escritório ([US04](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us04)). O Administrador muda textos e fotos sem depender de um desenvolvedor, e o site público ([US01](https://advocondo.github.io/docs/historias/ep01-portal-autenticacao/#us01)) lê o conteúdo daqui. O código fica em `src/advocondo/landing/`.

## Seções

A página tem seções fixas, as mesmas do [protótipo do site institucional](https://advocondo.github.io/docs/prototipos/site-institucional/). O Administrador edita o conteúdo de cada seção, mas não cria nem remove seções. Dentro de uma seção, as listas (áreas, parágrafos, avaliações, membros da equipe) podem ganhar ou perder itens, dentro dos limites abaixo.

| Seção | Campos |
| --- | --- |
| `hero` | `title`, `subtitle`, `button_label` |
| `practice_areas` | `title`, `areas` (1 a 12, cada uma com `title` e `description`), `closing_text` |
| `online_service` | `title`, `text`, `button_label` |
| `condominium_advisory` | `title`, `paragraphs` (1 a 6) |
| `reviews` | `title`, `reviews` (0 a 8, cada uma com `author`, `author_details` opcional, `rating` de 1 a 5 e `text`), `call_to_review_title`, `call_to_review_text`, `button_label`, `google_reviews_url` (opcional) |
| `why_us` | `title`, `paragraphs` (1 a 6), `button_label` |
| `team` | `title`, `members` (1 a 12, cada um com `name`, `role` e `photo_id` opcional), `highlights` (0 a 6) |
| `contact_form` | `title`, `subtitle` |
| `visit` | `title`, `text`, `button_label` |
| `contact` | Todos opcionais: `phone`, `whatsapp`, `email`, `address`, `opening_hours`, `facebook_url`, `instagram_url` |

Regras dos campos:

- Títulos, nomes, cargos e textos de botão têm de 1 a 150 caracteres. Textos e parágrafos têm de 1 a 1.000. Os espaços nas pontas são removidos.
- `phone` e `whatsapp` aceitam máscara e são gravados só com os dígitos, com DDD (10 ou 11 dígitos). O front monta o link do WhatsApp a partir de `whatsapp`.
- Links (`google_reviews_url`, `facebook_url`, `instagram_url`) precisam ser `https`.
- Campo fora desta lista é recusado com `422`.

O bloco `contact` alimenta o rodapé e todos os botões e ícones de WhatsApp e redes sociais. Assim, trocar o número exige mudar um lugar só.

Ficam fixos no front: o logo, os links de navegação, os campos do formulário de contato, o ano do copyright e os links de política de privacidade e de cookies.

## Conteúdo inicial

Todo o conteúdo fica no banco, na tabela `landing_blocks`, com uma linha por seção. A migration que cria a tabela (`183ab32038c5`) também grava as 10 seções com os textos do protótipo aprovado. Assim o site já sai completo do deploy, e daí em diante só o Administrador muda os textos, pela API.

Os textos ficam congelados na migration de propósito. Mudar o conteúdo depois do deploy é trabalho do Administrador, não de uma nova migration. O teste de migrations (`test_app_integration.py`) confere que a carga inicial passa pelos mesmos schemas da edição.

Ficam de fora da carga inicial:

- **as avaliações**: as do protótipo foram parafraseadas e não podem ser publicadas como se fossem de clientes reais. O Administrador copia as avaliações reais do Google;
- **o número de WhatsApp e os links das redes sociais**, que não estão no protótipo;
- **as fotos da equipe**: os membros vêm sem `photo_id`, e o site mostra um placeholder.

Nos testes, o banco é criado direto dos modelos, sem rodar migrations. Por isso a fixture `landing_page` (`tests/fixtures/landing.py`) grava uma página de teste antes de cada teste que precisa dela.

## Imagens

As imagens (hoje, só as fotos da equipe) ficam no PostgreSQL, numa coluna `bytea` da tabela `landing_images`. São poucas e pequenas, o que dispensa armazenamento externo ou volume no servidor.

- O tipo é lido da assinatura do arquivo, e não do nome nem do `Content-Type` enviado. São aceitos PNG, JPEG e WebP. SVG fica de fora porque pode carregar scripts.
- Uma imagem nunca muda: foto nova é imagem nova, com outro `id`. Por isso o navegador pode guardá-la em cache para sempre.
- Para usar uma foto, o front envia a imagem em `POST /landing/images` e coloca o `id` devolvido no `photo_id` do membro ao salvar a seção `team`.
- Ao salvar uma seção, as imagens que ela deixou de usar (foto trocada ou membro removido) são apagadas.

## Rotas

### `GET /landing`

Pública. Devolve todas as seções da página.

### `PATCH /landing`

Só **Administrador**. Recebe uma ou mais seções, e cada seção enviada substitui a anterior por inteiro. As seções não enviadas não mudam. A mudança fica pública assim que é salva (US04-CA01). A resposta é a página inteira, como em `GET /landing`.

```json
{
  "hero": {
    "title": "Seu direito é a nossa luta!",
    "subtitle": "Há mais de 14 anos defendendo os seus direitos.",
    "button_label": "Fale conosco no WhatsApp"
  }
}
```

### `POST /landing/images`

Só **Administrador**. Recebe o arquivo no campo `file` (`multipart/form-data`). Resposta `201` com o `id` da imagem.

### `GET /landing/images/{id}`

Pública. Devolve os bytes da imagem com o `Content-Type` dela e com `Cache-Control: public, max-age=31536000, immutable`.

### `DELETE /landing/images/{id}`

Só **Administrador**. Apaga uma imagem enviada mas nunca usada, por exemplo quando o Administrador desiste da troca de foto. Imagem em uso numa seção é recusada. Resposta `204`.

## Configuração

| Variável | Exemplo | Uso |
| --- | --- | --- |
| `LANDING_IMAGE_MAX_KILOBYTES` | `2048` | Tamanho máximo de cada imagem enviada |

## Respostas de erro

| Situação | Status | `detail` |
| --- | --- | --- |
| Edição ou envio sem token, ou com token desconhecido ou expirado | `401` | `Sua sessão expirou. Faça login novamente.` |
| Edição ou envio por Equipe Operacional ou Cliente (US04-CA02) | `403` | `Você não tem permissão para esta operação.` |
| Imagem inexistente | `404` | `Imagem não encontrada.` |
| Apagar imagem em uso | `409` | `A imagem está em uso na página institucional.` |
| `photo_id` de uma imagem que não existe | `422` | `A página usa uma imagem que não foi enviada. Envie a imagem de novo.` |
| Arquivo que não é PNG, JPEG nem WebP | `422` | `Envie uma imagem PNG, JPEG ou WebP.` |
| Imagem maior que o limite | `422` | `A imagem passa de 2048 KB.` (com o valor configurado) |
| Seção inválida ou desconhecida, seção enviada como `null` ou edição sem nenhuma seção | `422` | erros de validação do FastAPI |

## Pendências

- O destino dos envios do formulário de contato não está definido em nenhuma história ([#87](https://github.com/Advocondo/back/issues/87)).
- O protótipo não tem a tela de edição do Administrador. A tela fica com o front ([front#4](https://github.com/Advocondo/front/issues/4)).
