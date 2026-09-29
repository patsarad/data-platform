# High-water-mark semantics (task 4.1)

**Accepted task 4.1 design; tasks 4.2–4.7 implemented and verified offline.** The design was reviewed September 26, 2026 against the contracts, fetchers, paginator, CLI, runner, storage helpers, and offline tests. Normal CLI runs use per-entity persisted lookup, a fixed run-start cutoff, and optional windows; eligible successes publish the cutoff after the raw context exits. Explicit full refresh and backfill are available. No live incremental ingestion or PostgreSQL validation has been performed.

## Persisted lookup helper (task 4.2)

`src/storage/ingestion_runs.py::get_source_watermark(connection, schema_name, entity) -> datetime | None` reads the greatest non-NULL `source_watermark_end` from `succeeded` runs for exactly that entity in the supplied schema. The caller's connection selects the database. Schema identifiers use `psycopg.sql.Identifier`; the entity is a bound value. One `SELECT MAX(...)` excludes failed/running rows and NULL ends. Completion order is irrelevant: a later NULL-ended or older-ended success cannot hide or regress progress. Empty or legacy NULL-only history returns `None`.

For a caller that already owns a connection and schema setting:

```python
from src.storage.ingestion_runs import get_source_watermark

watermark = get_source_watermark(connection, schema_name, "games")
```

The result is the driver's datetime value, with no timestamp rounding or window calculation. The helper reads only run metadata, never raw rows, payload timestamps, archives, counts, or `source_watermark_start`. It opens/closes its cursor but creates no tables, performs no writes, and never commits, rolls back, closes, or enters the supplied connection. A SELECT may start a driver transaction; transaction completion and visibility remain the caller's responsibility. Use committed history without pending metadata writes on that connection; this helper cannot independently certify durability of rows visible to the caller. Database/missing-table errors and all other lookup failures propagate; only an aggregate NULL means no eligible watermark.

Offline tests assert exact SQL, parameters, modeled history results, error propagation, and absence of transaction/connection management calls. They do not execute PostgreSQL SQL or prove database isolation/durability; see [task 4.2 verification](../engineering/TESTING.md#task-42-lookup-verification). The normal CLI runner calls this helper after committed metadata DDL and before recording the running row; lookup failures abort before source work.

## Optional window API (task 4.3)

`src/ingestion/windows.py::calculate_source_window(watermark, *, run_started_at) -> SourceWindow` is a pure calculation: no clock reads, database access, or payload inspection. The caller supplies one fixed run-start datetime before source work. Both datetime inputs must be timezone-aware and at/after the epoch; any aware timezone is converted to UTC. Run start is floored to seconds using integer timedelta division. An existing watermark must already have whole-second precision; fractional watermarks are rejected rather than silently rounded. With W, reject `U <= W` and calculate `L=max(0, W-86400)`. With `watermark=None`, retain U and use `lower_bound=None` for an entirely unfiltered bootstrap.

The frozen `SourceWindow(lower_bound, upper_bound)` requires both arguments. Bounds must be nonnegative integer Unix seconds (booleans, floats, strings, and missing/None upper bounds are rejected). `lower_bound=None` deliberately represents bootstrap, not an incomplete filtered interval; otherwise require `lower_bound < upper_bound`. The calculator additionally enforces `U > W`, which the value object alone cannot check. A planned cutoff is not checkpoint eligibility or persistence.

Games, companies, and involved-companies builders and fetchers accept the keyword-only `window: SourceWindow | None = None`. Omitting it or passing a bootstrap window emits no filter and preserves the exact existing query. Supplying integer bounds emits `where updated_at >= L & updated_at < U;`. The same immutable value is captured across all offset pages, never recomputed from time or returned data. Custom projections replace defaults exactly, with no timestamp addition. All fetchers materialize iterable fields once. Genres/platforms now also accept optional windows for explicit backfills; normal and full-refresh calls remain unfiltered.

Offline query-construction example (no client, source request, or database required):

```python
from datetime import datetime, timezone
from src.ingestion.fetch_companies import build_companies_query
from src.ingestion.windows import calculate_source_window

window = calculate_source_window(
    datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    run_started_at=datetime(2026, 9, 26, 12, 0, 0, 999999, tzinfo=timezone.utc),
)
query = build_companies_query(limit=500, offset=0, window=window)
assert window.lower_bound == 1790251200
assert window.upper_bound == 1790424000
assert query == (
    "fields id, name, slug, updated_at; "
    "where updated_at >= 1790251200 & updated_at < 1790424000; "
    "sort id asc; limit 500; offset 0;"
)
bootstrap = calculate_source_window(
    None, run_started_at=datetime(2026, 9, 26, 12, tzinfo=timezone.utc),
)
assert bootstrap.lower_bound is None
assert build_companies_query(limit=500, offset=0, window=bootstrap) == (
    "fields id, name, slug, updated_at; sort id asc; limit 500; offset 0;"
)
```

Direct fetch callers can pass that same value as `fetch_companies_batches(client, window=window)` (likewise games/involved companies). No fetcher reads persisted history. The CLI runner now performs lookup and window calculation for those three entities. Fetchers preserve all returned records, including absent/null/unexpected timestamps; filtering is requested from IGDB, not performed locally. Offline tests prove query construction, frozen paging arguments, and payload fidelity, not live API filtering or snapshot consistency. [Verification](../engineering/TESTING.md#task-43-window-verification) describes the original optional API coverage.

## Overlap replay contract (task 4.4)

Existing games/companies/involved-companies loaders prepare unconditional `ON CONFLICT (igdb_id) DO UPDATE` statements keyed only by source `id`. The relationship entity uses its own record ID, never game/company references or a composite key. Tied timestamps do not merge distinct IDs, and repeated IDs remain in input order without timestamp deduplication. Each conflict replaces complete payload/fetch time and existing extracted columns; missing/null timestamps and all optional/nested source values remain intact. Counts acknowledge every input occurrence after the helper commit, including replays.

No production change was necessary. Focused offline tests compose calculated overlapping windows, real pagination/fetchers, and real upsert preparation against queued responses and mocked cursors. They assert emitted SQL, parameters, row order, payload fidelity, counts, and commit calls. They do not prove actual PostgreSQL constraint enforcement, live idempotency, rollback, durability, source filtering, or completeness. **Upserts do not enforce source-version ordering: a later stale response can overwrite a newer payload.** See [storage semantics](RAW_STORAGE.md#overlapping-window-preparation-task-44) and [verification](../engineering/TESTING.md#task-44-overlap-upsert-verification).

Task 4.5 activates runtime incremental selection and eligibility without changing these upserts. Empty/error behavior, archival, loading order, schemas, transaction boundaries, and reference-entity behavior remain unchanged.

## Entity policy and source evidence

| Entity | Accepted normal-run policy | Official field reference |
|---|---|---|
| `games` | Bootstrap, then `updated_at` windows | [Game](https://api-docs.igdb.com/#game) |
| `genres` | Full endpoint read every run; no watermark | [Genre](https://api-docs.igdb.com/#genre) |
| `platforms` | Full endpoint read every run; no watermark | [Platform](https://api-docs.igdb.com/#platform) |
| `companies` | Bootstrap, then `updated_at` windows | [Company](https://api-docs.igdb.com/#company) |
| `involved_companies` | Bootstrap, then `updated_at` windows | [Involved Company](https://api-docs.igdb.com/#involved-company) |

All five endpoints document `updated_at` as a datetime describing the entry's last update. [Filters](https://api-docs.igdb.com/#filters) document numeric `>=`/`<`, null predicates, and conjunction; [sorting](https://api-docs.igdb.com/#sorting) and [pagination](https://api-docs.igdb.com/#pagination) document field ordering, positional offsets, and a maximum page size of 500.

The [expander response](https://api-docs.igdb.com/#expander) shows integer update timestamps, for example `1323216000`. The [release-date example](https://api-docs.igdb.com/#coming-soon-games-for-playstation-4) calls `1538129354` milliseconds, although it represents the stated 2018 date in seconds. We interpret these JSON timestamps as Unix seconds; that unit interpretation is an inference from examples, not an unambiguous precision guarantee in the field tables.

The reviewed documentation does not establish non-nullness, strict timestamp monotonicity, a maximum visibility delay, propagation of related-record changes to a parent timestamp, or snapshot isolation across requests. These are not source guarantees.

**Project decisions:** genres/platforms use the full-refresh fallback because they are treated as modest lookup datasets, not because they lack `updated_at`. This size assumption must be revisited if observed volume makes full reads costly; the five-row smoke samples do not prove it. Companies and relationship records are not assumed small. Each entity follows its own timestamp; a company edit is not assumed to update a game. Full refresh means fetch and upsert, never truncate or delete rows absent from a response.

## Window and metadata contract

Use one active writer per entity in a configured database/schema. This is an operational requirement, not an implemented lock. Independent entities may run separately. Lookup failure aborts before source work; it is never mistaken for no history.

| Symbol or column | Meaning |
|---|---|
| `W` | Greatest non-NULL `source_watermark_end` among durable `succeeded` rows for this entity in this database/schema. This is the last successful progress boundary, not the last run by completion time. Ignore failed/running rows and successes with NULL ends. |
| `O` | Fixed initial overlap policy: 86,400 seconds (24 hours). No new configuration flag. |
| `U` | UTC clock at this entity's run start, floored to whole Unix seconds, captured once before any source request. Planned exclusive cutoff; never recomputed per page or from completion time. |
| `L` | For a subsequent normal run, `max(0, W - O)` in Unix seconds. |
| `source_watermark_start` | Actual inclusive timestamp lower bound `L` for a windowed extraction; NULL for an unfiltered extraction. It is **not** `W` and is never used as progress. The runner persists it with the running record. |
| `source_watermark_end` | NULL until an eligible success is durably recorded; then `U`, the committed exclusive progress boundary. It is **not** maximum payload `updated_at`, fetch time, or completion time. Ineligible successes and failed/running rows retain NULL. |

The high-water mark is therefore a completed extraction cutoff, subject to the source-consistency limitations below. It does not certify that every source row before that instant was observed. Never derive it from raw-table maxima, archive contents, processed counts, or the timestamp of a single returned record. Greatest-end lookup prevents a later historical run from moving progress backwards. Retain planned `U` in the run context and log the selection/bounds with the run UUID for diagnosis; NULL end means the run published no checkpoint, not that it had no planned upper bound.

For a normal run with `W`, freeze `[L, U)` across every page. Include timestamps equal to `L`; exclude those equal to `U`. If `U <= W` (same-second rerun or clock regression), abort before source work with no progress; do not manufacture a later cutoff. Use a correctly synchronized UTC host clock. Clock correctness is a deployment assumption.

**Bootstrap:** if there is no eligible `W`, read the whole endpoint unfiltered from offset zero, with no historical lookback limit. Set start to NULL. Capture `U` anyway and, after an eligible success, set end to `U`. Here `U` is a conservative progress cutoff, not a query bound: the unfiltered scan may also load records updated at/after `U`; the next window re-reads them. Existing successful smoke runs with NULL ends do not constitute a bootstrap. A missing/null timestamp found during bootstrap prevents checkpoint creation as described below.

The 24-hour overlap is a deliberately conservative starting budget for second-level ties, short publication delays, and ordinary reruns, at the cost of re-reading a day's changes. It is not a measured IGDB lag bound and does not promise recovery beyond a day. Bootstrap reads all history so older records are not discarded by an arbitrary initial date. Outages lasting longer than a day still resume from `W - O`, not from “now minus one day,” covering the elapsed gap. No additional delay before `U` is imposed.

### Units and example query

Compare integer Unix seconds since `1970-01-01T00:00:00Z`. Convert with timezone-aware UTC datetimes (for example `datetime.fromtimestamp(value, timezone.utc)`) for existing PostgreSQL `TIMESTAMPTZ` columns. Watermarks have zero microseconds; lifecycle/fetch timestamps retain their existing precision. PostgreSQL may display another session timezone; compare instants. Do not multiply by 1,000, round source fractions, parse strings, or invent timestamps for missing values. Raw JSONL/JSONB retains the original values unchanged.

Implemented optional companies query for `W=2026-09-25T12:00:00Z`, `L=2026-09-24T12:00:00Z`, `U=2026-09-26T12:00:00Z`:

```text
fields id, name, slug, updated_at; where updated_at >= 1790251200 & updated_at < 1790424000; sort id asc; limit 500; offset 0;
```

This is verified query-builder output when supplied the window above; it has not been live-validated against IGDB. Subsequent pages use offsets 500, 1000, etc., with identical fields, bounds, and ordering. Existing query builders called without window arguments keep their exact output. Custom fields remain exact replacements, with no automatic timestamp addition. A custom projection cannot establish the normal default-field checkpoint, even if it includes `updated_at` or returns no rows; it preserves fetch/archive/load behavior with a NULL end. Direct arbitrary fetch callbacks likewise do not imply eligibility.

## Eligibility and result handling

A normal/bootstrap run may publish `U` only when all of these hold: it uses the entity's default field contract and prescribed selection; `max_batches is None`; page size is within 1–500; pagination returns normally after a short or empty page; all returned timestamps pass the rules below; all fetched records are archived and acknowledged as processed by the loader; the raw connection context exits successfully; and terminal success plus end are committed together in the metadata transaction. No separate watermark transaction or new schema is needed. The CLI declares selection with `RunSelection`; the runner verifies canonical fetcher/options before publishing. Direct callback callers without that context cannot publish progress.

| Case | Accepted outcome after archive/raw/terminal success |
|---|---|
| Valid nonempty bootstrap or subsequent window | End becomes `U`; next normal run starts at `max(0, U - O)`. |
| Empty uncapped bootstrap/window | End becomes `U` with counts 0/0. Preserve empty archive, raw DDL, and existing empty-upsert behavior; no artificial raw upsert commit. An empty response establishes observed exhaustion, not a guarantee of no hidden records. |
| Any supplied `--max-batches`, including zero/negative, a high cap, or an early short/empty page | End remains NULL; prior `W` remains effective. Successful archive/load may still have `succeeded` status. A bounded bootstrap remains unfiltered; a bounded subsequent run uses the normal window, but cannot checkpoint it. |
| Missing/null/invalid returned `updated_at` on an incremental entity | Preserve and load every payload without coercion or dropping rows. Successful loading may finish `succeeded` with NULL end and a fixed safe warning explaining withheld progress. Retry uses the old `W` (or repeats bootstrap). |
| Genres/platforms, including missing/null update times | Unfiltered fetch/upsert; both watermark columns remain NULL. Empty results do not erase old raw rows. |

For timestamp eligibility require a JSON integer (excluding booleans), nonnegative, convertible to the supported UTC datetime, and no later than the UTC clock at fetch completion. This rejects typical millisecond timestamps and unexpected future values without silently repairing them. A subsequent window additionally requires every returned timestamp to satisfy `L <= updated_at < U`; a violation withholds the end. Bootstrap may legitimately observe updates between its start cutoff and fetch completion. Do not change loader optional-field tolerance or acknowledged counts to enforce these gates.

Records sharing a second are processed by ID across all pages; no timestamp is a unique row key. The lower boundary is inclusive, and overlap re-reads the whole boundary second. Do not checkpoint individual pages or resume at a last-seen timestamp/offset. All supplied caps are ineligible even if exhaustion seems evident: the current paginator returns only a list and has no completeness report. After a bounded run, an uncapped rerun starts at offset zero for the unchanged checkpoint window (or the full bootstrap), so unseen records are not skipped by partial progress.

A timestamp filter can hide records whose source timestamp is absent, null, malformed, backdated, or later cleared. Validation only covers returned rows; it cannot detect excluded records. The unfiltered bootstrap, reference refreshes, and explicit full refresh can retrieve them. Do not silently switch a large entity to full refresh, substitute `created_at`/`fetched_at`, or claim null detection from an empty filtered response. Persistent timestamp problems require investigation and an explicit full refresh; withholding a checkpoint may cause repeated full bootstraps.

## Offset pagination and consistency limits

Retain `sort id asc` and existing offset pagination. Unique-ID ordering is deterministic for a fixed result set and handles timestamp ties without relying on unsupported multi-field ordering. Every extraction starts at offset zero, including incremental runs. Pagination completion means the existing empty/short-page stopping rule was observed, not a source snapshot was taken.

An update can move a row out of `[L, U)` while pages are being read. For example, matching IDs `[1, 2, 3, 4]` return `[1, 2]` on page one; if ID 1 moves past `U`, offset 2 now returns `[4]`, skipping unchanged ID 3. Insertions, deletions, and delayed visibility can also shift offsets, causing duplicates or omissions. Fixed `U` limits the intended selection but does not freeze its membership. A skipped old row outside the next overlap can remain missing; even bootstrap has this risk. Upserts handle repeated IDs but cannot recover unseen rows. They also do not enforce version ordering, so a stale source response or concurrent writer could replace newer payloads.

The accepted scope is best-effort incremental synchronization with replay, not lossless change-data capture. Assume updates normally receive useful timestamps and become visible within the overlap; neither is guaranteed. Full rereads can repair older omissions but still lack snapshot consistency. Source deletions are not propagated by upserts. This task does not introduce keyset pagination, tombstones, historical snapshots, automatic reconciliation, or cross-entity consistency guarantees.

## Failure and transaction contract

Preserve the existing [transactions and acknowledged counts](RAW_STORAGE.md#transactions): separate metadata DDL/start commits, fetch then archive without an open database connection, separate raw DDL and nonempty-load commits, raw context exit, then terminal metadata on a fresh connection. Safe failure reporting uses another connection and never replaces the original error.

| Failure point | Retained counts/data and watermark outcome |
|---|---|
| Lookup, metadata setup/start, or start-context exit | Abort before source work; a running row may exist if a commit succeeded. No end is eligible. Never fall back to a new bootstrap because the lookup failed. |
| Source/client/later page | Fetched/loaded remain 0/0 because no complete list returned. No partial archive/load. Best-effort failed row; end NULL. |
| Archive | Fetched is the returned list length; loaded is zero. Archive may be partial; no raw load. Best-effort failed row; end NULL. |
| Raw DDL, preparation, execution, or load commit | Keep full archive and acknowledged fetched count. Loaded remains zero until the helper returns; earlier DDL commits survive. Best-effort failed row; end NULL. |
| Raw context exit after helper returned | Retain acknowledged loaded count and committed raw data. Fail the run; end NULL. |
| Terminal connection/write/commit after successful raw context | Command fails; committed raw data and acknowledged counts remain. Best-effort failed row with NULL end, unless success actually committed as described below. |

Terminal success must set status/counts/end atomically in its existing metadata commit and retain the `status='running'` guard. A failed or stale running row never supplies progress. Process death, `KeyboardInterrupt`, failure-reporting outages, or lost acknowledgments can leave running rows and their initial zero counts; age alone must not promote them to success. No automatic cleanup or stale-run repair is designed into Phase 4. Retry from the last durable eligible success, after ensuring the previous writer is no longer active.

**Ambiguous commits:** if a raw commit takes effect but its acknowledgment is lost, the helper may not return, so loaded stays zero even though data exists. No end is published; rerun by upsert. If the terminal success/end commit takes effect but its acknowledgment (or subsequent context exit) fails, the command still fails and all mode stops, but the database may contain an eligible succeeded row. The guarded failed update cannot overwrite it. On the next invocation, a fresh successful lookup accepts that durable end because raw commit/context success preceded it. If metadata cannot be read, stop; do not guess. “A failed command never advances” is thus too strong: failed/running **database rows** never advance, while a durable success can outlive a client-observed error. Archives/counts alone cannot resolve an ambiguous outcome.

In `--entity all`, lookup, clock cutoff, eligibility, archive, raw context, and metadata belong to each entity separately, in the existing games → genres → platforms → companies → involved_companies order. Earlier eligible successes may advance even when a later entity fails. Failed entities do not advance except for the durable-success acknowledgment case above; unstarted entities have no new run or progress. Genres/platforms never publish an end. There is no group checkpoint or rollback of earlier entities.

## Worked examples

All examples are hypothetical source responses under the implemented normal-run policy. They use UTC and assume stable pages, default fields, valid timestamps, matching acknowledged counts, and successful terminal commits unless stated otherwise. `NULL` means no value on that run row; it does not clear a prior checkpoint.

| Scenario | Extraction and run metadata | Next effective checkpoint |
|---|---|---|
| First games run | No `W`; capture `U=2026-09-25T12:00:00Z`; uncapped unfiltered scan returns old records and one updated at `12:00:01Z` during extraction. Archive/load all. Start NULL, end `2026-09-25T12:00:00Z`. | `W=2026-09-25T12:00:00Z`; no historical cutoff was imposed. The newer record will be replayed. |
| Overlap rerun | Previous `W=2026-09-25T12:00:00Z`; `U=2026-09-26T12:00:00Z`. Query `[2026-09-24T12:00:00Z, 2026-09-26T12:00:00Z)`. Two different IDs at exactly the lower bound are included; a record at exactly `U` is excluded. Start is the lower bound; end is `U`. | `W=2026-09-26T12:00:00Z`; next run re-reads from `2026-09-25T12:00:00Z`, including the previously excluded second. |
| Empty result | Previous `W=2026-09-26T12:00:00Z`; `U=2026-09-27T12:00:00Z`. Query `[2026-09-25T12:00:00Z, 2026-09-27T12:00:00Z)` returns an empty first page uncapped. Empty archive, raw context success, metadata 0/0; start is lower bound, end `U`. | `W=2026-09-27T12:00:00Z`, despite no payload maximum. |
| Bounded partial run | Same prior `W` and window as the empty example, but `--batch-size 2 --max-batches 1` fetches two of five matching records. Archive/load succeeds with 2/2; start `2026-09-25T12:00:00Z`, end NULL. | Still `W=2026-09-26T12:00:00Z`. An uncapped retry uses that lower bound and offset zero; it can reach the other three IDs. A bounded first run likewise cannot create `W`. |
| Failure after raw commit | Same window; five rows commit and helper returns 5. Terminal metadata write fails before commit; failure reporting succeeds with 5/5. Start `2026-09-25T12:00:00Z`, failed status, end NULL. | Still `W=2026-09-26T12:00:00Z`; replay all five safely by ID. If success had committed but its acknowledgment were lost, lookup would instead observe end `2026-09-27T12:00:00Z`. |

## Full refresh and backfill (task 4.7)

`--full-refresh` ignores `W` for extraction, reads each selected endpoint unfiltered from offset zero with default fields, and upserts without truncation or deletion. For incremental entities it follows bootstrap eligibility: start NULL, capture `U` before fetching, and publish `U` only after an uncapped valid success with `U > W` if `W` exists. It can retrieve old/null-timestamp records; encountering an invalid timestamp still withholds progress while preserving the raw load. For reference entities it is their usual unfiltered path with both columns NULL.

A historical backfill uses `--backfill-start A --backfill-end B`, with exact `YYYY-MM-DDTHH:MM:SSZ` whole-second UTC values at or after the Unix epoch and `A < B`. Every selected entity, including genres/platforms in all mode, requests `updated_at >= A & updated_at < B` on each page from offset zero. The run records start `A` and always leaves end NULL, even if uncapped and successful. It does not look up, replace, or advance the normal checkpoint; future normal runs resume from the greatest prior eligible end. With no such end, the next normal run still bootstraps. Backfills fetch current source objects selected by current `updated_at`, not past versions. They can miss records updated since the historical interval. Full refresh is the chosen repair for omissions of unknown age.

The two backfill flags must be supplied together and cannot be combined with `--full-refresh`. Parsing rejects malformed, reversed, equal, or pre-epoch bounds before settings, source, or database work. `--entity all` applies either mode independently in the usual order. Caps retain their existing per-entity meaning: any supplied cap withholds a full-refresh checkpoint; backfills always withhold it. Default fields, archives, upserts, counts, and lifecycle ordering remain unchanged.

```bash
python -m src.ingestion.run_ingestion --entity companies --full-refresh
python -m src.ingestion.run_ingestion --entity all --backfill-start 2026-09-01T00:00:00Z --backfill-end 2026-09-02T00:00:00Z
```

## Implementation status

| Task | Bounded implementation consequence |
|---|---|
| 4.2 (complete) | Read-only per-entity greatest successful non-NULL-end helper implemented and verified offline; ignores legacy NULLs/failed/running rows and propagates lookup errors. The normal CLI runner now calls it for incremental entities. |
| 4.3 (complete) | Pure window calculation and optional frozen bounds in the three supported query/fetch paths, verified offline. The normal CLI runner now supplies those bounds; bootstrap/reference reads remain unfiltered. |
| 4.4 (complete) | Existing primary-key upsert preparation verified offline for overlaps, tied timestamps, changed/stale replays, payload fidelity, input-order counts, and commit calls. No production changes; no claim of live constraint enforcement or snapshot completeness. |
| 4.5 (complete) | CLI passes explicit run selection/cap/default-field context. The runner looks up per-entity history, freezes windows, records the lower bound at start, and commits eligible end only with guarded terminal success after raw context exit. Timestamp/count gates, fixed safe warnings, and empty-result handling are verified offline. |
| 4.6 (complete) | Existing tests cover individual window, timestamp, cap, projection, count, lookup, metadata guard, and ambiguous-acknowledgment gates. Nine added cases cover consecutive bootstrap/overlap/no-change runs, runtime UTC/epoch behavior, source/archive/raw failures, all-mode eligible-success retention, and retry after a failed raw context exit. Fakes cannot establish live source isolation or database durability. |
| 4.7 (complete) | Explicit CLI full refresh and historical backfill follow the policy above, including caps and no-progress rules, without deleting raw records or resetting earlier successful metadata. |

Task 4.1 required no implementation changes. Tasks 4.2 and 4.3 added lookup and optional query-window support. Task 4.4 verified existing upsert preparation. Task 4.5 activates normal CLI incremental ingestion and checkpoint gates. Task 4.6 adds offline behavior coverage without production changes. Task 4.7 adds explicit selection modes; direct fetcher calls still default to unfiltered queries. Bounded CLI runs and reference entities retain NULL ends, as do backfills.
