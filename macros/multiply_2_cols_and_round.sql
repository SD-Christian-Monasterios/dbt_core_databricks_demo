{% macro multiply_columns_and_round(col1,col2, decimal_places = 2)  -%}
   round({{ col1 }} * {{ col2 }}, {{decimal_places}})
{%- endmacro %}