## Media Lab Equipment Lending Software
By Arja S, Joyal Liju Jacob, Murali Krishnan, Upasana Rai.
<br> For COMP350: Software Design Practical 2026

## Local application

The only HTTP backend is `MLM.integration/server/server.py`. It serves the maintained frontend from `Media Lab Front` and uses the SQLite database in `MLM.Database/media-lab.sqlite`.

```powershell
python MLM.integration/server/server.py
```

Login uses a Krea email and four-digit PIN. The PIN is persisted as an scrypt hash and sessions are persisted in SQLite. The browser receives only an HttpOnly session cookie; no bearer token is stored in browser storage. `@krea.edu.in` faculty and Media Lab roles can access staff APIs; administrator access is limited to `demo.admin@krea.edu.in`, `bing@krea.edu.in`, and addresses ending in `@krea.medialab.in`.

For local HTTP development, run with `COOKIE_SECURE=false`. Production must run behind HTTPS with `COOKIE_SECURE=true` (the default).

Google authentication is not implemented.
    
