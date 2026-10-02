with associations as (
    select distinct game_id, platform_id
    from {{ ref('int_game_platforms') }}
), metrics as (
    select
        associations.platform_id,
        count(*) as game_count,
        count(games.rating) as rated_game_count,
        avg(games.rating) as avg_rating,
        count(games.rating_count) as rating_count_game_count,
        sum(games.rating_count) as rating_count_sum
    from associations
    inner join {{ ref('stg_games') }} as games using (game_id)
    group by associations.platform_id
)

select
    metrics.platform_id,
    dimensions.name,
    metrics.game_count,
    metrics.rated_game_count,
    metrics.avg_rating,
    metrics.rating_count_game_count,
    metrics.rating_count_sum
from metrics
left join {{ ref('stg_platforms') }} as dimensions using (platform_id)
