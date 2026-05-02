set define off
set echo on
set feedback on
set timing on
set serveroutput on size unlimited
whenever sqlerror exit sql.sqlcode rollback

spool logs/deploy_shadow.log

prompt Deploying generated DEV shadow objects

@@objects/example.sql

show errors

spool off
exit
