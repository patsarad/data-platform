with expected as (
    select
        extract(year from first_release_at at time zone 'UTC')::integer as release_year,
        count(*) as release_count
    from {{ ref('stg_games') }}
    where first_release_at is not null
    group by 1
)

select
    expected.release_year as expected_year,
    actual.release_year as actual_year,
    expected.release_count as expected_count,
    actual.release_count as actual_count
from expected
full outer join {{ ref('mart_release_trends') }} as actual using (release_year)
where expected.release_year is null
    or actual.release_year is null
    or expected.release_count is distinct from actual.release_count
