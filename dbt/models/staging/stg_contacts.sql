-- One row per raw contact (duplicates still present), with normalized email and
-- title parsed into seniority and department.
with base as (
    select
        contact_id,
        account_id,
        trim(first_name)                                       as first_name,
        trim(last_name)                                        as last_name,
        email                                                  as email_raw,
        lower(trim(email))                                     as email,
        nullif(trim(title), '')                                as title_raw,
        cast(source_updated_at as date)                        as source_updated_at
    from {{ source('raw', 'raw_contacts') }}
),

titles as (
    select
        *,
        -- expand the abbreviations seen in the source so rules below stay simple
        nullif(trim(
            replace(replace(replace(regexp_replace(title_raw, '\s+', ' ', 'g'),
                'Sr.', 'Senior'), 'Dir.', 'Director of'), 'VP, ', 'VP of ')
        ), '') as title_clean
    from base
),

parsed as (
    select
        *,
        lower(title_clean) as t,
        -- title case, with the few acronyms fixed up ("vp of data" -> "VP of Data")
        replace(replace(replace(replace(
            array_to_string(
                list_transform(string_split(lower(title_clean), ' '), w -> upper(w[1]) || w[2:]),
                ' '),
            'Vp ', 'VP '), ' Of ', ' of '), 'Revops', 'RevOps'), ' And ', ' and ') as title_standard
    from titles
)

select
    contact_id,
    account_id,
    first_name,
    last_name,
    first_name || ' ' || last_name                             as full_name,
    email_raw,
    email,
    regexp_full_match(
        email, '^[a-z0-9_%+-]+(\.[a-z0-9_%+-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$'
    )                                                          as is_valid_email,
    title_raw,
    title_standard                                             as title,
    case
        when t is null then null
        when t like 'chief %' or t like '% officer' then 'C-level'
        when t like 'vp%' or t like 'vice president%' then 'VP'
        when t like 'director%' or t like 'head of%' then 'Director'
        when t like '%manager%' then 'Manager'
        else 'IC'
    end                                                        as seniority,
    case
        when t is null then null
        when t like '%revenue operations%' or t like '%revops%' or t like '%sales operations%' then 'RevOps'
        when t like '%financ%' then 'Finance'
        when t like '%operat%' then 'Operations'
        when t like '%data%' or t like '%analytics%' then 'Data'
        when t like '%engineer%' or t like '%technology%' then 'Engineering'
        when t like '%sales%' or t like '%account executive%' or t like '%revenue%' then 'Sales'
        when t like '%market%' or t like '%growth%' then 'Marketing'
    end                                                        as department,
    source_updated_at,
    date_diff('day', source_updated_at, date '{{ var("reference_date") }}')
        > {{ var('stale_contact_days') }}                      as is_stale
from parsed
