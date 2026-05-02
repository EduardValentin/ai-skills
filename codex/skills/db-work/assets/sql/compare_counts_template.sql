set define off
set feedback on
set timing on

/*
Replace both query bodies with equivalent original and shadow calls.
*/

with original_result as (
    select *
    from table(ORIGINAL_PACKAGE.some_function())
),
shadow_result as (
    select *
    from table(SHADOW_PACKAGE.some_function())
)
select 'ORIGINAL' as source_name, count(*) as row_count from original_result
union all
select 'SHADOW' as source_name, count(*) as row_count from shadow_result;

/*
Optional difference checks when result columns are comparable.
*/

with original_result as (
    select *
    from table(ORIGINAL_PACKAGE.some_function())
),
shadow_result as (
    select *
    from table(SHADOW_PACKAGE.some_function())
)
select 'ORIGINAL_MINUS_SHADOW' as diff_name, count(*) as diff_count
from (
    select * from original_result
    minus
    select * from shadow_result
)
union all
select 'SHADOW_MINUS_ORIGINAL' as diff_name, count(*) as diff_count
from (
    select * from shadow_result
    minus
    select * from original_result
);
