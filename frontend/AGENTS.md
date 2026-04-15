# Frontend Guidelines

- Use Prettier for formatting (`npm run format`).
- Keep `.env.local.example` current with required variables.
- Run `npm test` and `npm run lint` before committing.
- Use the `GlassPanel` component for translucent surfaces and keep the Glassmorphism Red palette consistent.
- Wrap protected pages with `AuthGuard` and ensure `NavBar` links reflect
  all available routes.
- Guard server-side routes with `middleware.ts` and the `session` cookie.
- Manage global state with Zustand stores.
- Maintain custom `error` and `not-found` pages.
- API requests should use `/api` relative paths; `next.config.ts` rewrites them to the Flask backend.
