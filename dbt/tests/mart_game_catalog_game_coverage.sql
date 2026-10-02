with missing_games as (
    select game_id from {{ ref('stg_games') }}
    except
    select game_id from {{ ref('mart_game_catalog') }}
),

extra_games as (
    select game_id from {{ ref('mart_game_catalog') }}
    except
    select game_id from {{ ref('stg_games') }}
)

select game_id from missing_games
union all
select game_id from extra_games
