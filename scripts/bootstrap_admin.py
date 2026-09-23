"""Create the first production admin, recording credentials only in a private local note.

Run after deploying sources and before opening the app to the team. Fails if the
admin already exists; it never resets an existing account or prints its password.
"""
from pathlib import Path
import os
import secrets
import subprocess

root = Path(__file__).resolve().parents[1]
note = root / 'ACCESS-PRIVATE.txt'
if note.exists():
    raise SystemExit('Private access note already exists. No credentials were changed.')
password = secrets.token_urlsafe(24)
content = ('Studio reklam — dostęp administratora\n\n'
           'Adres: http://192.168.15.42:8765\n'
           'Sieć: biuro lub firmowy VPN\n'
           'Login: admin\nHasło: ' + password + '\n\n'
           'Po zalogowaniu można zmienić hasło w menu konta.\n'
           'Dodaj osobne konta redaktorów w zakładce Zespół. Nie udostępniaj konta admin całemu zespołowi.\n')
fd = os.open(note, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as target:
    target.write(content)
command = '''set -eu
umask 077
cd /home/ubuntu/google-ads-assets/current
set -a
. /home/ubuntu/google-ads-assets/service.env
set +a
password_file=/home/ubuntu/google-ads-assets/data/.bootstrap-password
trap 'rm -f "$password_file"' EXIT
cat > "$password_file"
/home/ubuntu/google-ads-assets/venv/bin/python app.py create-admin admin --password-file "$password_file"
'''
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', 'ubuntu@192.168.15.42', command], input=password, text=True, capture_output=True)
if result.returncode:
    raise SystemExit('Admin bootstrap failed; private note retained for recovery. Inspect CLI without printing passwords.')
print('Admin created. Credentials saved in ACCESS-PRIVATE.txt (mode600); no password printed.')
