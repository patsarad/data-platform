select
    involved_company_id,
    game_id,
    company_id,
    developer,
    publisher
from {{ ref('stg_involved_companies') }}
