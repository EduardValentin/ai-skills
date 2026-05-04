-- One-time grants for the bench harness on the DEV user that runs perf.sql.
-- Run as a privileged DEV admin (or SYS).
--
--   "$DB_WORK_SKILL_DIR/scripts/run_sqlplus_dev.sh" \
--     --connect /@DEVDB_ADMIN_ALIAS \
--     --script "$DB_WORK_SKILL_DIR/assets/sql/perf_harness_grants.sql"
--
-- Replace YE_DEV with the actual DEV user when the grantee differs.

grant select on sys.v_$mystat   to ye_dev;
grant select on sys.v_$statname to ye_dev;
grant select on sys.v_$sql      to ye_dev;

exit
