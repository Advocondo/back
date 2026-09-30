# HTTPS e CORS

O front roda na Vercel e a API no Coolify, em domínios diferentes. Por isso a API precisa de CORS configurado, liberando exatamente os domínios do front, e de HTTPS obrigatório, porque trafega dados financeiros e de autenticação.

## HTTPS

O certificado e o redirecionamento de HTTP para HTTPS ficam no proxy do Coolify (Traefik), e não na aplicação. A API recebe o tráfego já descriptografado pelo proxy.

### Configuração

1. **DNS:** crie um registro `A` do domínio da API (ex.: `api.<dominio>`) apontando para o IP público da instância na Oracle Cloud.
2. **Portas na Oracle Cloud:** libere as portas `80` e `443` em dois lugares:
    - na *Security List* (ou *Network Security Group*) da VCN da instância;
    - no firewall da própria VM. As imagens da Oracle vêm com regras de `iptables` que bloqueiam tudo além do SSH.

    A porta `80` precisa ficar aberta mesmo com HTTPS: o Let's Encrypt usa ela para validar o domínio, e é por ela que chega o acesso que será redirecionado.
3. **Coolify:** no recurso da API, preencha o campo **Domains** com a URL **começando com `https://`** (ex.: `https://api.<dominio>`) e faça o redeploy. O Coolify emite o certificado do Let's Encrypt, renova sozinho e redireciona HTTP para HTTPS.
4. **HSTS:** depois de confirmar que o HTTPS funciona, defina `HSTS_MAX_AGE` na API (ver abaixo).

### Verificação

```bash
# HTTP deve redirecionar para HTTPS (status 301, 302, 307 ou 308, com Location https://...)
curl -sI http://api.<dominio>/health | grep -iE "^HTTP|^location"

# HTTPS deve responder 200, com certificado válido e o cabeçalho HSTS
curl -sI https://api.<dominio>/health | grep -iE "^HTTP|strict-transport-security"
```

### HSTS

Com `HSTS_MAX_AGE` maior que zero, a API envia `Strict-Transport-Security`. A partir daí, o navegador passa a usar só HTTPS com o domínio da API, mesmo que alguém digite `http://`.

- Comece com um valor baixo (ex.: `300`, 5 minutos) e, depois de confirmar que tudo funciona, suba para `31536000` (1 ano).
- **Não ligue** o HSTS antes de o HTTPS estar funcionando: os navegadores deixariam de acessar a API até o prazo expirar.
- Em desenvolvimento, deixe `0` (desligado).

## CORS

O navegador só deixa o front ler as respostas da API se a origem do front estiver liberada. A API libera:

- **Produção:** os domínios listados em `CORS_ALLOW_ORIGINS`, separados por vírgula (ex.: `https://<projeto>.vercel.app` e o domínio próprio, se houver).
- **Previews da Vercel:** as origens que casam com `CORS_ALLOW_ORIGIN_REGEX`.

Qualquer outra origem não recebe os cabeçalhos CORS e é bloqueada pelo navegador. Sem essas variáveis, **nenhuma** origem externa é liberada. `*` é recusado na inicialização.

### Padrão dos previews da Vercel

A Vercel gera dois formatos de URL de preview:

- por deploy: `https://<projeto>-<hash de 9 caracteres>-<time>.vercel.app`
- por branch: `https://<projeto>-git-<branch>-<time>.vercel.app`

A regex que cobre os dois, e só eles:

```
https://<projeto>-(?:[a-z0-9]{9}|git-[a-z0-9-]+)-<time>\.vercel\.app
```

Troque `<projeto>` pelo nome do projeto na Vercel e `<time>` pelo slug do time (aparece nas URLs de preview). A regex precisa casar com a origem **inteira** (a API usa `fullmatch`), então não é preciso `^` nem `$`. Os testes em `tests/unit/test_security.py` cobrem origens liberadas e bloqueadas, incluindo domínios parecidos e previews de outros times.

### Risco da regex de preview

Os subdomínios de `vercel.app` são escolhidos pelos usuários da Vercel. Qualquer pessoa pode criar um projeto chamado, por exemplo, `<projeto>-abcdefghi-<time>`, cuja URL de produção casa com a regex. Por isso:

- **`CORS_ALLOW_CREDENTIALS` fica `false`.** Com ele desligado, o navegador não envia cookies para a API em requisições de outra origem, e um site malicioso liberado pela regex não consegue agir em nome de um usuário logado. A autenticação deve usar o header `Authorization`, e não cookies.
- Se um dia a autenticação passar a usar cookies (`CORS_ALLOW_CREDENTIALS=true`), a API de **produção** deve liberar só os domínios de produção, sem a regex. Os previews devem apontar para a API de staging.

### Métodos e cabeçalhos

São permitidos os métodos `GET`, `POST`, `PUT`, `PATCH` e `DELETE` e os cabeçalhos `Authorization`, `Content-Type` e `X-Request-ID`. O front consegue ler o `X-Request-ID` da resposta, útil para reportar erros. Os preflights (`OPTIONS`) ficam em cache no navegador por 10 minutos.

## Variáveis

| Variável | Produção | Desenvolvimento |
| --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | `https://<projeto>.vercel.app` (+ domínio próprio) | `http://localhost:3000` |
| `CORS_ALLOW_ORIGIN_REGEX` | regex dos previews (acima) | vazio |
| `CORS_ALLOW_CREDENTIALS` | `false` | `false` |
| `HSTS_MAX_AGE` | `31536000` (depois do período de teste) | `0` |
