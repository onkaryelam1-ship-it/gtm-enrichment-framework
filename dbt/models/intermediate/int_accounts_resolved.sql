-- Combine seed accounts with enrichment and resolve disagreements field by field.
--
-- Industry: providers return broad labels, our seed uses a finer 12-bucket taxonomy.
-- seeds/industry_mapping.csv maps each label to its compatible buckets.
--   * Generic labels ("Software Development", "IT Services...") are applied to
--     security, fintech and health companies alike, so they carry too little
--     information to contradict the seed: the seed is kept, no conflict.
--   * Specific labels ("Computer and Network Security", "Banking") are trusted:
--     if the seed bucket is not compatible, the enrichment wins and a conflict
--     is logged.
--
-- Country: the seed comes from a curated public list, so it wins; enrichment only
-- fills gaps. Disagreements are still logged for review.
with accounts as (
    select * from {{ ref('stg_accounts') }}
),

enrichment as (
    select * from {{ ref('stg_enrichment') }}
),

mapping as (
    select * from {{ ref('industry_mapping') }}
),

joined as (
    select
        a.*,
        e.account_id is not null                                       as has_enrichment,
        e.provider                                                     as enrichment_provider,
        e.enriched_at,
        e.is_stale_enrichment,
        e.industry_label,
        e.employee_count,
        e.hq_country                                                   as enriched_country,
        e.founded_year,
        e.size_band,
        e.size_min,
        e.size_max,
        e.description,
        e.matched_name,
        (select any_value(m.industry_bucket) from mapping m
          where m.provider_label = e.industry_label and m.is_primary)  as enriched_industry,
        exists (select 1 from mapping m
                 where m.provider_label = e.industry_label)            as label_is_mapped,
        coalesce((select bool_or(m.is_generic) from mapping m
                   where m.provider_label = e.industry_label), false)  as label_is_generic,
        exists (select 1 from mapping m
                 where m.provider_label = e.industry_label
                   and (m.industry_bucket = a.seed_industry or m.is_generic)) as seed_industry_compatible
    from accounts a
    left join enrichment e using (account_id)
)

select
    *,
    case
        when industry_label is null then seed_industry
        when not label_is_mapped then seed_industry
        when seed_industry_compatible then seed_industry
        else enriched_industry
    end                                                                as industry,
    case
        when not has_enrichment then 'seed_only_no_enrichment'
        when industry_label is null then 'seed_only_provider_blank'
        when not label_is_mapped then 'seed_kept_label_unmapped'
        when label_is_generic then 'seed_kept_generic_label'
        when seed_industry_compatible then 'seed_kept_compatible'
        else 'enrichment_overrides_conflict'
    end                                                                as industry_rule,
    industry_label is not null and label_is_mapped
        and not seed_industry_compatible                               as has_industry_conflict,
    coalesce(hq_country, enriched_country)                             as country,
    hq_country is not null and enriched_country is not null
        and hq_country <> enriched_country                             as has_country_conflict,
    -- Headcount vs the provider's own size band. Size bands are self-reported and
    -- lag reality, so being 2-10x outside the band is only a warning. Being 10x or
    -- more outside suggests the provider matched a different company altogether
    -- (a namesake or a small subsidiary).
    coalesce(
        employee_count < size_min / 10
        or (size_max is not null and employee_count > size_max * 10),
        false
    )                                                                  as is_suspected_wrong_entity,
    coalesce(
        (employee_count < size_min / 2 or (size_max is not null and employee_count > size_max * 2))
        and not (employee_count < size_min / 10 or (size_max is not null and employee_count > size_max * 10)),
        false
    )                                                                  as has_headcount_band_mismatch
from joined
