"""Shared source-to-raw contracts for implemented IGDB entities."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityConfig:
    """Describe an endpoint and its raw destination using code-owned names.

    ``source_primary_key`` identifies the payload field used for sorting and
    loading; ``raw_primary_key`` names its destination column/conflict key.
    ``update_field`` is a source payload field, or None when not applicable.
    It describes metadata only: no incremental filtering or extra column is
    implied. ``raw_table`` excludes the environment-configured schema.
    """

    endpoint: str
    fields: tuple[str, ...]
    raw_table: str
    source_primary_key: str
    raw_primary_key: str
    update_field: str | None


GAMES = EntityConfig(
    endpoint="games",
    fields=(
        "id",
        "name",
        "slug",
        "first_release_date",
        "rating",
        "rating_count",
        "total_rating",
        "total_rating_count",
        "updated_at",
        "genres",
        "platforms",
        "involved_companies",
    ),
    raw_table="raw_games",
    source_primary_key="id",
    raw_primary_key="igdb_id",
    update_field="updated_at",
)


GENRES = EntityConfig(
    endpoint="genres",
    fields=("id", "name", "slug", "updated_at"),
    raw_table="raw_genres",
    source_primary_key="id",
    raw_primary_key="igdb_id",
    update_field="updated_at",
)


PLATFORMS = EntityConfig(
    endpoint="platforms",
    fields=("id", "name", "slug", "updated_at"),
    raw_table="raw_platforms",
    source_primary_key="id",
    raw_primary_key="igdb_id",
    update_field="updated_at",
)


COMPANIES = EntityConfig(
    endpoint="companies",
    fields=("id", "name", "slug", "updated_at"),
    raw_table="raw_companies",
    source_primary_key="id",
    raw_primary_key="igdb_id",
    update_field="updated_at",
)


INVOLVED_COMPANIES = EntityConfig(
    endpoint="involved_companies",
    fields=("id", "game", "company", "developer", "publisher", "updated_at"),
    raw_table="raw_involved_companies",
    source_primary_key="id",
    raw_primary_key="igdb_id",
    update_field="updated_at",
)
