# AUTOROSTER

Django JSON API (`/api/...`) plus a plain HTML/CSS/JS single-page frontend in `web/`
(no build step, hash routing), served by Django on the same origin.

```bash
venv/Scripts/python manage.py runserver   # open http://127.0.0.1:8000/
venv/Scripts/python manage.py test roster.tests_endpoints
node web/app.test.js
```
