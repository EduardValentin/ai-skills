set define off
set feedback on
set timing on
set autotrace traceonly statistics

prompt ORIGINAL query

select *
from table(ORIGINAL_PACKAGE.some_function());

prompt SHADOW query

select *
from table(SHADOW_PACKAGE.some_function());

set autotrace off
exit
