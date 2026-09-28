-- The four weights must add up to 1 so the priority stays on a 0-100 scale.
select 1
where abs({{ var('w_fit') }} + {{ var('w_role') }} + {{ var('w_engagement') }} + {{ var('w_intent') }} - 1) > 0.0001
