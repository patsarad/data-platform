with observed as (
    select
        relationships.*,
        exists (
            select 1 from {{ ref('stg_games') }} as games
            where games.game_id = relationships.game_id
        ) as game_loaded
    from {{ ref('int_game_companies') }} as relationships
    where relationships.company_id is not null
), output as (
    select
        company_id,
        count(*) as relationship_record_count,
        count(*) filter (where game_id is null) as null_game_relationship_count,
        count(distinct game_id) as game_count,
        count(distinct game_id) filter (where game_loaded) as loaded_game_count,
        count(distinct game_id) filter (where developer is true) as developer_game_count,
        count(distinct game_id) filter (where publisher is true) as publisher_game_count
    from observed
    group by company_id
)
select
    output.company_id,
    companies.name,
    companies.company_id is not null as company_loaded,
    output.relationship_record_count,
    output.null_game_relationship_count,
    output.game_count,
    output.loaded_game_count,
    output.developer_game_count,
    output.publisher_game_count
from output
left join {{ ref('stg_companies') }} as companies using (company_id)
