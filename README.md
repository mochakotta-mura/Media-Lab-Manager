## Media Lab Equipment Lending Software
By Arja S, Joyal Liju Jacob, Murali Krishnan, Upasana Rai.
<br> For COMP350: Software Design Practical 2026

## Local application

The HTTP server is in `server/server.js` and serves the maintained frontend from `Media Lab Front`. Start it after installing the database dependency:

```powershell
cd MLM.Database
npm.cmd install
cd ..
node server/server.js
```

The browser login uses account type, Krea email, and a four-digit PIN. The backend validates the account type and email domain, verifies the PIN against a scrypt hash, and creates an HttpOnly server session plus a file-compatible bearer session token.

```powershell
node server/server.js
```

Students must use `@krea.ac.in`; Faculty and Media Lab accounts must use `@krea.edu.in`. The PIN is never stored as plaintext. Opening `Media Lab Front/index.html` directly is supported while the backend is running on `http://localhost:3000`.

The current authentication implementation is the account-type, Krea-domain, and four-digit PIN flow. It creates a scrypt hash for a first-time account, returns a bearer session token, and stores the authenticated user in the frontend session. Equipment and reservation requests continue through the existing database command module; the server always uses the authenticated user's database ID for a request. Google authentication is not currently implemented.
    
