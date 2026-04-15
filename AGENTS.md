# Repository Guidelines

- Follow [PEP 8](https://peps.python.org/pep-0008/) style with 4-space indentation.
- Keep imports sorted and remove unused ones.
- Check for circular imports by running `pycycle --here` before committing.
- Run `pytest` and ensure all tests pass before committing.
- `TWILIO_SERVICE_SID` is optional. When set, use the messaging service; otherwise send from `TWILIO_WHATSAPP_NUMBER`.
- Keep `README.md` and `AGENTS.md` up to date; remove outdated info and add new requirements.
- Track the migration to a Next.js frontend in `MIGRATION.md` and keep its checklist current.
- Document state management and API proxy decisions for the Next.js frontend in `MIGRATION.md`.
- Run `npm test` for the Next.js frontend (in `frontend/`) when client code is present.
- Run `npm run lint` for the Next.js frontend (in `frontend/`) when client code is present.
- Format frontend code with Prettier using `npm run format`.
- Keep Next.js `error.tsx` and `not-found.tsx` pages up to date.
- Use the `GlassPanel` component and Glassmorphism Red palette for translucent UI elements in the Next.js frontend.
- Wrap protected Next.js pages with the `AuthGuard` component and keep
  `NavBar` links up to date with available routes.
- Protect routes server-side with Next.js middleware that checks the
  `session` cookie.
- Use Zustand for global state management in the Next.js frontend.
- Store the admin password as a bcrypt hash in the `ADMIN_PASSWORD_HASH` env var.
- Maintain the User Dashboard development checklist in `README.md` and keep tasks current.
- Maintain the `/settings` page for notification preferences and keep related tests updated.
- Ensure `/dashboard/data` powers real-time charts and keep its tests current.
- Set log verbosity with the `LOG_LEVEL` env var. Third-party loggers like Twilio are capped at `WARNING`.
- Use Supervisor for process management; keep the Supervisor instructions in `README.md` current.
- Proxy `/api/*` requests through Next.js `rewrites` to the Flask backend and keep the configuration current.
