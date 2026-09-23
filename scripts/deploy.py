"""Deploy this isolated internal service. Dry-run is the default; --apply performs deployment."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '/home/ubuntu/google-ads-assets'
FILES = ['app.py', 'background.py', 'svg_media.py', 'template_library.py', 'requirements.txt', 'templates', 'static', 'models', 'third_party', 'scripts/serve.py', 'scripts/google-ads-assets.service', 'README.md', 'SPEC.md', 'DEPLOY.md', 'docs/operations']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    missing = [name for name in FILES if not (ROOT / name).exists()]
    if missing:
        raise SystemExit('Missing release files: ' + ', '.join(missing))
    selected = FILES + (['storage.py'] if (ROOT / 'storage.py').exists() else [])
    release = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    print(f'Release {release}: {len(selected)} allowlisted source entries; no local data or credentials.')
    print('Target: ubuntu@192.168.15.42; bind192.168.15.42:8765; quota1GiB; reserve1GiB.')
    print('Only google-ads-assets.service will be installed/restarted. Existing services are untouched.')
    if not args.apply:
        print('Dry-run only. Use --apply after tests and deployment authorization.')
        return
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', 'ubuntu@192.168.15.42']
    subprocess.run(ssh + [f'test -x {BASE}/venv/bin/python && test "$(df --output=avail -B1 / | tail -1)" -gt 1800000000'], check=True)
    subprocess.run(ssh + [f"{BASE}/venv/bin/python -c 'import defusedxml, tinycss2'"], check=True)
    destination = BASE + '/releases/' + release
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode='w') as bundle:
            for name in selected:
                bundle.add(ROOT / name, arcname=name, filter=lambda entry: None if '__pycache__' in entry.name or entry.name.endswith('.pyc') else entry)
        archive.seek(0)
        subprocess.run(ssh + [f'umask 077; mkdir -p {destination}; tar -xf - -C {destination}'], stdin=archive, check=True)
    # This configuration contains no secrets. Existing environment configuration is preserved.
    config = '\n'.join(['ADS_DATA_DIR=' + BASE + '/data', 'ADS_QUOTA_BYTES=1073741824', 'ADS_RESERVE_BYTES=1073741824', 'ADS_COOKIE_SECURE=0', 'ADS_TRUSTED_HOSTS=192.168.15.42,127.0.0.1,localhost', 'STUDIO_BIND=192.168.15.42', 'STUDIO_PORT=8765', 'PYTHONDONTWRITEBYTECODE=1', ''])
    subprocess.run(ssh + [f'umask 077; if test ! -f {BASE}/service.env; then cat > {BASE}/service.env; else cat > /dev/null; fi'], input=config, text=True, check=True)
    command = f'''set -eu
{BASE}/venv/bin/python -m py_compile {destination}/app.py {destination}/background.py {destination}/svg_media.py {destination}/template_library.py {destination}/storage.py
cd {destination}
printf '%s  %s\\n' '309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8' 'models/u2netp.onnx' | sha256sum -c -
if test -L {BASE}/current; then readlink {BASE}/current > {BASE}/previous-release; fi
ln -sfn {destination} {BASE}/next
mv -Tf {BASE}/next {BASE}/current
sudo -n install -m 644 scripts/google-ads-assets.service /etc/systemd/system/google-ads-assets.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable google-ads-assets.service
sudo -n systemctl restart google-ads-assets.service
'''
    subprocess.run(ssh, input=command, text=True, check=True)
    print('Deployment started. Verify health/session and authorized browser journey before reporting complete.')
    print('Release path: ' + destination)


if __name__ == '__main__':
    main()
