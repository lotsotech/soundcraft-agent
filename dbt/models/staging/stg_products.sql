with source as (
    select * from read_csv_auto('{{ env_var("SOUNDCRAFT_DATA_PATH", "../../data/raw") }}/products.csv')
),

renamed as (
    select
        product_id,
        name                                        as product_name,
        brand,
        category,
        subcategory,
        cast(price as decimal(10,2))                as price,
        description,
        skill_level,
        use_case,
        cast(in_stock as boolean)                   as in_stock,
        manufacturer_url
    from source
)

select * from renamed
