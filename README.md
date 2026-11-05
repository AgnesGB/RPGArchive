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
  editor Markdown com barra de formatação, **editor visual de tabelas**, imagens coladas ou arrastadas no texto e pré-visualização.
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
- **Acervo**: todas as imagens e arquivos do mundo (imagens, PDF, EPUB, TXT, MD, DOCX, ODT, ZIP; até 40 MB).

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
