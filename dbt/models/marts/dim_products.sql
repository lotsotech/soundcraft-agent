with products as (
    select * from {{ ref('stg_products') }}
),

enriched as (
    select
        product_id,
        product_name,
        brand,
        category,
        subcategory,
        price,
        description,
        skill_level,
        use_case,
        in_stock,

        -- budget tier bucketing for agent filtering
        case
            when price < 100        then 'budget'
            when price < 500        then 'entry'
            when price < 1500       then 'mid-range'
            else                         'premium'
        end                                         as price_tier,

        -- denormalized skill array for overlap matching
        string_split(skill_level, '-')              as skill_levels_array
    from products
)

select * from enriched
