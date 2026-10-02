-- One violation per game/column; SQL NULL and JSON null are both invalid containers.
-- Array contents remain covered by independent integration comparisons.
select catalog.game_id, relationships.column_name
from {{ ref('mart_game_catalog') }} as catalog
cross join lateral (values
    ('observed_genres', catalog.observed_genres),
    ('observed_platforms', catalog.observed_platforms),
    ('observed_company_relationships', catalog.observed_company_relationships)
) as relationships(column_name, value)
where jsonb_typeof(relationships.value) is distinct from 'array'
