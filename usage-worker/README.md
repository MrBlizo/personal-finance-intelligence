# PFI usage counter

A tiny Cloudflare Worker that counts how many PFI installs are active each
week. The app only talks to it when the user has said yes (first start or
Settings › Privacy). It receives three values: a random id made on the PC,
the app version and the language. It stores one row per id and week and
nothing else. No IP addresses or other headers are kept.

## Set up (free Cloudflare plan)

You need a Cloudflare account and Node.js.

```bat
cd usage-worker
npx wrangler login
npx wrangler d1 create pfi-usage
```

Copy the printed `database_id` into `wrangler.toml`, then:

```bat
npx wrangler d1 execute pfi-usage --remote --file=schema.sql
npx wrangler secret put STATS_KEY
npx wrangler deploy
```

`STATS_KEY` is a password you choose for reading the numbers; it is typed
into wrangler, never stored in the repository. `deploy` prints the address,
e.g. `https://pfi-usage.<your-subdomain>.workers.dev`.

Put that address followed by `/ping` into `USAGE_URL` in
`backend/app/services/usage.py` and build the app. Until `USAGE_URL` is set,
the app does not show the question at all.

## Read the numbers

```bat
curl -H "Authorization: Bearer YOUR_STATS_KEY" https://pfi-usage.<your-subdomain>.workers.dev/stats
```

`weeks` lists active installs per week (people who said no are not
counted, so this is a lower bound).

## Test it

```bat
curl -X POST https://pfi-usage.<your-subdomain>.workers.dev/ping -H "Content-Type: application/json" -d "{\"id\":\"0123456789abcdef0123456789abcdef\",\"version\":\"0.5.0\",\"lang\":\"en\"}"
```

A `204` answer means the ping was counted.
