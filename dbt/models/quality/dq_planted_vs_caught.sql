-- Recall per check: of the errors planted on purpose, how many did we catch?
select
    error_type,
    expected_check,
    count(*)                                            as planted,
    count(*) filter (where was_caught)                  as caught,
    count(*) filter (where not was_caught)              as missed,
    round(100.0 * count(*) filter (where was_caught) / count(*), 1) as recall_pct,
    -- for industry conflicts, recall over the ones the data could reveal at all
    count(*) filter (where coalesce(is_detectable, true))  as detectable,
    round(100.0 * count(*) filter (where was_caught)
          / nullif(count(*) filter (where coalesce(is_detectable, true)), 0), 1) as detectable_recall_pct
from {{ ref('dq_planted_detail') }}
group by 1, 2
order by recall_pct, error_type
