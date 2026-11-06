# Deploy no PythonAnywhere — midiri.pythonanywhere.com

Tudo que muda entre o seu PC e o servidor fica em **um lugar só**: o arquivo `~/RPGArchive/.env` no servidor.
O código é o mesmo.

| O quê | Onde configurar |
|---|---|
| Segredos e modo produção | `~/RPGArchive/.env` (passo 3) |
| Qual código o site roda | Aba **Web** › arquivo WSGI (passo 5) |
| Virtualenv | Aba **Web** › *Virtualenv* (passo 4) |
| Arquivos estáticos | Aba **Web** › *Static files* (passo 4) |
| HTTPS | Aba **Web** › *Force HTTPS* (passo 4) |
| Login com Google | Google Cloud Console (passo 7) |

---

> O usuário é **Midiri** (com M maiúsculo) e os caminhos diferenciam maiúsculas: `/home/Midiri/...`.
> O domínio e o arquivo WSGI continuam em minúsculas (`midiri.pythonanywhere.com`, `/var/www/midiri_pythonanywhere_com_wsgi.py`).

## 1. Clonar (console Bash do PythonAnywhere)

Aba **Consoles** › **Bash**:

```bash
cd ~
git clone https://github.com/YggdrasilGeekNetwork/RPGArchive.git
```

> O repositório tem os assets do `mapkit/`, cuja licença não permite redistribuir — deixe o repo **privado** no GitHub.
> Com repo privado, o `git clone` pede usuário e senha: a senha é um **Personal Access Token**
> (GitHub › Settings › Developer settings › Fine-grained tokens, permissão *Contents: Read-only* só nesse repo).

## 2. Criar o virtualenv

Ainda no Bash:

```bash
mkvirtualenv rpgarchive --python=python3.12
pip install -r ~/RPGArchive/requirements.txt
```

(Se o 3.12 não existir na sua conta, use a versão mais nova da lista da aba Web, e a mesma nos passos 2 e 4.)

## 3. Criar o `.env` do servidor

```bash
cd ~/RPGArchive
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # copie a saída
nano .env
```

Deixe assim:

```ini
SECRET_KEY=<cole a chave gerada>
APP_ENV=production
SQLITE_JOURNAL_MODE=DELETE
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Salve com `Ctrl+O`, `Enter`, `Ctrl+X`. O `.env` está no `.gitignore`, então não vai para o GitHub.

- `APP_ENV=production` liga HTTPS no callback do Google e cookie seguro, e o app se recusa a subir sem `SECRET_KEY`.
- `SQLITE_JOURNAL_MODE=DELETE` porque o modo WAL do SQLite não funciona direito no disco de rede do PythonAnywhere.

## 4. Criar o web app (aba **Web**)

1. **Add a new web app** › domínio `midiri.pythonanywhere.com` › **Manual configuration** (não escolha "Flask") › Python **3.12**.
2. Seção **Virtualenv**: `/home/Midiri/.virtualenvs/rpgarchive`
3. Seção **Static files**, adicione:

   | URL | Directory |
   |---|---|
   | `/static/` | `/home/Midiri/RPGArchive/lore/static` |

4. Seção **Security**: ligue **Force HTTPS**.

## 5. Arquivo WSGI

Na seção **Code**, clique no link **WSGI configuration file** (`/var/www/midiri_pythonanywhere_com_wsgi.py`),
**apague tudo** e cole o conteúdo de [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py). Salve.

## 6. Recarregar

Botão verde **Reload** no topo da aba Web. Abra https://midiri.pythonanywhere.com.

O banco (`instance/lore.db`) e os uploads (`instance/uploads/`) são criados sozinhos na primeira requisição.
Se der erro, veja o **Error log** (link na aba Web, seção *Log files*).

## 7. Login com Google (opcional)

1. https://console.cloud.google.com/apis/credentials › seu ID do cliente OAuth.
2. Em **URIs de redirecionamento autorizados** adicione:
   `https://midiri.pythonanywhere.com/auth/google/callback`
3. Em **Origens JavaScript autorizadas** (se pedir): `https://midiri.pythonanywhere.com`
4. Coloque `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `~/RPGArchive/.env` do servidor e dê **Reload**.

> Contas gratuitas só acessam a internet por uma lista de sites liberados. Os domínios do Google OAuth estão nela;
> se o login do Google der erro de conexão no Error log, é isso.

---

## Atualizar o site depois

No seu PC: `git push`. No Bash do PythonAnywhere:

```bash
bash ~/RPGArchive/deploy/atualizar.sh
```

Ele faz `git pull`, instala dependências novas e recarrega o site.

## Backup

Tudo que é do usuário está em `~/RPGArchive/instance/` (banco + uploads + nada mais). Para baixar:

```bash
cd ~ && zip -r backup-$(date +%F).zip RPGArchive/instance
```

e baixe o zip pela aba **Files**.

## Limites da conta gratuita

- 512 MB de disco no total — uploads de até 40 MB enchem rápido. Acompanhe na aba **Files**.
- O site precisa ser "renovado" a cada 3 meses (botão **Run until 3 months from today** na aba Web); você recebe e-mail antes.
