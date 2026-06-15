with source as (
    select * from read_csv_auto('{{ env_var("SOUNDCRAFT_DATA_PATH", "../../data/raw") }}/orders.csv')
),

renamed as (
    select
        order_id,
        customer_id,
        product_id,
        cast(quantity as integer)                   as quantity,
        cast(unit_price as decimal(10,2))           as unit_price,
        quantity * unit_price                       as line_total,
        cast(order_date as date)                    as order_date,
        status
    from source
)

select * from renamed
