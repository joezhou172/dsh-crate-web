# `dsh-crate-web`

DSH Web Settings surface for the DSH Crate Core. It provides:

- Settings → DSH Crate → Export;
- Settings → DSH Crate → Import, with Preflight before confirmation;
- Settings → DSH Crate → Inspect;
- Settings → DSH Crate → Verify;
- Settings → DSH Crate → History.

The browser half does not implement Crate schema, integrity, Preflight, or
Import. It sends a small JSON request to the host half. The published plugin
package runs its bundled Core source through its bundled Windows Python
runtime, so the normal installation path needs no environment-variable setup
or system Python. Set `DSH_PACK_CLI` (and, when needed, `DSH_PACK_CLI_PREFIX`)
only to override Core discovery in a development or controlled deployment
environment.

On non-Windows development environments, or when a development build omits the
runtime directory, the bridge falls back to `dsh-crate`, `python`, `python3`, or
Windows `py`. The Core remains the same Python implementation used by the CLI;
the plugin does not reimplement Crate business rules in JavaScript.
The bridge sets `DSH_PACK_CORE_MODE=1` for this child process so an installed
user-facing console script still returns the raw Core JSON contract.

Import defaults to a user-named new Profile and rejects duplicate names. The
UI also lets the user select an existing Profile for replacement, but only
after a confirmation popup; Core additionally requires the explicit
`OVERWRITE` confirmation token. A separate Delete Profile action likewise
requires a confirmation popup and the Core `DELETE` token. Merge remains
unsupported, and Secret values are never persisted. Import preview and the
Verify page render Core-owned decisions and statuses.
The page also has a visible Profile management area: it reports the currently
running Profile, exposes Delete directly, and provides an explicit “Switch and
restart Profile” action. Switching stops the current DSH process, starts the
selected Profile, and reports HTTP readiness; importing a Pack never switches
the running Profile automatically. The active Profile cannot be deleted.
Structured Core failure diagnostics remain available in the page for viewing
and copying; the browser does not reduce them to a plain error message.
When a reference-only package is not available in the current DSH_HOME, Core
can fall back to npm for recorded registry, GitHub/Git, tarball, and alias
sources. The download happens only during formal Import, inside the temporary
Profile, with lifecycle scripts disabled. Inspect and dry-run remain read-only;
use the Core/CLI `--offline` option to disable this fallback.

## Model Experience

None. DSH Crate is an environment-management surface and does not add model
tools or alter model requests.

## Install / compose

The normal user installation is from the npm registry through the official DSH
plugin command:

```powershell
dsh plugin --profile web add dsh-crate-web@0.1.0
```

This installs the package into the selected DSH Profile and lets DSH reconcile
the declared Bundle. Restart DSH and open Settings → DSH Crate.

For local development, offline testing, or a private build, the same package
can still be installed from a local directory or tarball:

```powershell
# From the repository root
dsh plugin --profile web add .\plugins\dsh-crate-web

# From a packed artifact
dsh plugin --profile web add .\dsh-crate-web-0.1.0.tgz
```

Do not use a global `npm install`: the package must be installed inside the
target DSH Profile so DSH can resolve its Bundle and host/browser faces.
