with associations as (
    select distinct game_id, genre_id
    from {{ ref('int_game_genres') }}
), metrics as (
    select
        associations.genre_id,
        count(*) as game_count,
        count(games.rating) as rated_game_count,
        avg(games.rating) as avg_rating,
        count(games.rating_count) as rating_count_game_count,
        sum(games.rating_count) as rating_count_sum
    from associations
    inner join {{ ref('stg_games') }} as games using (game_id)
    group by associations.genre_id
)

select
    metrics.genre_id,
    dimensions.name,
    metrics.game_count,
    metrics.rated_game_count,
    metrics.avg_rating,
    metrics.rating_count_game_count,
    metrics.rating_count_sum
from metrics
left join {{ ref('stg_genres') }} as dimensions using (genre_id)
