# Migração para Rails — plano

Decisões (8/nov/2026):

- **Stack igual à do Arkheion**: Rails 8 só de API (GraphQL + PostgreSQL) + front em Remix/React.
  O lore maker continua um **produto separado** (site próprio), mas no mesmo padrão, para reaproveitar
  o painel do mestre e ficar fácil ligar com as fichas do Arkheion depois.
- **Hospedagem fora do PythonAnywhere** (ele só roda Python) e **separada do Arkheion**: um serviço gerenciado
  (Render, Fly.io ou Railway). Escolha final na fase 0.
- **Separação Mundos × Mesas só no Rails**: o site Flask atual fica como está (só correções) até o novo substituí-lo.
- **Começa do zero**: sem migrar contas e conteúdo do site atual.

---

## Ideia do produto

Cada pessoa tem **Mundos** (lore maker) e **Mesas** (jogo), em abas separadas.

| Área | O que tem |
|---|---|
| **Mundos** | O que já existe hoje: páginas (editor de blocos), categorias, favoritos, relações, mapas mentais, linhas do tempo, árvores genealógicas, mapas (editor com conjuntos próprios), acervo, colaboradores. |
| **Mesas** | Lugar de jogo, separado da preparação. Ao criar uma mesa, o mestre escolhe a qual mundo ela fica atrelada (opcional). |
| **Área do jogador** | Ao aceitar o convite, o jogador informa o **nome do personagem** (editável depois). Na mesa aparece o nome do personagem e, embaixo, menor e mais claro, o nome do jogador. |
| **Área do mestre** | Planejamento de encontros + o dashboard do mestre vindo do Arkheion: soundboard, rolagem de dados, causar dano, ver o básico dos personagens (testes de resistência, percepção passiva), mensagens secretas para personagens. |

**Fichas ficam no Arkheion.** O lore maker não terá fichas próprias; no futuro, a mesa poderá ligar cada jogador
à ficha dele no Arkheion (por isso o login e o modelo de mesa já nascem pensando nisso).

---

## Modelo de dados (rascunho)

```
users                (email, nome, senha/Google, avatar, preferências de tema)
worlds               (dono, nome, descrição, ícone, capa)
world_members        (world, user, papel: dono | editor)
pages / page_blocks, relations, favorites, boards/cards/links, timelines, trees, maps/pins/sets/tilesets, files (Active Storage)

tables               (mestre = user, world opcional, nome, sistema: "t20"…, código de convite)
table_members        (table, user, papel: gm | player, character_name, arkheion_character_id opcional)
table_invites        (table, email, token, aceito_em)
encounters           (table, …)  — vindos do planejamento de encontros
table_messages       (table, de, para (opcional = secreta), texto, lida_em)
```

Observação: `tables` conflita com nomes comuns em Rails/SQL; usar `Mesa`/`mesas` no código (como o Arkheion já faz nas rotas `dm/mesas`).

---

## Repositórios

Mesmo esquema do Arkheion (um repositório "raiz" com scripts + sub-repositórios):

| Repositório | Conteúdo |
|---|---|
| `rpgarchive` | raiz: `bin/setup`, `bin/dev`, `docker-compose.yml`, docs |
| `rpgarchive_api` | Rails 8 API-only, GraphQL (graphql-ruby), PostgreSQL, Active Storage (S3/R2) |
| `rpgarchive_app` | Remix + React + TypeScript + Tailwind |
| tempo real | Action Cable no próprio Rails **ou** um servidor Socket.io como o `arkheion_socket` (decidir na fase 5) |

O repositório Flask atual (`YggdrasilGeekNetwork/RPGArchive`) fica como referência e é arquivado no fim.

---

## Fases

| # | Fase | Entrega |
|---|---|---|
| 0 | **Base** | Repositórios, `bin/dev` com Docker (Postgres), CI rodando testes, escolha da hospedagem e primeiro deploy "olá mundo". |
| 1 | **Contas** | Cadastro/login (e-mail + senha, Google), perfil com foto, tema claro/escuro e cor. Tokens JWT como no Arkheion, já pensando em login único no futuro. |
| 2 | **Mundos (núcleo)** | Mundos, colaboradores/convites, páginas com editor de blocos, categorias, barra lateral com favoritos, relações, busca, ícones (pack Raven). |
| 3 | **Mundos (ferramentas)** | Acervo (arquivos), mapas mentais (filhos, lista "Relacionados"), linhas do tempo, árvores genealógicas (parentesco calculado). |
| 4 | **Mapas** | Editor de mapas (grade, terreno, paredes, objetos, conjuntos próprios), modo jogar com marcadores e tokens. O `map.js` atual entra num componente React primeiro e é refatorado depois. |
| 5 | **Mesas** | Mesas atreladas (ou não) a um mundo, convites, área do jogador (nome do personagem + nome do jogador), área do mestre com encontros e o dashboard do Arkheion (soundboard, dados, dano, testes, mensagens secretas), tempo real. |
| 6 | **Troca** | Domínio apontando para o site novo, PythonAnywhere desligado, repositório Flask arquivado. |

Cada fase termina com o site novo no ar (mesmo que ainda incompleto) e testes (Minitest na API, Vitest no app),
seguindo as regras do `CLAUDE.md` do Arkheion.

---

## Reaproveitamento

- **Do Arkheion**: autenticação (JWT/bcrypt/OAuth), estrutura GraphQL, setup Docker/`bin/*`, e o
  `components/dm/**` (painel do mestre, ~70 componentes React). Hoje o painel do mestre usa dados de exemplo
  (`createMockCharacter`); aqui ele passa a ler mesas e personagens de verdade da API.
- **Do site atual**: regras de negócio (parentesco da árvore, recorte de tilesets, filtro de HTML do editor),
  os scripts de canvas (`board.js`, `map.js`, `editor.js`), o sprite de ícones e a identidade visual.

## Riscos

- **Tamanho**: é praticamente reescrever o site. As fases 2–4 são as mais longas.
- **Arquivos**: serviços gerenciados não guardam arquivos em disco; uploads vão para armazenamento de objetos (S3/Cloudflare R2).
- **Tempo real**: mapas mentais e mapas hoje sincronizam por polling; na mesa (dados, dano, mensagens secretas) precisa ser em tempo real de verdade.
