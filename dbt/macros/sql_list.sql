{# Render a list var as a SQL IN-list: ('a', 'b') #}
{% macro sql_list(values) -%}
    ({% for v in values %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
{%- endmacro %}
