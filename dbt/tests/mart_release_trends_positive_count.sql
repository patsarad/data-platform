select release_year, release_count
from {{ ref('mart_release_trends') }}
where release_count <= 0
