# Production database user administration

These instructions apply to the SQLite database mounted at
`/data/recrbro.db` on the Railway API service.

Connect to the production API container:

```sh
railway link
railway ssh
```

Before making changes, create a backup:

```sh
cp /data/recrbro.db "/data/recrbro.db.backup-$(date +%Y%m%d-%H%M%S)"
```

Open the SQLite command-line interface:

```sh
uv run python -m sqlite3 /data/recrbro.db
```

## Update a user to Premium

Replace `user@example.com` with the user's email address:

```sql
BEGIN;

UPDATE users
SET plan = 'premium',
    result_limit = 10
WHERE lower(email) = lower('user@example.com');

SELECT id, name, email, plan, result_limit
FROM users
WHERE lower(email) = lower('user@example.com');

COMMIT;
```

The update changes the user's plan but does not create a payment or add credit
to the user's balance ledger.

## List all users

```sql
.headers on
.mode column

SELECT id,
       name,
       email,
       plan,
       result_limit,
       created_at
FROM users
ORDER BY id;
```

## Delete a user

Deleting a user is irreversible. Related sessions, profiles, searches, offers,
usage records, payments, balance events, and application statuses are removed
through foreign-key cascades.

First verify the target:

```sql
SELECT id, name, email, plan
FROM users
WHERE lower(email) = lower('user@example.com');
```

Then delete it:

```sql
PRAGMA foreign_keys = ON;
BEGIN;

DELETE FROM users
WHERE lower(email) = lower('user@example.com');

SELECT changes() AS deleted_users;

COMMIT;
```

`deleted_users` must be `1`. If it is `0`, no matching user was found. If it is
greater than `1`, roll back instead of committing:

```sql
ROLLBACK;
```

Exit SQLite with:

```sql
.quit
```
