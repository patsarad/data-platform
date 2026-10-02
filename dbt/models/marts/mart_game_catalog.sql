with genres as (
    select
        relationships.game_id,
        jsonb_agg(
            jsonb_build_object('genre_id', relationships.genre_id, 'name', genres.name)
            order by relationships.genre_id
        ) as observed_genres
    from {{ ref('int_game_genres') }} as relationships
    left join {{ ref('stg_genres') }} as genres using (genre_id)
    group by relationships.game_id
),

platforms as (
    select
        relationships.game_id,
        jsonb_agg(
            jsonb_build_object('platform_id', relationships.platform_id, 'name', platforms.name)
            order by relationships.platform_id
        ) as observed_platforms
    from {{ ref('int_game_platforms') }} as relationships
    left join {{ ref('stg_platforms') }} as platforms using (platform_id)
    group by relationships.game_id
),

companies as (
    select
        relationships.game_id,
        jsonb_agg(
            jsonb_build_object(
                'involved_company_id', relationships.involved_company_id,
                'company_id', relationships.company_id,
                'name', companies.name,
                'developer', relationships.developer,
                'publisher', relationships.publisher
            ) order by relationships.involved_company_id
        ) as observed_company_relationships
    from {{ ref('int_game_companies') }} as relationships
    left join {{ ref('stg_companies') }} as companies using (company_id)
    group by relationships.game_id
)

select
    games.game_id,
    games.name,
    games.slug,
    games.first_release_at,
    games.rating,
    games.rating_count,
    games.total_rating,
    games.total_rating_count,
    coalesce(genres.observed_genres, '[]'::jsonb) as observed_genres,
    coalesce(platforms.observed_platforms, '[]'::jsonb) as observed_platforms,
    coalesce(companies.observed_company_relationships, '[]'::jsonb) as observed_company_relationships
from {{ ref('stg_games') }} as games
left join genres using (game_id)
left join platforms using (game_id)
left join companies using (game_id)
