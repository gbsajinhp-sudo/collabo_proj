# Current Shared Deployment

## MotherDuck

- Database: `gyeonggi_industryDB`
- Physical schema: existing `main`
- Application access: read-only
- Runtime variable: `MOTHERDUCK_READONLY_TOKEN`
- DATA_in and DATA_out: team ownership labels, not new physical schemas

The hackathon repository does not contain a database uploader or token provisioning script. Do not alter the shared production database. Create a new versioned database for any data-changing experiment.

## Vercel responsibility

- human3 prepares a Preview candidate.
- human1 verifies environment variables, API smoke tests, UI behavior and rollback target.
- human1 performs the final Production deployment.

## Required verification

```text
/api/health
/api/meta
/api/industries
/api/regions
/api/summary
/api/map/cells
```

The frontend must never receive a MotherDuck token.
