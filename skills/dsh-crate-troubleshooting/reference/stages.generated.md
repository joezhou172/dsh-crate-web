# DSH Crate Diagnostic Stages

> Generated from `core/dsh_pack/diagnostics.py` (schema v1). Do not edit by hand.

| Stage | Title | Description | Import state |
| --- | --- | --- | --- |
| commit | Commit | Committing the prepared Profile and metadata as a successful Import. | commit |
| composition | Bundle composition | Composing Bundle patches and Loader rows for the Profile. | composition |
| configuration | Configuration | Writing Pack profile configuration into the target Profile. | configuration |
| delete | Delete | Deleting a non-running Profile after explicit confirmation. | delete |
| embedded-install | Embedded install | Installing an embedded plugin artifact (npm tarball) into the temporary Profile. | embedded-install |
| environment | Environment | Environment compatibility findings (OS, Node, DSH versions). | environment |
| network-install | Network install | Downloading and installing a recorded network package. | network-install |
| planning | Plan | Operation planning: target Profile selection, name validation, pack read, and Import preview. | planning |
| plugin-smoke | Plugin smoke | Running a plugin-specific smoke test against the runtime. | plugin-smoke |
| preflight | Preflight | Read-only Inspect/Preflight of a Pack before any Profile change. | preflight |
| probe | Probe | Running a runtime capability probe after boot. | probe |
| reference-install | Reference install | Installing or resolving a reference-only plugin source. | reference-install |
| restart | Restart | Restarting DSH on the target Profile and port. | restart |
| runtime | Runtime boot | Starting the DSH runtime and waiting for a ready URL. | runtime |
| surface | Surface | Web surface or Bundle composition surface checks. | surface |
| version-confirmation | Version confirmation | Confirming the installed package identity matches the Pack resolution. | version-confirmation |
