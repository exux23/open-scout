# REA investigation and reconstruction boundary

Investigation date: October 22, 2026.

## Inputs and reproducibility

- Upstream tool: [morluto/rea](https://github.com/morluto/rea), checked out at
  `86655eac66555aaf4cbe500797d34071077a396a` (package version 6.7.0).
- Analyzed artifact: the published MIT-licensed `exa-js@2.26.0` npm package.
- Acquisition: `npm pack exa-js@2.26.0`, extract to a dedicated work directory.
- Analysis: `npx -y rea-agents@6.7.0 analyze-javascript-application /absolute/path/to/package --json`.
- Root artifact SHA-256:
  `a060a297bf9555e3c285667145acb88526d9cd40ec83f40779053f6f071cef10`.
- REA Evidence ID:
  `ev_33baeab57c9799c9fc8ab0fd631647340f89e4cdd4f3c0a24c7011495a6f6e41`.

The complete analysis was retained locally as intermediate evidence. The repository
includes a clearly labeled compact [evidence excerpt](rea-evidence-excerpt.json),
not a rewritten canonical REA Evidence record. Re-running REA may change identifiers
when local paths or tool versions differ; the artifact digest establishes the input.

## Observations

REA parsed four JavaScript/declaration artifacts among seven relevant files, visited
60,078 AST nodes, and reported zero parse failures. The endpoint observations in the
excerpt identify `/search`, `/contents`, and `/findSimilar` in the shipped client.
These are static artifact observations; no Exa service requests were made.

Focused inspection of the same `dist/index.js` artifact confirmed:

| Location in exa-js 2.26.0 | Observation |
| --- | --- |
| Constructor, approximately lines 3631–3652 | Configurable base URL, API-key header, JSON transport |
| Search methods, approximately lines 3940–4008 | Search requests carry the query and options |
| Similar methods, approximately lines 4010–4079 | Similar-page requests use a source URL |
| getContents, approximately lines 4084–4121 | Content requests accept URL arrays |

The public [search reference](https://exa.ai/docs/reference/search) and
[contents reference](https://exa.ai/docs/reference/get-contents) corroborated the
public contract. The old find-similar documentation URL redirected to the current
search page on the investigation date; the published SDK still contains that route.

## Independent design decisions

Open Scout implements only the routes and options described in its README. SQLite
FTS5, bounded crawling, BGE embeddings, cosine retrieval, reciprocal rank fusion,
the UI, and MCP adapter are original implementation choices. They are not claims
about Exa's internals. No Exa SDK source, branding, private code, credentials, data,
or search index was incorporated into the application.

The API shape is familiar, but full SDK compatibility is not claimed. Content
retrieval is index-only. `auto` selects local keyword/hybrid behavior; it does not
replicate Exa routing. Generated summaries, global discovery, research agents,
websets, publication dates, and link-prediction models are outside this release.

## Unknowns and coverage limits

REA inspected inert syntax and did not execute the package. Dynamic relationships
may remain unresolved. The tool explicitly marks graph coverage incomplete, and
static relationships do not prove runtime behavior. Exa's server implementation,
training data, proprietary models, global index, ranking quality, latency at scale,
and operational infrastructure remain unknown. This work reconstructs a useful
public-facing capability subset, not the closed service itself.
