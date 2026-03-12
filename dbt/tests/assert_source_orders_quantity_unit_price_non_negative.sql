{{config(
    severity='warn'
)}}

SELECT * FROM 
{{source("landing","orders")}}
where 
unit_price <  0 or quantity < 0
