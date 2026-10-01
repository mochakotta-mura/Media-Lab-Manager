"""Authentication and authorization application service."""

import hashlib
import hmac
import re
import secrets
import time


class AuthenticationService:
    def __init__(self, database, api_error, session_cookie, cookie_secure, session_seconds,
                 staff_roles, admin_emails, role_by_domain, staff_domains):
        self.db = database
        self.ApiError = api_error
        self.session_cookie = session_cookie
        self.cookie_secure = cookie_secure
        self.session_seconds = session_seconds
        self.staff_roles = staff_roles
        self.admin_emails = admin_emails
        self.role_by_domain = role_by_domain
        self.staff_domains = staff_domains

    def is_admin_email(self, email):
        value = str(email or '').lower()
        return value in self.admin_emails or value.endswith('@krea.medialab.in')

    def role_for_email(self, email):
        value = str(email or '').lower()
        if self.is_admin_email(value):
            return 'admin'
        return self.role_by_domain.get(value.rsplit('@', 1)[-1])

    def is_staff_email(self, email):
        return str(email or '').lower().rsplit('@', 1)[-1] in self.staff_domains

    def is_staff(self, user):
        return user.get('role') in self.staff_roles and self.is_staff_email(user.get('email'))

    def is_admin(self, user):
        return self.is_admin_email(user.get('email'))

    def public_user(self, user):
        email = str(user.get('email', '')).lower()
        stored_role = str(user.get('role') or '').lower()
        if self.is_admin_email(email):
            role = 'admin'
        elif stored_role == 'admin':
            role = self.role_for_email(email) or 'student'
        else:
            role = stored_role or self.role_for_email(email) or 'student'
        return {'id': user['id'], 'kreaId': user['krea_id'], 'name': user['name'],
                'email': user.get('email'), 'role': role}

    @staticmethod
    def hash_pin(pin):
        salt = secrets.token_bytes(16)
        value = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
        return f'scrypt${salt.hex()}${value.hex()}'

    @staticmethod
    def verify_pin(pin, encoded):
        try:
            scheme, salt, expected = encoded.split('$')
            if scheme != 'scrypt':
                return False
            actual = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
            return hmac.compare_digest(actual, bytes.fromhex(expected))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def cookie_header(self, token, max_age):
        secure = '; Secure' if self.cookie_secure else ''
        return f'{self.session_cookie}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}{secure}'

    def current_user(self, handler):
        if handler.headers.get('Authorization'):
            return None
        token = handler.cookies().get(self.session_cookie)
        if not token:
            return None
        row = self.db.connection.execute(
            'SELECT u.*,s.id AS session_id,s.expires_at AS session_expires_at FROM sessions s '
            'JOIN users u ON u.id=s.user_id WHERE s.token_hash=?', (self.token_hash(token),)
        ).fetchone()
        if not row or float(row['session_expires_at']) < time.time() or row['banned']:
            if row:
                self.db.connection.execute('DELETE FROM sessions WHERE id=?', (row['session_id'],))
                self.db.connection.commit()
            return None
        now = time.time()
        self.db.connection.execute('UPDATE sessions SET expires_at=?,last_seen_at=? WHERE id=?', (now + self.session_seconds, now, row['session_id']))
        self.db.connection.commit()
        return self.public_user(dict(row))

    def login(self, handler, data, check_allowed, record_failed, clear_failed):
        email = str(data.get('email', '')).lower().strip()
        pin = str(data.get('pin', ''))
        assigned_role = self.role_for_email(email)
        if not assigned_role or not re.match(r'^[^@\s]+@(?:krea\.ac\.in|krea\.edu\.in|krea\.medialab\.in)$', email):
            raise self.ApiError('Use a valid @krea.ac.in, @krea.edu.in, or @krea.medialab.in email address')
        if len(pin) != 4 or not pin.isdigit():
            raise self.ApiError('PIN must be exactly 4 digits')
        row = self.db.connection.execute('SELECT * FROM users WHERE email=? LIMIT 1', (email,)).fetchone()
        user = dict(row) if row else None
        if not user:
            user = self.db.add_user({'kreaId': email, 'name': email.split('@', 1)[0], 'email': email, 'role': assigned_role})
            user['pin_hash'] = ''
        elif user.get('role') not in self.staff_roles and user.get('role') != assigned_role:
            self.db.connection.execute('UPDATE users SET role=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (assigned_role, user['id']))
            self.db.connection.commit(); user['role'] = assigned_role
        check_allowed(handler.client_address[0], email, user)
        encoded = user.get('pin_hash') or ''
        if encoded:
            if not self.verify_pin(pin, encoded):
                record_failed(handler.client_address[0], email, user)
                raise self.ApiError('Invalid email or PIN', 401)
        else:
            self.db.connection.execute('UPDATE users SET pin_hash=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (self.hash_pin(pin), user['id']))
            self.db.connection.commit()
        if user.get('banned'):
            raise self.ApiError('This account is banned')
        clear_failed(handler.client_address[0], email, user)
        token = secrets.token_hex(32)
        self.db.connection.execute('INSERT INTO sessions(token_hash,user_id,expires_at,last_seen_at) VALUES (?,?,?,?)', (self.token_hash(token), user['id'], time.time() + self.session_seconds, time.time()))
        self.db.connection.commit()
        return handler.send_json(200, {'user': self.public_user(user)}, {'Set-Cookie': self.cookie_header(token, self.session_seconds)})
