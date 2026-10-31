# Supabase fixtures (STORAGE_BACKEND=supabase contract tests)

Responses the Supabase Auth and Storage REST APIs are assumed to give, served by `httpx.MockTransport` in
`tests/test_storage_supabase.py`. **ASSUMED SHAPE**, not recorded: the build session had no Supabase credentials and
could not reach supabase.com, so every shape is read off the official Python clients' source (`storage3` 2.33.0,
`supabase_auth` 2.33.0 on PyPI). Each file's `_shape` names its source; `_source` names the function. Keys starting with
`_` are stripped before a test serves the body.

| File | Request it answers |
|------|--------------------|
| `auth_token_password.json` | `POST /auth/v1/token?grant_type=password` with the storage writer's email and password |
| `auth_token_refresh.json` | `POST /auth/v1/token?grant_type=refresh_token` |
| `auth_error_invalid_credentials.json` | the password grant with a wrong password (HTTP 400 assumed) |
| `storage_upload.json` | `POST /storage/v1/object/<bucket>/<key>` multipart upload with `x-upsert: true` (`Key` is `<bucket>/<key>`) |
| `storage_error_rls.json` | an upload RLS refuses (HTTP 400 or 403; the adapter reports both statuses) |
| `storage_error_not_found.json` | `GET /storage/v1/object/public/<bucket>/<key>` for a missing object |

At go-live, record one of each with the real project (the upload, a public read, and a refused upload from a user without
the policy) and replace these files; if a shape differs, fix `adapters/storage/supabase.py`, not the workers.
