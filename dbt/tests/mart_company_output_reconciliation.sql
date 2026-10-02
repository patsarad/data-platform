with relationships as (
    select * from {{ ref('int_game_companies') }}
), company_ids as (
    select distinct company_id from relationships where company_id is not null
), game_pairs as (
    select
        company_id,
        game_id,
        bool_or(developer) as any_developer,
        bool_or(publisher) as any_publisher
    from relationships
    where company_id is not null and game_id is not null
    group by company_id, game_id
), expected as (
    select
        ids.company_id,
        companies.name,
        companies.company_id is not null as company_loaded,
        (select count(*) from relationships r
         where r.company_id = ids.company_id) as relationship_record_count,
        (select count(*) from relationships r
         where r.company_id = ids.company_id and r.game_id is null) as null_game_relationship_count,
        (select count(*) from game_pairs p
         where p.company_id = ids.company_id) as game_count,
        (select count(*) from game_pairs p
         where p.company_id = ids.company_id and p.game_id in (
             select game_id from {{ ref('stg_games') }}
         )) as loaded_game_count,
        (select count(*) from game_pairs p
         where p.company_id = ids.company_id and p.any_developer is true) as developer_game_count,
        (select count(*) from game_pairs p
         where p.company_id = ids.company_id and p.any_publisher is true) as publisher_game_count
    from company_ids ids
    left join {{ ref('stg_companies') }} companies using (company_id)
)
select expected.company_id, actual.company_id
from expected
full outer join {{ ref('mart_company_output') }} actual using (company_id)
where expected.company_id is null
   or actual.company_id is null
   or expected.name is distinct from actual.name
   or expected.company_loaded is distinct from actual.company_loaded
   or expected.relationship_record_count is distinct from actual.relationship_record_count
   or expected.null_game_relationship_count is distinct from actual.null_game_relationship_count
   or expected.game_count is distinct from actual.game_count
   or expected.loaded_game_count is distinct from actual.loaded_game_count
   or expected.developer_game_count is distinct from actual.developer_game_count
   or expected.publisher_game_count is distinct from actual.publisher_game_count
