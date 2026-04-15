# Front-End Migration to Next.js (Glassmorphism Red)

## Overview
We are migrating the existing Flask templates to a Next.js front-end styled with a **Glassmorphism Red** theme. The new client will consume the current Flask API while delivering a modern, responsive experience.

The Next.js project will be bootstrapped using `create-next-app` with **TypeScript** and **ESLint**.

## Checklist

### 1. Project Setup
- [x] Initialize Next.js project with TypeScript and ESLint.
- [x] Configure base directories (`app/`, `components/`, `lib/`).
- [x] Install and configure Tailwind CSS with Glassmorphism utilities.
- [x] Define environment variables for backend API URL.
- [x] Add `.env.local.example` for frontend configuration.
- [x] Set up Prettier and integrate with ESLint.

### 2. Design System
- [x] Establish Glassmorphism Red color palette and typography.
- [x] Create reusable glass panel component (blur, transparency, red accents).
- [x] Document global styles and theming guidelines.

### 3. Routing and Layouts
- [x] Implement main layout with navigation and auth guard.
- [x] Recreate routes: `/dashboard`, `/settings`, `/send_template`, etc.
- [x] Add error and 404 pages.

### 4. Authentication
- [x] Port login flow; integrate with Flask auth endpoints.
- [x] Persist session via cookies or JWT.
- [x] Protect routes with middleware.

### 5. API Integration
- [x] Build shared API client for Flask backend.
- [ ] Fetch real-time data from `/dashboard/data` using SWR or React Query.
- [ ] Support file uploads (e.g., CSV templates).

### 6. State Management & API Layer
- [x] Choose a global state library (e.g., Zustand or Redux Toolkit).
- [x] Configure API proxy routes to forward requests to the Flask backend.
- [x] Implement centralized error handling for API calls.

### 7. Feature Parity
- [ ] Dashboard charts (Chart.js or equivalent).
- [ ] Notification settings management.
- [ ] Send Templates workflow with CSV preview.
- [ ] Admin tools and logs viewer.

### 8. Testing
- [ ] Unit tests for components and utilities.
- [ ] Integration tests for page behaviors and API calls.
- [ ] End-to-end tests with Playwright or Cypress.
- [ ] Configure GitHub Actions to run frontend linting and tests.

### 9. Performance & Accessibility
- [ ] Optimize images, fonts, and bundles.
- [ ] Ensure ARIA roles and keyboard navigation.
- [ ] Run Lighthouse audits.
- [ ] Verify color contrast meets WCAG AA standards.

### 10. Deployment
- [ ] Configure build pipeline (Vercel or containerized deployment).
- [ ] Update CI/CD to build and deploy the Next.js app.
- [ ] Document deployment steps.

### 11. Documentation
- [x] Update `README.md` with Next.js instructions.
- [ ] Keep this checklist current as tasks are completed.

## State Management & API Proxy Decisions

- Using **Zustand** for lightweight global state; `useAuthStore` holds the session.
- A shared API client handles credentials and redirects unauthorized users to `/login`.
- API proxy routes use Next.js `rewrites` to forward `/api/*` requests to the Flask backend.

