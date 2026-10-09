# Caça-Promo

Site pessoal que guarda os produtos que você quer comprar e, todo dia às 7h (Brasília),
pesquisa as melhores ofertas na web com a API da Claude (web search) e mostra o menor
preço, as outras ofertas, o histórico e um aviso quando passa abaixo do seu preço-alvo.

## Como funciona

- `products.json`: lista de produtos (editada pelo site ou direto no GitHub).
- `search_deals.py`: para cada produto, pesquisa e grava `data/deals.json`.
- `.github/workflows/daily.yml`: GitHub Actions roda o script todo dia (e quando você
  adiciona um produto) e salva o resultado no repositório.
- `index.html`: o site (GitHub Pages), lê os dois JSONs.

## Setup (uma vez, ~10 min)

1. Crie um repositório **público** no GitHub (Pages grátis exige repo público; ou use
   conta Pro para repo privado) e suba esta pasta.
2. Crie uma chave grátis em https://serper.dev (2.500 buscas ao cadastrar, sem cartão) e
   adicione em **Settings → Secrets and variables → Actions → New repository secret**
   com o nome `SERPER_API_KEY`. (Opcional: se preferir a pesquisa com IA da Claude, que é
   mais esperta porém mais cara, use o secret `ANTHROPIC_API_KEY` e defina a variável
   `PROVIDER=claude`.)
3. **Settings → Pages**: Source = *Deploy from a branch*, branch `main`, pasta `/ (root)`.
4. **Actions → Busca diária de promoções → Run workflow** para a primeira busca.
5. Abra `https://SEU_USUARIO.github.io/NOME_DO_REPO/`.

### Adicionar produtos pelo site

1. Em GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained**:
   escolha só este repositório, permissões **Contents: Read and write** e
   **Actions: Read and write** (esta última é para a aba Pesquisar).
2. No site, clique em ⚙︎ e informe usuário, repositório e token (fica só no seu navegador).
3. Use **+ Produto**. O site faz o commit em `products.json` e a busca roda sozinha.

Sem o token, edite `products.json` direto no GitHub, o efeito é o mesmo.

### Aba Pesquisar

Digite o nome de um produto e o site dispara o workflow `search.yml` no GitHub Actions,
que pesquisa o menor preço e grava `data/search.json`. O resultado aparece na tela em
1 a 3 minutos (precisa do token configurado em ⚙︎). Depois da pesquisa, o botão
**+ Acompanhar todo dia** coloca o produto na lista diária. Cada pesquisa gasta uma busca do Serper.

## Ajustes

- Horário: `cron` em `daily.yml` (em UTC; Brasília = UTC−3).
- Provedor padrão (Serper): 1 busca no Google Shopping por produto, sem IA. Custa a partir
  de US$ 0,30 por 1.000 buscas depois dos créditos grátis, ou seja, centavos por mês.
  Filtra anúncios que não batem com o nome, usados e preços muito fora do normal.
- Provedor Claude (`PROVIDER=claude`): pesquisa mais inteligente, mas custa bem mais
  (`MAX_SEARCHES` buscas web + tokens por produto). Modelo em `CLAUDE_MODEL`.

## Cuidados

- Confira sempre o link e o preço na loja antes de comprar: o resultado vem de uma busca
  automática e pode ter erro ou preço já expirado.
- O repositório público expõe sua lista de desejos. Não coloque nada que não queira mostrar.
