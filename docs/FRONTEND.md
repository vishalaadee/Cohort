# Frontend

Two HTML files sharing one design system. No build step — served as static
files by Caddy. Migrating to React + TypeScript as features grow, but the
design tokens and layout patterns stay the same.

## Structure

```
frontend/
├─ public/
│  └─ index.html     Landing page — the sales artifact.
│                    Hero with live drive pipeline, before/after strip,
│                    live dashboard preview (calls /api, falls back to demo),
│                    feature grid, value section.
└─ app/
   └─ app.html       The product app — hash-routed SPA.
                     Login (Google / password / claim tabs), admin console
                     (dashboard, students, CSV import, companies), student
                     portal (my applications, drives).
```

## Design system

Typefaces (loaded from Google Fonts):
- **Display:** Bricolage Grotesque — headings, stats, brand
- **Body:** Inter — prose, labels, buttons
- **Mono:** IBM Plex Mono — data, codes, chips, eyebrows

Palette (`--var` names match CSS custom properties):
- `--ink` (#0E1B33) — primary text, dark surfaces (sidebar, hero)
- `--paper` (#F4F6FB) — page background
- `--panel` (#FFFFFF) — card/panel surfaces
- `--indigo` (#3B4CC7) — primary action, links, active states
- `--gold` (#E6A02C) — accent, tier-1 chips, value stats
- `--teal` (#12968A) — positive states, placement rates, live indicators
- `--rose` (#C4485F) — errors, destructive actions
- `--slate` (#5B6788) — secondary text, labels
- `--line` (#E3E7F1) — borders, dividers

Components (reused across both files):
- `.btn` / `.btn-primary` / `.btn-ghost` — buttons
- `.chip` + `.ok` / `.warn` / `.mut` / `.t1` / `.t2` — status/category tags
- `.stat` (`.k` + `.v`) — metric cards
- `.panel` + `.panel-t` — content sections
- `.fn` (`.lbl` + `.track` + `.fill` + `.n`) — pipeline funnel bars
- `.drop` — file upload zone
- `.toast` — notification overlay

## How routing works (app.html)

Hash-based SPA router. Each route maps to a view function that:
1. Calls `Shell(contentHTML, activeNavHref)` to render the sidebar + main area.
2. Fetches data from `/api/*` using the `api()` helper (auto-attaches JWT).
3. Fills the content area with the results.

```javascript
const ROUTES = {
  "#/login": LoginView,
  "#/dashboard": DashboardView,
  "#/students": StudentsView,
  "#/import": ImportView,
  "#/companies": CompaniesView,
  "#/home": StudentHomeView,
};
```

Navigation is role-aware: staff (owner/admin/sub_admin) see dashboard +
students + import + companies; students see my-placements + drives.
Unauthorized access to staff routes redirects to the student home.

## Adding a new view

1. Write the view function (e.g. `async function FeedbackView()`).
2. Call `Shell(yourHTML, "#/feedback")` to get the sidebar.
3. Add to `ROUTES` and to the appropriate nav array (`STAFF_NAV` or
   `STUDENT_NAV`).
4. Fetch data with `api("/api/your-endpoint")` — handles JWT and 401
   auto-logout.

## Auth flow in the UI

`/api/auth/config` is called on load — returns `google_client_id` (the
Google button renders only if this is set) and `dev_fallback`. The JWT is
stored in `localStorage` as `cohort_auth` and sent on every API call.
Sessions expire after 8 hours (configurable).

## Moving to React

When the feature count justifies a build step:
1. Scaffold with Vite + React + TypeScript in `frontend/`.
2. Move the CSS custom properties and component patterns into a proper design
   system (shadcn/ui or a small custom library).
3. Use TanStack Query for server state (replaces the `api()` helper).
4. Keep the same hash-based or push-state routing.
5. Update the Caddy config to serve the built output.

The design tokens, palette, typography, and layout system carry over
unchanged.
