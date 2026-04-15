# Moeen AI Frontend

This Next.js app provides the Glassmorphism Red interface for Moeen AI and consumes the existing Flask API.

## Development

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

## Routing

Navigation and access control are handled by a `NavBar`, cookie-based
`AuthGuard`, and server-side middleware that verifies the `session` cookie.
Protected placeholder pages include:

- `/dashboard`
- `/settings`
- `/send_template`

The app also includes a custom `not-found` page and an `error` boundary for unexpected issues.

The `/login` page posts credentials to the Flask backend and stores the session via cookies.

## State Management & API

- Global state uses a lightweight Zustand store (`useAuthStore`).
- API calls go through `lib/api.ts`, which uses `/api` paths that Next.js rewrites to the Flask backend and includes credentials with centralized error handling.

## Design System

- **Color Palette**: uses a Glassmorphism Red accent (`#ff4d4d`) with translucent white backgrounds.
- **Typography**: default font is `Inter` for a clean modern look.
- **Glass Panel**: use the `GlassPanel` component for frosted surfaces.

## Scripts

- `npm run lint` – lint the codebase
- `npm test` – run frontend tests (none yet)
- `npm run format` – check formatting with Prettier
- `npm run format:fix` – auto-format files
