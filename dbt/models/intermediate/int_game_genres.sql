select distinct
    games.game_id,
    genre.genre_id::bigint as genre_id
from {{ ref('stg_games') }} as games
cross join lateral jsonb_array_elements_text(
    nullif(games.genre_ids, 'null'::jsonb)
) as genre(genre_id)
