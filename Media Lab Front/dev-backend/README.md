# Media Lab Manager development backend

This is a temporary, development-only HTTP server. It is isolated from the team repository and writes only to `data/media-lab-dev.sqlite`. It does not use or modify the production database.

Requirements: Node.js 22 or newer. Node.js 24 is recommended because this server uses the built-in `node:sqlite` module and has no npm dependencies.

Start it from this directory with:

```powershell
node server.js
```

The API listens on `http://localhost:3000`. In the browser console, before opening the frontend pages, run:

```js
localStorage.setItem('mlmApiBase', 'http://localhost:3000/api');
```

The frontend API adapter will then use the mock server. Authentication is intentionally a placeholder: the frontend creates a local development user through `POST /api/users`; no Google authentication is implemented.
