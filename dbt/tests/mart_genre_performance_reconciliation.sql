with associations as (
    select game_id, genre_id
    from {{ ref('int_game_genres') }}
), observed_dimensions as (
    select distinct genre_id from associations
), expected_metrics as (
    select
        dimensions.genre_id,
        count(*) as game_count,
        count(games.rating) as rated_game_count,
        avg(games.rating) as avg_rating,
        count(games.rating_count) as rating_count_game_count,
        sum(games.rating_count) as rating_count_sum
    from observed_dimensions as dimensions
    inner join {{ ref('stg_games') }} as games on exists (
        select 1 from associations
        where associations.genre_id = dimensions.genre_id
            and associations.game_id = games.game_id
    )
    group by dimensions.genre_id
), expected as (
    select metrics.*, dimensions.name
    from expected_metrics as metrics
    left join {{ ref('stg_genres') }} as dimensions using (genre_id)
)

select expected.genre_id as expected_id, actual.genre_id as actual_id
from expected
full outer join {{ ref('mart_genre_performance') }} as actual using (genre_id)
where expected.genre_id is null
    or actual.genre_id is null
    or expected.name is distinct from actual.name
    or expected.game_count is distinct from actual.game_count
    or expected.rated_game_count is distinct from actual.rated_game_count
    or expected.avg_rating is distinct from actual.avg_rating
    or expected.rating_count_game_count is distinct from actual.rating_count_game_count
    or expected.rating_count_sum is distinct from actual.rating_count_sum
