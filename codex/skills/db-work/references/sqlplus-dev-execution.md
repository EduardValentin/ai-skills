# SQLPlus DEV Execution

Machine setup is in `references/01-machine-setup.md`. Run `db-work-doctor.sh` first.

## Connect string

Use Oracle Secure External Password Store (SEPS): `/@DEVDB_ALIAS`. Never paste passwords in chat or store them in `.db-work.yml`.

```bash
export DB_WORK_DEV_CONNECT='/@DEVDB_ALIAS'
```

Or in the temp `.db-work.yml`:

```yaml
dev_connect: /@DEVDB_ALIAS
```

## Execute a generated script

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
  --script util/VA-515/dev_sandbox/deploy_shadow.sql

# or with explicit alias:
"$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
  --connect /@DEVDB_ALIAS \
  --script util/VA-515/dev_sandbox/deploy_shadow.sql
```

## Why mkstore (deprecated by Oracle)

`mkstore` is deprecated upstream but `db-work` uses it deliberately: it gives a leaner, automatable macOS ARM wallet path than installing a full Oracle Database Client. `ensure_sqlplus.sh --wallet-tools` installs a tiny Java launcher for `mkstore`.

## Troubleshooting

- "TNS could not resolve…" → check `TNS_ADMIN` and that `tnsnames.ora` contains the alias.
- SQLPlus prompts for a password → check `sqlnet.ora`'s `WALLET_LOCATION` and `SQLNET.WALLET_OVERRIDE = TRUE`, and that the credential matches the alias exactly.
- `mkstore -listCredential` works but SQLPlus does not → another `TNS_ADMIN` is winning. Inspect `env | grep -i ORACLE` and `env | grep TNS_ADMIN`.

## Sources

- <https://www.oracle.com/database/technologies/instant-client/macos-arm64-downloads.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/mxcli/index.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/configuring-authentication.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/netrf/parameters-for-the-sqlnet.ora.html>
