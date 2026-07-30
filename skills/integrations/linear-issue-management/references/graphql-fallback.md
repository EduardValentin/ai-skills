# Linear GraphQL Fallback

Read this reference only when Linear MCP is unavailable and the workflow will
use direct GraphQL. If Linear MCP is available, use it and do not continue
here.

## Keychain access

Direct GraphQL requires macOS Keychain access to the generic-password service
`course-platform.linear-api-key`. No environment-variable or plaintext-file
fallback is used.

Retrieve the item with `/usr/bin/security find-generic-password -s
course-platform.linear-api-key -w` only inside a non-verbose process that
captures and consumes stdout in memory. Never run the retrieval as a standalone
agent tool call because stdout is the credential. Use an in-process HTTP client
or another mechanism that keeps the credential out of process arguments and
diagnostics.

Remove only the single terminal `LF` or `CRLF` added by the command, then reject
an empty value or any remaining whitespace. Never print, log, persist, commit,
return, or expose it. If `/usr/bin/security` is unavailable, retrieval fails, or
access is missing, locked, or denied, do not modify Keychain state, change
access controls, or retry automatically. Report that GraphQL fallback is
unavailable and stop before any live write.

## Request contract

Send a JSON `POST` to `https://api.linear.app/graphql` with `Content-Type:
application/json`. Use the credential only as the raw `Authorization` header
value; do not prepend `Bearer`. Disable redirects and treat every `3xx` response
as failed or unverified; never forward the credential or request body.
Build the JSON body in the same process or supply it through protected standard
input. Keep both credential and body out of process arguments, shell history,
verbose output, logs, and diagnostics.

Keep small named operations and variables local to each request. Resolve
current workspace IDs before mutation; never interpolate guessed or stale IDs.

## Preflight and pagination

Before creation, query viewer and organization context, actor membership, team
defaults, and applicable or selected template data. Treat `templateId` and
`useDefaultTemplate` as approval-gated fields. Apply a template only after all
effective values have been preflighted and approved; stop if current defaults
cannot be determined.

Follow `pageInfo.hasNextPage` and `endCursor` until every metadata or
duplicate-search connection is complete. Use `includeArchived: true` for
duplicate searches.

## Mutation verification

Treat a non-success HTTP status, any GraphQL `errors`, a false or missing
mutation success flag, incomplete response data, a missing issue, a failed
re-read, or effective metadata that differs from approval as a failed,
mismatched, or unverified write.

Keep the complete pre-mutation issue-ID set from duplicate search. If creation
has an unknown outcome, do not claim success or retry blindly. Search again and
accept success only for a unique newly observed issue matching the approved
payload or other definitive mutation evidence. Otherwise report the outcome as
pending.
