{#
  Standard dbt override: a custom schema config (+schema: gold) should mean exactly
  that schema, not "<target_schema>_gold" (dbt's default concatenation behavior).
  Lets staging/intermediate/marts land in staging/silver/gold directly, matching the
  schema names the Phase 1 hand-written SQL already used — so dbt takes over the
  same three schemas rather than introducing a fourth naming scheme.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
