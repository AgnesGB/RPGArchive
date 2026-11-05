#!/usr/bin/env bash
# Atualiza o site no PythonAnywhere depois de um push no GitHub.
# Uso (num console Bash do PythonAnywhere):  bash ~/RPGArchive/deploy/atualizar.sh
set -euo pipefail

cd "$HOME/RPGArchive"
git pull --ff-only
"$HOME/.virtualenvs/rpgarchive/bin/pip" install -q -r requirements.txt
touch /var/www/midiri_pythonanywhere_com_wsgi.py   # recarrega o site
echo "Pronto: https://midiri.pythonanywhere.com"
