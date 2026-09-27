-- Pivot the long enrichment table to one row per account (latest enrichment wins
-- if an account was enriched more than once) and cast values to proper types.
with pivoted as (
    select
        record_id                                                          as account_id,
        provider,
        source_file,
        cast(enriched_at as date)                                          as enriched_at,
        max(value) filter (where field = 'industry')                       as industry_label,
        max(value) filter (where field = 'employee_count')                 as employee_count_raw,
        max(value) filter (where field = 'hq_country')                     as hq_country,
        max(value) filter (where field = 'founded_year')                   as founded_year_raw,
        max(value) filter (where field = 'size_band')                      as size_band,
        max(value) filter (where field = 'description')                    as description,
        max(value) filter (where field = 'matched_name')                   as matched_name
    from {{ source('raw', 'raw_clay_enrichment') }}
    where record_id is not null
    group by all
),

latest as (
    select *
    from pivoted
    qualify row_number() over (partition by account_id order by enriched_at desc, provider) = 1
)

select
    account_id,
    provider,
    source_file,
    enriched_at,
    date_diff('day', enriched_at, date '{{ var("reference_date") }}')
        > {{ var('stale_enrichment_days') }}                               as is_stale_enrichment,
    industry_label,
    try_cast(try_cast(employee_count_raw as double) as integer)            as employee_count,
    upper(trim(hq_country))                                                as hq_country,
    try_cast(try_cast(founded_year_raw as double) as integer)              as founded_year,
    size_band,
    -- "1,001-5,000 employees" -> 1001 / 5000 ; "10,001+ employees" -> 10001 / null
    try_cast(replace(regexp_extract(size_band, '^([0-9,]+)', 1), ',', '') as integer) as size_min,
    try_cast(replace(regexp_extract(size_band, '-([0-9,]+)', 1), ',', '') as integer) as size_max,
    description,
    matched_name
from latest
