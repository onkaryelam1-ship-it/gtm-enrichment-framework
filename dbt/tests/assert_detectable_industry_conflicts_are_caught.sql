-- Every planted industry conflict that the enrichment could reveal (a specific,
-- non-blank provider label) must be caught.
select *
from {{ ref('dq_planted_detail') }}
where expected_check = 'industry_conflict'
  and is_detectable
  and not was_caught
