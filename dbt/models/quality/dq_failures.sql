-- Every failed check, one row per (check, record). This is the quarantine / work
-- queue: `action` says what happens to the record.
with contacts as (select * from {{ ref('int_contacts_deduped') }}),
     accounts as (select * from {{ ref('int_accounts_resolved') }}),
     known_accounts as (select account_id from {{ ref('stg_accounts') }})

-- contacts ------------------------------------------------------------------
select 'invalid_email' as check_name, 'contact' as entity, contact_id as record_id,
       'error' as severity, 'quarantine' as action, email_raw as detail
from contacts where not is_valid_email

union all
select 'orphan_contact', 'contact', contact_id, 'error', 'quarantine', account_id
from contacts where account_id not in (select account_id from known_accounts)

union all
select 'duplicate_contact', 'contact', contact_id, 'warn', 'merge',
       'merged into ' || survivor_contact_id
from contacts where not is_survivor

union all
select 'possible_duplicate', 'contact', contact_id, 'warn', 'review',
       'similar to ' || possible_duplicate_of
from contacts where possible_duplicate_of is not null

union all
select 'missing_title', 'contact', contact_id, 'warn', 'flag', null
from contacts where title is null

union all
select 'unmapped_title', 'contact', contact_id, 'warn', 'flag', title
from contacts where title is not null and (seniority is null or department is null)

union all
select 'stale_contact', 'contact', contact_id, 'warn', 'refresh',
       cast(source_updated_at as varchar)
from contacts where is_stale

-- accounts ------------------------------------------------------------------
union all
select 'missing_enrichment', 'account', account_id, 'warn', 'queue_for_enrichment', domain
from accounts where not has_enrichment

union all
select 'stale_enrichment', 'account', account_id, 'warn', 're_enrich',
       cast(enriched_at as varchar)
from accounts where is_stale_enrichment

union all
select 'missing_industry', 'account', account_id, 'warn', 'flag', enrichment_provider
from accounts where has_enrichment and industry_label is null

union all
select 'missing_employee_count', 'account', account_id, 'warn', 'flag', enrichment_provider
from accounts where has_enrichment and employee_count is null

union all
select 'unmapped_industry_label', 'account', account_id, 'warn', 'add_mapping', industry_label
from accounts where industry_label is not null and not label_is_mapped

union all
select 'industry_conflict', 'account', account_id, 'warn', 'resolved_by_rule',
       seed_industry || ' vs ' || industry_label
from accounts where has_industry_conflict

union all
select 'country_conflict', 'account', account_id, 'warn', 'resolved_by_rule',
       hq_country || ' vs ' || enriched_country
from accounts where has_country_conflict

union all
select 'suspected_wrong_entity', 'account', account_id, 'error', 'review',
       coalesce(matched_name, company_name) || ': ' || employee_count || ' employees vs "' || size_band || '"'
from accounts where is_suspected_wrong_entity

union all
select 'headcount_band_mismatch', 'account', account_id, 'warn', 'flag',
       employee_count || ' employees vs "' || size_band || '"'
from accounts where has_headcount_band_mismatch
