# 👁️ Aquele que Observa

Site colaborativo para escrever e organizar a lore de campanhas de RPG.
Inspirado no Notion (páginas), no vvd.world (wiki do mundo) e no Milanote (mapas mentais).

**Stack:** Flask (Python) · SQLite · Tailwind CSS (CDN) · JS puro. Monolito, sem etapa de build.

## Funcionalidades

- **Login** com e-mail + senha ou com Google. Contas com o mesmo e-mail verificado são vinculadas.
- **Aparência**: modo claro ou escuro + cor de destaque (amarelo, vermelho, azul, rosa, roxo, verde),
  pelo botão redondo do topo. Fica salvo por usuário.
- **Mundos compartilhados**: o dono convida pessoas por e-mail. Quem está no mundo vê tudo e pode criar e editar
  páginas, mapas mentais, mapas e arquivos. Convites para e-mails sem conta são liberados quando a pessoa se cadastra.
- **Páginas estilo Notion**: capa (upload, link ou nenhuma) com ajuste de posição, ícone em emoji, subpáginas
  (árvore na lateral), categorias (personagem, local, facção, criatura, item, evento, livro/registro, nota),
  e **editor de blocos** direto na página (salva sozinho; "Propriedades" cuida de capa, ícone, categoria e ano):
  - `/` ou `+` insere blocos: texto, títulos, listas, tarefas, lista recolhível, citação, destaque (callout com ícone),
    divisor, tabela, código, imagem, **vídeo/música por link** (YouTube, Spotify, SoundCloud, Vimeo, Deezer, Apple Music,
    Twitch), áudio, vídeo e arquivo enviados, subpágina, link para página, 2/3 colunas e markdown.
  - Alça `⋮⋮`: arraste para cima/baixo ou **para o lado de outro bloco (cria colunas)**; clique para transformar, colorir,
    duplicar ou apagar. Colunas e imagens/vídeos se redimensionam arrastando a borda.
  - Atalhos: `# `, `## `, `### `, `- `, `1. `, `[] `, `> `, `---`, ```` ``` ````; `[[` liga uma página; Ctrl+K cria link;
    selecionar texto mostra negrito/itálico/cor/marca-texto. Colar ou soltar imagens/áudios/arquivos cria os blocos.
  - Divisores decorativos: todo `.svg`/`.png` em `lore/static/dividers/` vira um estilo (SVG ganha a cor do tema).
  - Páginas antigas em Markdown aparecem num bloco "Markdown", com o botão "converter em blocos".
  - `[[Nome]]` ou `[[Nome|texto]]` liga páginas; links para páginas inexistentes ficam vermelhos e criam a página.
  - **Relações** (0..N) entre páginas: pai/mãe, cônjuge, irmão, aliado, inimigo, membro de, vive em, possui ou texto livre.
  - Cada página mostra suas relações, ligações nos mapas mentais e quem a menciona.
- **Mapas mentais**: canvas com pan/zoom; cards de ideia, página (com capa), imagem e arquivo.
  Puxe a bolinha da borda de um card até outro para ligá-los (seta com rótulo, dá para inverter).
  Arraste páginas da lateral, cole ou solte imagens e arquivos. Atualiza sozinho quando outra pessoa edita.
- **Várias linhas do tempo** (com cor): uma página com ano pode aparecer em uma ou várias; há também a visão "Todas".
- **Várias árvores genealógicas**: cada árvore é um grupo de pessoas; os laços pai/mãe e cônjuge valem para o mundo todo.
- **Mapas**, em dois modos:
  - **Editar mapa** (estilo Inkarnate): começa do zero ou de uma imagem de fundo; grade **quadrada ou hexagonal**;
    pincel e balde de **terreno**, **paredes nas arestas** (pedra, madeira, porta, janela, cerca, passagem secreta),
    **objetos** (árvores, casas, móveis, criaturas, itens…), desfazer/refazer e salvamento automático com controle de versão.
  - **Jogar**: **marcadores** (ligados a páginas, com livro/arquivo anexado e anotações) e **tokens** de jogadores
    arrastáveis, sincronizados entre todos.
  - **Névoa** (fog of war): ferramenta "Névoa" no editor (pincel, cobrir/revelar tudo) e botão "Revelar névoa" no
    modo Jogar para ir abrindo durante a sessão. O mestre vê através (listrado); jogadores veem opaco e não recebem
    marcadores/tokens que estejam sob a névoa.
- **Mesa (aba Jogar)** — papel **jogador**, diferente de colaborador:
  - Jogadores só entram na Mesa; qualquer rota do planejamento os redireciona para lá (`get_world` barra por padrão).
  - **Encontros** (só o mestre): planeje cada cena com mapas, páginas e arquivos do acervo, mais anotações do mestre.
    **Começar** põe os mapas do encontro na mesa; páginas e arquivos são revelados um a um ("revelar") quando os
    jogadores acharem; **Encerrar** tira os mapas da mesa (o que foi revelado continua revelado).
  - O mestre vê a barra lateral do planejamento também na Mesa; jogadores não.
  - **Mapas da mesa**: o mestre escolhe quais mapas compartilhar; jogadores só observam e movem tokens
    (anotações, anexos e passagens secretas ficam escondidos).
  - **Arquivos encontrados**: o mestre revela páginas (leitura) e arquivos do acervo; só esses arquivos ficam acessíveis.
  - **Área do grupo**: um "mundo da mesa" ligado ao principal, onde jogadores (e o mestre) fazem anotações, mapas mentais,
    cronologias e árvores genealógicas.
- **Barra lateral recolhível**: o adesivo colado na borda da barra (ou Ctrl+\).
- **Acervo**: todas as imagens e arquivos do mundo (imagens, PDF, EPUB, TXT, MD, DOCX, ODT, ZIP, áudio e vídeo; até 40 MB).

## Rodando

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # opcional: preencha para ativar o Google
.venv\Scripts\python app.py
```

Abra http://localhost:5000. Banco em `instance/lore.db` e arquivos em `instance/uploads/` (apague `instance/` para zerar).
Bancos da versão anterior são migrados automaticamente ao iniciar.

## Kit de assets do editor de mapas

Os terrenos e objetos ficam em `lore/static/mapkit/` e são gerados a partir dos pacotes em `assets/`:

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python scripts\build_mapkit.py
```

Para trocar ou acrescentar tiles e objetos, edite as listas em `scripts/build_mapkit.py` (pacotes em `assets/` e
`assets/novos/`; os cristais da aba **Catalisadores** ficam em `assets/catalisadores/`).

Categorias: Paredes (peças que encaixam no grid), Paredes · peças, Masmorra, Personagens, Criaturas, Animais,
Catalisadores, Árvores e plantas, Natureza selvagem, Pedras, Decoração, Construções, Vila, Interior e Itens.
No editor: **R** gira 90° (Shift+R volta), o controle deslizante gira de 15 em 15°, e há espelhar, duplicar e tamanho.

Os pacotes são de uso pessoal/gratuito e não permitem redistribuir os arquivos (veja `lore/static/mapkit/CREDITS.md`):
não publique `assets/` nem `mapkit/` em repositório público.

**Uso comercial.** Alguns pacotes não podem ser usados em nada que gere dinheiro (assinatura, anúncio, venda): as
versões grátis do Cute Fantasy e Cute Fantasy Icons (Kenmi), e ainda sem licença confirmada o Fan-tasy Tileset, o Farm RPG,
o FreeEnvironment e os cristais. Para gerar um kit sem eles:

```powershell
.venv\Scripts\python scripts\build_mapkit.py --comercial                    # substitui o kit do site
.venv\Scripts\python scripts\build_mapkit.py --comercial --out C:\tmp\kit   # só para comparar
```

Os terrenos desses pacotes (grama, água, areia, caminho…) ganham substitutos com a mesma chave, então mapas já
pintados continuam abrindo; objetos deles somem dos mapas. Rodar sem `--comercial` volta o kit completo.
A lista fica em `NON_COMMERCIAL` no script: ao comprar a versão premium de um pacote (ou confirmar a licença), tire-o
de lá. Os ícones pixel da interface (*Raven Fantasy Icons*, versão grátis) também são só para uso pessoal e não passam
por esse script.

## Ícones

- **Pixel-art** (navegação, categorias, tipos de card): sprite em `lore/static/icons/raven.png` + `raven.css`,
  gerado do pack *Raven Fantasy Icons* (não versionado). Para trocar/acrescentar, edite `ICONS` em `scripts/build_icons.py`
  (índice no spritesheet de 16 px) e rode `python scripts/build_icons.py "<pasta do pack>"`.
  Nos templates: `{{ ri('castle') }}`, `{{ ri('map', 32) }}` (use 16/32/48/64 px: múltiplos inteiros mantêm o pixel nítido).
- **Ações** (apagar, fechar, editar…): ícones de traço em `lore/static/icons/ui.svg` → `{{ ui('trash') }}`.
- Ícone de página/mundo: emoji escolhido pela pessoa ou `ri:<nome>` (padrão da categoria) → `{{ valor|glyph }}`.
- No JS (`lore/static/icons.js`): `ri()`, `ui()`, `glyph()`.

## Login com Google

1. Em https://console.cloud.google.com/apis/credentials crie um **ID do cliente OAuth** do tipo *Aplicativo da Web*.
2. Em *URIs de redirecionamento autorizados* adicione `http://localhost:5000/auth/google/callback`.
3. Coloque `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env` e reinicie.

O botão "Entrar com Google" só aparece quando essas variáveis estão definidas.
Use `localhost` (e não `127.0.0.1`) no navegador, para bater com a URI cadastrada.

## Estrutura

```
app.py                  ponto de entrada
lore/__init__.py        create_app, config, CSRF, tema
lore/db.py              SQLite: schema + migração
lore/access.py          acesso por membro do mundo, barra lateral
lore/auth.py            cadastro, login, Google, convites, preferências de tema
lore/worlds.py          mundos, configurações, colaboradores
lore/pages.py           páginas e relações
lore/history.py         linhas do tempo e árvores genealógicas
lore/boards.py          mapas mentais (cards + ligações) e API
lore/maps.py            mapas com marcadores e tokens, API
lore/files.py           uploads, acervo, entrega de arquivos com checagem de acesso
lore/static/board.js    canvas do mapa mental
lore/static/map.js      mapas: editor (grade, terreno, paredes, objetos) e modo jogar
lore/static/mapkit/     terrenos e objetos gerados (manifest.json)
scripts/build_mapkit.py gera o mapkit a partir de assets/
lore/templates/         Jinja + Tailwind
```

## Para produção

Passo a passo do PythonAnywhere (midiri.pythonanywhere.com): veja [DEPLOY.md](DEPLOY.md).

- Defina `SECRET_KEY` e `APP_ENV=production` no `.env` e rode com um servidor WSGI (ex.: `waitress-serve --port=5000 app:app`) atrás de HTTPS.
- Faça backup de `instance/` (banco + uploads).
- Troque o Tailwind via CDN pelo Tailwind CLI se quiser CSS compilado.
- Cadastre a URI de callback do Google com o domínio real.
