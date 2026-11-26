# Windows installer

Place `Clipwise-Setup-1.3.0.exe` here before `npm run build`.

The build copies this folder into `web/dist/downloads/`, so the landing page link
`/downloads/Clipwise-Setup-1.3.0.exe` works from the public origin. The executable
is intentionally gitignored because it is a large binary; copy it from
`desktop/dist/installer/` after building the desktop bundle or from the release
artifact on the deployment machine.

The desktop build deliberately excludes `web/dist/downloads/` from the packaged
app, so the installer is never nested inside itself. `verify_bundle.py` skips
this folder for the same reason.
