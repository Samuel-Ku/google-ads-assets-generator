# Deployment / operations

For the repeatable operator procedure, see the [Ukrainian deployment runbook](docs/operations/deployment-runbook-uk.md). This file remains the concise English summary.

The user approved deployment to Ubuntu 192.168.15.42 after reviewing SPEC.md. This app is isolated from existing services, uses CPU only, renders assets in the browser and makes no paid API requests.

## Layout

- `/home/ubuntu/google-ads-assets/releases/<release>`: immutable application sources/model.
- `/home/ubuntu/google-ads-assets/current`: current release symlink.
- `/home/ubuntu/google-ads-assets/venv`: isolated pinned Python environment.
- `/home/ubuntu/google-ads-assets/data`: private SQLite, session secret and media (mode 700).
- `/home/ubuntu/google-ads-assets/service.env`: private runtime configuration (mode 600).
- `google-ads-assets.service`: single-process Waitress. Existing nginx and other services are not modified.

## Preflight and release

1. Confirm free disk, free listening port, package compatibility and background model checksum. Keep at least 1 GiB free for the OS/other apps.
2. Install requirements in the isolated venv with `pip --no-cache-dir`. Never install into system Python.
3. Run backend tests and browser acceptance locally. Create an allowlisted release archive, excluding development data and credentials.
4. Extract into a new release directory, check model SHA256, run a CPU inference smoke check.
5. Configure storage quota of 1 GiB and reserve of 1 GiB. Create first admin via CLI with a private password file; remove bootstrap password file afterwards. Share credentials only in a private local access note.
6. Switch `current` symlink to the tested release; install/restart only this service.
7. Check service health, login, protected assets, create/save campaign, background removal and ZIP export through browser. Verify free space and service memory.

The service binds only the private VM address, port 8765. Access is intended for office LAN / corporate VPN. This internal URL uses HTTP; do not expose or port-forward it publicly. A trusted internal HTTPS hostname/reverse proxy can be configured later with the network administrator. No existing TLS/domain setup is altered.

## Recovery / rollback

For a failed first deployment: `sudo systemctl stop google-ads-assets` and investigate logs with `sudo journalctl -u google-ads-assets -n 80 --no-pager`. This has no effect on other services.

For a later release: stop the service, point `current` back to the previous release, start and verify. Take a consistent SQLite backup before any schema migration. The editor extension adds `jobs.method` with default `smart` when absent; existing rows and data are preserved, and older releases ignore this additional column. The template library adds an independent `shared_templates` table; older code ignores it. Future migrations still require a consistent pre-migration backup. Keep at most one prior source release to bound disk use.

Retain data during code rollback. Do not remove or reset the data directory to fix a release. Credentials/session secrets must survive restart.

## Retention

Uploaded campaign media and ZIP exports expire after 7 days. Brand assets and campaign text/history persist and count toward limits. Cleanup touches only app-owned records/files. Changing a text does not silently extend retention. The app rejects work when quota/free-space reserve would be exceeded. No automatic cleanup of other VM directories.

Media backups are not configured in this pilot. Download final ZIPs within the displayed retention window; move persistent backups to a separate approved storage location if later required. Do not accumulate backups on the almost-full system disk.

Current release: `/home/ubuntu/google-ads-assets/releases/20260921-150038`. Detailed verification: [reports/template-library-verification-2026-09-21.md](reports/template-library-verification-2026-09-21.md).
