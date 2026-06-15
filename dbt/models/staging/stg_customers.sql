with source as (
    select * from read_csv_auto('{{ env_var("SOUNDCRAFT_DATA_PATH", "../../data/raw") }}/customers.csv')
),

renamed as (
    select
        customer_id,
        first_name,
        last_name,
        first_name || ' ' || last_name              as full_name,
        email,
        skill_level,
        primary_instrument,
        cast(years_playing as integer)              as years_playing,
        use_case,
        budget_range,
        cast(created_at as date)                    as created_at
    from source
)

select * from renamed
