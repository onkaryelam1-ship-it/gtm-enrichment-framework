{# Use the configured schema name as-is (staging, marts, ...) instead of dbt's
   default "<target>_<custom>" prefixing, so tables land in readable schemas. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
