select
    igdb_id as genre_id,
    name,
    slug,
    to_timestamp((payload ->> 'updated_at')::bigint) as source_updated_at,
    fetched_at
from {{ source('igdb', 'raw_genres') }}
