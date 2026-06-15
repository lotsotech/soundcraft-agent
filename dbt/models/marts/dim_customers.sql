with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
),

customer_stats as (
    select
        customer_id,
        count(distinct order_id)                    as total_orders,
        sum(line_total)                             as lifetime_value,
        max(order_date)                             as last_order_date,
        min(order_date)                             as first_order_date,
        array_agg(distinct product_id)              as purchased_product_ids
    from orders
    group by customer_id
),

final as (
    select
        c.customer_id,
        c.full_name,
        c.email,
        c.skill_level,
        c.primary_instrument,
        c.years_playing,
        c.use_case,
        c.budget_range,
        c.created_at,
        coalesce(cs.total_orders, 0)                as total_orders,
        coalesce(cs.lifetime_value, 0)              as lifetime_value,
        cs.last_order_date,
        cs.first_order_date,
        coalesce(cs.purchased_product_ids, [])      as purchased_product_ids
    from customers c
    left join customer_stats cs using (customer_id)
)

select * from final
