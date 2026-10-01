select
    igdb_id as game_id,
    name,
    slug,
    to_timestamp((payload ->> 'first_release_date')::bigint) as first_release_at,
    to_timestamp((payload ->> 'updated_at')::bigint) as source_updated_at,
    (payload ->> 'rating')::numeric as rating,
    (payload ->> 'rating_count')::bigint as rating_count,
    (payload ->> 'total_rating')::numeric as total_rating,
    (payload ->> 'total_rating_count')::bigint as total_rating_count,
    payload -> 'genres' as genre_ids,
    payload -> 'platforms' as platform_ids,
    payload -> 'involved_companies' as involved_company_ids,
    fetched_at
from {{ source('igdb', 'raw_games') }}
