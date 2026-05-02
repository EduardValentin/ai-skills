# SQLPlus DEV Execution

Use Oracle Secure External Password Store (SEPS) for DEV execution. The skill should never ask the user to paste a database password into chat.

Oracle deprecates `mkstore` in newer database documentation, but `db-work` uses `mkstore` deliberately because it is a leaner, automatable macOS ARM setup path than requiring a full Oracle Database Client just to create a local DEV wallet.

Sources:

- <https://www.oracle.com/database/technologies/instant-client/macos-arm64-downloads.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/mxcli/index.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/configuring-authentication.html>
- <https://docs.oracle.com/en/database/oracle/oracle-database/26/netrf/parameters-for-the-sqlnet.ora.html>

## Expected Runtime

Before running DEV SQL, `scripts/run_sqlplus_dev.sh` checks whether `sqlplus` is available or discoverable in common Oracle client locations. If it is missing, the wrapper calls `scripts/ensure_sqlplus.sh`.

Automatic SQLPlus installation is intentionally minimal:

- macOS: installs Oracle Instant Client Basic and SQL*Plus using Oracle's official DMG package flow.
- Other platforms: prints manual installation guidance.

Set `DB_WORK_AUTO_INSTALL_SQLPLUS=0` to disable automatic installation.

Wallet setup needs `mkstore`. The wallet setup script calls `scripts/ensure_sqlplus.sh --wallet-tools` before it creates wallet files.

Best toolchain split:

- runtime DEV SQL execution on macOS ARM: Oracle Instant Client Basic plus SQL*Plus;
- wallet creation/update: `mkstore` from the lean Java wallet utility launcher installed by the skill.

Automatic `mkstore` setup needs:

- Java on `PATH`;
- `curl` on `PATH`;
- network access to Maven Central.

Do not put credentials in `.db-work.yml`; use only non-secret local environment variables or config values. By default, `.db-work.yml` should live in the temporary db-work session directory created by `scripts/start_session.sh`, not in the Oracode repo.

The execution script expects either:

```bash
export DB_WORK_DEV_CONNECT='/@DEVDB_ALIAS'
```

or this non-secret value in the temp `.db-work.yml`:

```yaml
dev_connect: /@DEVDB_ALIAS
```

The alias should clearly identify DEV, for example `DEVDB_ALIAS`, `ORACODE_DEV`, or a team-approved equivalent.

## Create An Oracle Wallet

The agent should create the wallet configuration for the user after required CLI tools are available. Do not leave the user to manually create folders, write `sqlnet.ora`, or run `mkstore` commands by hand unless the setup script cannot proceed.

The only user interaction should be local terminal prompts for secret values. Do not ask for database passwords in chat.

1. Verify or install only the required tools.

The agent may run:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/ensure_sqlplus.sh" --wallet-tools
```

If `mkstore` is missing, the script installs it by downloading Oracle's database security jar to `~/.oracle/mkstore/lib` and creating a local launcher under `~/.oracle/mkstore/bin`. `mkstore` is needed only for creating, listing, or updating the wallet. It is not needed for normal SQLPlus script execution once the wallet exists.

2. Gather non-secret connection details.

The agent may ask for:

- DEV TNS alias, for example `ORACODE_DEV`;
- non-secret TNS descriptor if the alias is not already present in `tnsnames.ora`.

Do not ask for the database password in chat.

3. Run the setup script.

If the alias already exists in `tnsnames.ora`:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/setup_oracle_wallet.sh" \
  --alias DEVDB_ALIAS
```

If the alias is not present and the user provides a non-secret descriptor:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/setup_oracle_wallet.sh" \
  --alias DEVDB_ALIAS \
  --tns-descriptor '(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=dev-host.example.com)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=dev_service)))'
```

The script creates the local Oracle folders, updates `tnsnames.ora` when a descriptor is provided, writes a managed `WALLET_LOCATION` plus `SQLNET.WALLET_OVERRIDE = TRUE` block to `sqlnet.ora`, creates the auto-login wallet, creates the credential with `mkstore -createCredential`, and tests `sqlplus -L /@DEVDB_ALIAS`.

The user responds only to local terminal prompts for secret values, such as database username/password and any wallet password requested by Oracle.

4. Confirm the generated connection.

The script prints the non-secret `DB_WORK_DEV_CONNECT=/@DEVDB_ALIAS` value when setup succeeds.

5. Configure `db-work`.

Prefer an environment variable:

```bash
export DB_WORK_DEV_CONNECT='/@DEVDB_ALIAS'
```

Or add the non-secret alias to the temp `.db-work.yml`:

```yaml
dev_connect: /@DEVDB_ALIAS
```

## Execute A Generated Script

From the Oracode repo root:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/run_sqlplus_dev.sh" \
  --script util/VA-515/dev_sandbox/deploy_shadow.sql
```

To pass the alias directly:

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/db-work/scripts/run_sqlplus_dev.sh" \
  --connect /@DEVDB_ALIAS \
  --script util/VA-515/dev_sandbox/deploy_shadow.sql
```

## Troubleshooting

- If SQLPlus cannot resolve the alias, check `TNS_ADMIN` and `tnsnames.ora`.
- If SQLPlus prompts for a password, check `sqlnet.ora`, `WALLET_LOCATION`, `SQLNET.WALLET_OVERRIDE`, and whether the wallet connect string exactly matches the TNS alias.
- If `mkstore -listCredential` works but SQLPlus does not, the active SQLPlus process may be using a different `TNS_ADMIN`.
- If the skill refuses to execute, confirm the alias contains `DEV` or set `DB_WORK_ALLOW_NON_DEV=1` only after confirming the target is safe.
