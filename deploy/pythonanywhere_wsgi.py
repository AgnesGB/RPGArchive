# Cole este conteúdo no arquivo WSGI do PythonAnywhere:
#   aba "Web" > seção "Code" > link "WSGI configuration file"
#   (/var/www/midiri_pythonanywhere_com_wsgi.py) — apague tudo que estiver lá e cole isto.
#
# As configurações (SECRET_KEY, Google etc.) ficam no arquivo .env da pasta do projeto,
# não aqui. Veja DEPLOY.md.
import os
import sys

# ~ = /home/<seu usuário> (no PythonAnywhere o usuário diferencia maiúsculas: /home/Midiri)
PROJECT_DIR = os.path.expanduser("~/RPGArchive")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import app as application  # noqa: E402
