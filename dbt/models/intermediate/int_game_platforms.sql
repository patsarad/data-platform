select distinct
    games.game_id,
    platform.platform_id::bigint as platform_id
from {{ ref('stg_games') }} as games
cross join lateral jsonb_array_elements_text(
    nullif(games.platform_ids, 'null'::jsonb)
) as platform(platform_id)
