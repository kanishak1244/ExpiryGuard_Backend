# DawaiFlow public website (`dawaiflow.com`)

The marketing website only. It is independent of the backend, the web app and the Flutter app:
a static Vite + React + TypeScript + Tailwind site with no API calls and no secrets. Pilot requests
and contact go through WhatsApp / email links (`src/config/appConfig.ts`).

| Domain | Serves |
|---|---|
| `https://dawaiflow.com` | This website (static host) |
| `https://api.dawaiflow.com` | Backend API, web app at `/web`, used by the Flutter app |

## Develop and build

Node.js 20 or newer.

```bash
npm ci            # install exact versions from package-lock.json
npm run dev       # http://localhost:3000
npm run build     # production build -> dist/
npm run preview   # serve dist/ locally to check it
```

- Build command: `npm ci && npm run build`
- Output directory: `dist/`
- Root folder (in the repository): `public_site/`
- Environment variables: none (see `.env.example`)

`public/` is copied into `dist/` as is: `robots.txt`, `sitemap.xml`, `favicon.svg`, images and
`_redirects`.

## Redirects (`public/_redirects`)

Used by Cloudflare Pages (and Netlify). They keep old links working once `dawaiflow.com` is served by
the static host instead of the backend:

- `/web`, `/web/*` -> `https://api.dawaiflow.com/web/...` (the web app calls its API on the domain it
  runs on, so it must run on `api.dawaiflow.com`)
- `/docs`, `/health` -> the API domain
- `/terms`, `/privacy`, `/data-policy`, `/disclaimer`, `/contact`, ... -> the matching homepage section

## Deploy to `dawaiflow.com` (Cloudflare Pages, free)

The domain's DNS is already on Cloudflare. Steps (done by the owner in the Cloudflare dashboard):

1. Workers & Pages -> Create -> Pages -> Connect to Git -> choose this repository.
2. Production branch: `main`. Root directory: `public_site`. Build command: `npm ci && npm run build`.
   Build output directory: `dist`. Environment variable `NODE_VERSION` = `20` (no other variables).
3. Deploy, then open the `*.pages.dev` address and check the page, images, WhatsApp buttons and
   `/web` redirect.
4. Custom domains -> add `dawaiflow.com` (and `www.dawaiflow.com` if wanted). Cloudflare replaces the
   current `dawaiflow.com` DNS record (which points to Railway) with the Pages one.
5. Leave the `api` DNS record untouched: `api.dawaiflow.com` stays on Railway.
6. In Railway, remove `dawaiflow.com` from the backend service's custom domains only after step 4 works
   (keep `api.dawaiflow.com`).

Until step 4, `dawaiflow.com` keeps working exactly as before (served by the backend from the committed
`dist/`).

## Note on the backend copy

The backend (`app.py`) also serves `public_site/dist/` at `/` so `api.dawaiflow.com/` shows the site.
That is unchanged; rebuild and commit `dist/` if you want the backend copy updated too.
