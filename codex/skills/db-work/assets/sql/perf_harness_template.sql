-- =============================================================================
-- db-work bench harness template — Phase 5 variant benchmarking
--
-- Copy to:   util/<TICKET>/variants/<n>/perf.sql
-- Run via:   scripts/perf-bench.sh --spec util/<TICKET>/variants/bench_spec.json
--
-- Contract
-- --------
-- The harness must print exactly ONE trailing TSV line to the spool, with
-- KPI columns in the order declared in bench_spec.json.kpis. Default order:
--
--   elapsed_ms  consistent_gets  db_block_gets  sorts_memory  recursive_calls  plan_cost
--
-- perf-bench.sh picks the LAST line in the spool that matches a TSV of
-- numbers. Don't print other purely-numeric TSV lines after the result.
--
-- Required grants (one-time, on the DEV user running the harness):
--   GRANT SELECT ON SYS.V_$MYSTAT   TO <user>;
--   GRANT SELECT ON SYS.V_$STATNAME TO <user>;
--   GRANT SELECT ON SYS.V_$SQL      TO <user>;
--
-- How to fill this template
-- -------------------------
--   1. Pick ONE variant body below (A, B, C, or D) and delete the others.
--   2. Replace placeholders in {{DOUBLE_BRACES}} with concrete values.
--   3. Keep the /*+ db_work_perf_harness */ comment hint in your SQL — it lets
--      the harness identify the exact SQL_ID for plan_cost lookup.
--
-- Cache policy: WARM CACHE
-- -------------------------
--   This harness does NOT flush the buffer cache. perf-bench.sh runs the
--   harness --warmup times before measurement to populate the buffer cache,
--   warm the row cache, and hard-parse the SQL. Warmup invocations are
--   discarded; the trailing --runs invocations are recorded in bench_results.tsv.
--
--   If a plan requires cold-cache numbers (rare — production traffic is
--   warm-cache), add the line below ONCE inside the variant body and run with
--   --warmup 0. Requires DBA. Document the deviation in the plan.
--     execute immediate 'alter system flush buffer_cache';
--
-- Notes
-- -----
--   * v$mystat counters are session-scoped, so reads from the harness itself
--     contribute a small constant. That bias is symmetric across variants/runs
--     and does not affect comparison.
--   * Result cache can be bypassed for the session if the privilege exists:
--       execute dbms_result_cache.bypass(true);
-- =============================================================================

set serveroutput on size unlimited
set feedback off
set timing off
set verify off
set echo off

alter session set statistics_level = ALL;

declare
  -- ---------------------------------------------------------------------
  -- Helpers
  -- ---------------------------------------------------------------------
  function stat_value(p_name in varchar2) return number is
    v number;
  begin
    select ms.value
      into v
      from v$mystat   ms
      join v$statname sn on sn.statistic# = ms.statistic#
     where sn.name = p_name;
    return v;
  end;

  -- KPI accumulators
  v_consistent_gets_before number;
  v_db_block_gets_before   number;
  v_sorts_memory_before    number;
  v_recursive_calls_before number;

  v_consistent_gets_after  number;
  v_db_block_gets_after    number;
  v_sorts_memory_after     number;
  v_recursive_calls_after  number;

  v_t0_cs       number;
  v_t1_cs       number;
  v_elapsed_ms  number;
  v_plan_cost   number := -1;
  v_row_count   number := 0;
begin
  -- Pre-snapshot
  v_consistent_gets_before := stat_value('consistent gets');
  v_db_block_gets_before   := stat_value('db block gets');
  v_sorts_memory_before    := stat_value('sorts (memory)');
  v_recursive_calls_before := stat_value('recursive calls');

  v_t0_cs := dbms_utility.get_time;

  -- =====================================================================
  -- VARIANT BODY — pick ONE of A / B / C / D, delete the rest.
  -- =====================================================================

  -- ----- A. Table function variant -------------------------------------
  -- Use when the variant is a function returning a collection that the
  -- caller selects from with TABLE(...).
  for r in (
    select /*+ db_work_perf_harness */ *
      from table({{SHADOW_OBJECT}}.{{CALLABLE_NAME}}(
              {{ARG_NAME}} => {{ARG_VALUE}}
            ))
  ) loop
    v_row_count := v_row_count + 1;
  end loop;

  -- ----- B. Scalar function variant ------------------------------------
  -- Use when the variant returns a scalar value.
  -- declare
  --   v_result {{RETURN_TYPE}};
  -- begin
  --   for i in 1 .. {{ITERATIONS}} loop
  --     select /*+ db_work_perf_harness */ {{SHADOW_OBJECT}}.{{CALLABLE_NAME}}(
  --              {{ARG_NAME}} => {{ARG_VALUE}}
  --            )
  --       into v_result
  --       from dual;
  --     v_row_count := v_row_count + 1;
  --   end loop;
  -- end;

  -- ----- C. Procedure (side-effect) variant ----------------------------
  -- Use when the variant is a procedure. Wrap with setup/cleanup to keep
  -- runs comparable. Plan cost will reflect the worst-cost child SQL of
  -- the call (captured below by the harness comment hint inside the
  -- procedure's most expensive query, when annotated). If no harness-
  -- hinted SQL is found, plan_cost falls back to -1.
  -- {{SETUP_SQL}}
  -- {{SHADOW_OBJECT}}.{{CALLABLE_NAME}}(
  --   {{ARG_NAME}} => {{ARG_VALUE}}
  -- );
  -- v_row_count := sql%rowcount;
  -- {{CLEANUP_SQL}}

  -- ----- D. RefCursor variant ------------------------------------------
  -- Use when the variant returns or exposes a SYS_REFCURSOR. The harness
  -- MUST fetch the full cursor, not just open it — open-only timing is
  -- misleading.
  -- declare
  --   l_rc      sys_refcursor;
  --   l_buffer  {{ROW_TYPE}};
  -- begin
  --   l_rc := {{SHADOW_OBJECT}}.{{CALLABLE_NAME}}(
  --             {{ARG_NAME}} => {{ARG_VALUE}}
  --           );
  --   loop
  --     fetch l_rc into l_buffer;
  --     exit when l_rc%notfound;
  --     v_row_count := v_row_count + 1;
  --   end loop;
  --   close l_rc;
  -- end;

  -- =====================================================================
  -- END VARIANT BODY
  -- =====================================================================

  v_t1_cs := dbms_utility.get_time;
  v_elapsed_ms := (v_t1_cs - v_t0_cs) * 10;  -- centiseconds -> ms

  -- Post-snapshot
  v_consistent_gets_after  := stat_value('consistent gets');
  v_db_block_gets_after    := stat_value('db block gets');
  v_sorts_memory_after     := stat_value('sorts (memory)');
  v_recursive_calls_after  := stat_value('recursive calls');

  -- Plan cost: pick the optimizer cost of the most recently active SQL
  -- in this session that carries the db_work_perf_harness comment hint.
  begin
    select optimizer_cost
      into v_plan_cost
      from (
        select optimizer_cost
          from v$sql
         where sql_text like '%db_work_perf_harness%'
           and sql_text not like '%v$sql%'
         order by last_active_time desc
      )
     where rownum = 1;
  exception
    when no_data_found then
      v_plan_cost := -1;
  end;

  -- TSV trailing line. Field order MUST match bench_spec.json.kpis.
  dbms_output.put_line(
    v_elapsed_ms                                         || chr(9) ||
    (v_consistent_gets_after - v_consistent_gets_before) || chr(9) ||
    (v_db_block_gets_after   - v_db_block_gets_before)   || chr(9) ||
    (v_sorts_memory_after    - v_sorts_memory_before)    || chr(9) ||
    (v_recursive_calls_after - v_recursive_calls_before) || chr(9) ||
    v_plan_cost
  );

  -- Optional human-readable line for log inspection. NOT picked up by
  -- perf-bench.sh because it contains non-numeric tokens. Safe to keep.
  dbms_output.put_line(
    '-- harness ok: rows=' || v_row_count ||
    ' elapsed_ms=' || v_elapsed_ms ||
    ' plan_cost=' || v_plan_cost
  );
end;
/

exit
