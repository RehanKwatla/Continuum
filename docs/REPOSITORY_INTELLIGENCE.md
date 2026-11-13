# Repository Intelligence — public GitHub milestone

## Initial repository assessment

The existing GitHub integration uses PyGithub for authenticated account connection and synchronously converts selected commits, issues, pull requests, README files, and root files into the existing `Source` pipeline. It requires OAuth, a PAT, or a configured server token; it does not validate an arbitrary public GitHub URL, traverse a full branch tree, persist a repository snapshot, or expose durable asynchronous progress. The app has no external queue worker. The public judge mode provides a fixed demo identity and blocks writes except for explicit allowlisted actions.

Reusable pieces: project and workspace membership checks, `Source` normalization, secret scanning, evidence-span creation, GitHub enums, the central Axios client, and the project's existing route and visual components. Repository-specific records are additive; they do not create approved claims.

## Implemented in this milestone

- Provider contract and `GitHubPublicConnector` using the fixed `api.github.com` hostname, allowlisted paths, TLS, timeouts, disabled redirects, bounded retries, rate-limit mapping, and paginated REST calls.
- Strict public GitHub URL parsing; optionally accepts `/tree/{branch...}` with slash-containing branch names.
- Metadata and branch validation, then a persisted snapshot executed through FastAPI `BackgroundTasks` and independently opened database sessions.
- Bounded recursive tree ingestion with a Contents API fallback and explicit truncated-tree warnings.
- File metadata, filtered text extraction, and Source/EvidenceSpan creation using the existing ingestion pipeline. Excluded paths and failed/oversize files remain visible as skipped metadata where within the tree-entry cap.
- Bounded commit, issue, pull-request, changed-file and review retrieval, persisted records, and source attribution. Raw records remain separate from human-approved claims.
- Project-scoped repository detail, branch, run progress, snapshot, file, commit, issue and pull-request endpoints; reader access follows normal project membership. Anonymous analysis is restricted to projects in the configured demo workspace.
- A Repository Intelligence screen on the project's existing GitHub route, with URL validation, branch selection, analysis stages, and paginated record views.

## Default safety limits

Settings are configurable by `REPOSITORY_MAX_*` environment variables:

| Limit | Default |
| --- | ---: |
| Files whose content may be fetched | 80 |
| Individual file content | 256 KiB |
| Total file content | 8 MiB |
| File metadata rows per snapshot | 5,000 |
| Commits | 30 |
| Issues | 50 |
| Pull requests | 20 |
| GitHub API requests per connector | 250 |
| Tree fallback depth | 20 |
| Processing duration target | 300 seconds |

Secret/certificate files, environment files, generated/build/vendor directories, minified assets, binaries, and dependency lockfiles are excluded from source-content ingestion. Lockfiles and excluded files retain metadata and a reason when they fit within the metadata cap. GitHub emails are stored for commit attribution but removed from repository list responses.

## Known boundaries

- The background mechanism is FastAPI's in-process task runner. Job state survives request completion and is queryable, but a process restart during a run does not automatically resume it; a durable queue/worker is a later deployment milestone.
- A repository tree marked truncated stays explicitly partial even when the bounded fallback adds more entries. A tree larger than the metadata cap reports how many entries were omitted.
- GitHub review and changed-file details can be unavailable due to access limits; the snapshot carries a warning and the records expose availability separately.
- This change does not automatically extract or approve project-memory claims. It creates normalized Sources with provenance, then leaves reconstruction and human review to the existing workflow.
- The full PostgreSQL-backed suite and repository snapshot persistence could not be exercised because the configured local PostgreSQL service at `localhost:5433` was unreachable. The migration was validated in Alembic offline SQL mode but was not applied to a live database.
- A read-only live GitHub validation against `https://github.com/fastapi/fastapi` succeeded: GitHub returned repository metadata, the `master` default branch and 27 branches. Full file/commit/issue/PR ingestion against a live DB remains unverified.
