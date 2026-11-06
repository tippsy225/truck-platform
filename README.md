![Tests](https://github.com/tippsy225/truck-platform/actions/workflows/tests.yml/badge.svg)

## API

Interactive documentation lives at `/api/docs/` when the site is running. Sign in with
`POST /api/auth/token/`, then send the token as `Authorization: Token <token>`.

- REST API built with Django REST Framework and documented with OpenAPI (drf-spectacular)
- Token login with rate limiting, role-based permissions, and pagination
- Phone numbers are only exposed to the two people on a booking, and only after both platform fees are paid
- Tested with 118 automated tests covering pricing, fees and discounts, expiry and payment deadlines,
  escrow and disputes, referrals, ratings, and the API's permissions

## Run the tests

    python manage.py test
