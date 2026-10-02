select game_id, genre_id
from {{ ref('int_game_genres') }}
group by game_id, genre_id
having count(*) > 1
