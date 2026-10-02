select
    extract(year from first_release_at at time zone 'UTC')::integer as release_year,
    count(*) as release_count
from {{ ref('stg_games') }}
where first_release_at is not null
group by 1
