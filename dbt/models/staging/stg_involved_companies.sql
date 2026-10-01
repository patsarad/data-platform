select
    igdb_id as involved_company_id,
    (payload ->> 'game')::bigint as game_id,
    (payload ->> 'company')::bigint as company_id,
    (payload ->> 'developer')::boolean as developer,
    (payload ->> 'publisher')::boolean as publisher,
    to_timestamp((payload ->> 'updated_at')::bigint) as source_updated_at,
    fetched_at
from {{ source('igdb', 'raw_involved_companies') }}
