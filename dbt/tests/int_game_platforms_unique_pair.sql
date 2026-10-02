select game_id, platform_id
from {{ ref('int_game_platforms') }}
group by game_id, platform_id
having count(*) > 1
