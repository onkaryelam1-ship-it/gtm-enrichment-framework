-- Rule-based checks (format, completeness, freshness, referential, exact dedup)
-- must catch 100% of the errors planted for them. Returns the misses.
-- Industry conflicts are excluded on purpose: broad provider labels make some
-- planted conflicts undetectable, and that recall is reported, not asserted.
select *
from {{ ref('dq_planted_detail') }}
where expected_check <> 'industry_conflict'
  and not was_caught
