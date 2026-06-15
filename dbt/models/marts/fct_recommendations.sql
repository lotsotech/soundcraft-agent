-- Fact table capturing every agent recommendation event and SE handoff
-- Powers the ops dashboard: conversion tracking, SE workload, agent quality

with handoffs as (
    select * from read_csv_auto('{{ env_var("SOUNDCRAFT_DATA_PATH", "../../data/raw") }}/se_handoffs.csv')
)

select
    handoff_id,
    session_id,
    json(customer_snapshot)                         as customer_snapshot,
    json(recommended_products)                      as recommended_products,
    conversation_summary,
    priority,
    cast(created_at as timestamp)                   as created_at,
    assigned_se
from handoffs
