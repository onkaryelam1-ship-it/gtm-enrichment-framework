-- Every score part and the final priority must stay within 0-100.
select contact_id
from {{ ref('fct_prospect_scores') }}
where not (
    fit_score between 0 and 100 and role_score between 0 and 100
    and engagement_score between 0 and 100 and intent_score between 0 and 100
    and priority_score between 0 and 100
)
