# GitHub REST API Reference Guide

> A comprehensive reference for the GitHub REST API (v3).
> Generated: 2026-05-22 19:30 UTC

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Rate Limits](#rate-limits)
4. [Pagination](#pagination)
5. [Endpoint Reference](#endpoint-reference)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)

---

## Overview

- **Base URL:** `https://api.github.com`
- **Version:** v3 (media type: application/vnd.github.v3+json)
- **Encoding:** All responses are in JSON format
- **Dates:** All timestamps are in ISO 8601 format (UTC)

---

## Authentication

Token-based (Authorization: Bearer <token>), OAuth2, and Basic Auth

### Token-based Authentication

```
Authorization: Bearer ghp_xxxxxxxxxxxxxxxxxxxx
```

Tokens can be created in GitHub Settings > Developer settings > Personal access tokens.
Fine-grained tokens allow scoped access to specific repositories and permissions.

### OAuth2

For applications acting on behalf of users, use the OAuth2 web application flow:
1. Redirect user to `https://github.com/login/oauth/authorize`
2. Receive authorization code callback
3. Exchange code for access token at `POST https://github.com/login/oauth/access_token`

---

## Rate Limits

Unauthenticated: 60 requests/hour. Authenticated: 5,000 requests/hour.

| Authentication | Limit |
|---------------|-------|
| Unauthenticated | 60 requests/hour |
| Authenticated | 5,000 requests/hour |
| GitHub App (installation) | 5,000 requests/hour (scaled) |

Check your rate limit status:

```
GET /rate_limit
Response includes: core, search, graphql limits
```

Rate limit headers are returned in every response:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset` (Unix timestamp)

---

## Pagination

Link header-based, 100 items per page max.

Paginated responses include a `Link` header with `rel` relations:
- `rel="next"` — the next page
- `rel="last"` — the last page
- `rel="first"` — the first page
- `rel="prev"` — the previous page

Use the `per_page` parameter to control page size (max 100, default 30).
Use the `page` parameter to navigate pages.

---

## Endpoint Reference

| Category | Method | Endpoint | Description |
|----------|--------|----------|-------------|
| Repos | `GET` | `/repos/{owner}/{repo}` | Get a repository |
| Repos | `POST` | `/user/repos` | Create a repository |
| Repos | `PATCH` | `/repos/{owner}/{repo}` | Update a repository |
| Repos | `DELETE` | `/repos/{owner}/{repo}` | Delete a repository |
| Issues | `GET` | `/repos/{owner}/{repo}/issues` | List repository issues |
| Issues | `POST` | `/repos/{owner}/{repo}/issues` | Create an issue |
| Issues | `PATCH` | `/repos/{owner}/{repo}/issues/{number}` | Update an issue |
| Pulls | `GET` | `/repos/{owner}/{repo}/pulls` | List pull requests |
| Pulls | `POST` | `/repos/{owner}/{repo}/pulls` | Create a pull request |
| Pulls | `GET` | `/repos/{owner}/{repo}/pulls/{number}` | Get a pull request |
| Pulls | `PUT` | `/repos/{owner}/{repo}/pulls/{number}/merge` | Merge a pull request |
| Users | `GET` | `/users/{username}` | Get a user |
| Users | `GET` | `/user` | Get the authenticated user |
| Search | `GET` | `/search/repositories?q={query}` | Search repositories |
| Search | `GET` | `/search/code?q={query}` | Search code |
| Search | `GET` | `/search/issues?q={query}` | Search issues and pull requests |
| Activity | `GET` | `/repos/{owner}/{repo}/commits` | List commits |
| Activity | `GET` | `/repos/{owner}/{repo}/releases` | List releases |
| Activity | `GET` | `/repos/{owner}/{repo}/forks` | List forks |
| Activity | `POST` | `/repos/{owner}/{repo}/forks` | Create a fork |

---

### Repositories

The Repos API lets you manage repositories on GitHub.

```bash
# Get a repository
curl -H 'Authorization: Bearer TOKEN' \
  https://api.github.com/repos/octocat/Hello-World

# Create a repository
curl -X POST -H 'Authorization: Bearer TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-new-repo","description":"My new repo"}' \
  https://api.github.com/user/repos
```

### Issues

The Issues API enables issue tracking per repository.

```bash
# List issues
curl -H 'Authorization: Bearer TOKEN' \
  https://api.github.com/repos/octocat/Hello-World/issues

# Create an issue
curl -X POST -H 'Authorization: Bearer TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Bug found","body":"Description of the bug"}' \
  https://api.github.com/repos/octocat/Hello-World/issues
```

### Pull Requests

The Pulls API supports creating, reviewing, and merging pull requests.

```bash
# List pull requests
curl -H 'Authorization: Bearer TOKEN' \
  https://api.github.com/repos/octocat/Hello-World/pulls

# Create a pull request
curl -X POST -H 'Authorization: Bearer TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"title":"My PR","head":"feature-branch","base":"main"}' \
  https://api.github.com/repos/octocat/Hello-World/pulls
```

### Users

The Users API provides access to user profiles and settings.

### Search

The Search API provides advanced search across repositories, code, issues, and users.

---

## Error Handling

| Status Code | Meaning |
|-------------|---------|
| `200 OK` | Request succeeded |
| `201 Created` | Resource created successfully |
| `204 No Content` | Request succeeded (no response body) |
| `301 Moved` | Resource has moved (follow `Location` header) |
| `304 Not Modified` | Resource not modified (use conditional requests) |
| `400 Bad Request` | Invalid request body or parameters |
| `401 Unauthorized` | Missing or invalid authentication |
| `403 Forbidden` | Insufficient permissions or rate limited |
| `404 Not Found` | Resource does not exist |
| `409 Conflict` | Conflict with current state (e.g., merge conflict) |
| `422 Unprocessable Entity` | Validation errors |
| `429 Too Many Requests` | Rate limit exceeded |

Error responses include a JSON body with `message` and `documentation_url` fields.

---

## Best Practices

1. **Use Conditional Requests** — Include `If-None-Match` (ETag) and
   `If-Modified-Since` headers to avoid re-downloading unchanged data.
   A `304 Not Modified` response does not count against your rate limit.

2. **Include Authentication** — Authenticated requests get 83x higher rate limits.
   Use token-based auth for scripts and OAuth2 for user-facing apps.

3. **Handle Pagination** — Always check the `Link` header and handle pagination
   for endpoints that return lists of resources.

4. **Use the Correct Media Type** — Send `Accept: application/vnd.github.v3+json`
   for the stable v3 API.

5. **Retry on 429/5xx** — Implement exponential backoff with `Retry-After` headers.
   The `X-RateLimit-Reset` header tells you when your limit resets.

6. **Use GraphQL for Complex Queries** — For fetching related data in a single
   request, the GitHub GraphQL API (v4) is more efficient than multiple REST calls.

7. **Watch for Breaking Changes** — GitHub announces API changes via the
   [developer blog](https://developer.github.com/changes/) and the
   `Sunset` HTTP header on deprecated endpoints.

---

*Documentation generated by a2a api-doc-generator artifact using live ddgr web search.*