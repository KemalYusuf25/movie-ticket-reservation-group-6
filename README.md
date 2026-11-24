# Büyülü Salon — Movie Ticket Reservation System (Group 6)

CMPE341 Database Design & Management project.
A web application where customers browse movies, pick seats on a seat map and buy
tickets, and administrators manage movies, cinemas, halls, screenings, users and
reservations. Built with **PostgreSQL 16**, **Python / Flask** and **Docker**.

## Quick start

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose).

```bash
git clone https://github.com/KemalYusuf25/movie-ticket-reservation-group-6.git
cd movie-ticket-reservation-group-6
docker compose up
```

The first start takes a minute (images are downloaded and the database is created with
all tables and sample data). Then open:

**http://localhost:8080**

## Test accounts

| Role     | Username  | Password      |
|----------|-----------|---------------|
| Admin    | `admin`   | `Admin123!`   |
| Admin    | `manager` | `Manager123!` |
| Customer | `ayse`    | `Ayse123!`    |
| Customer | `mehmet`  | `Mehmet123!`  |
| Customer | `zeynep`  | `Zeynep123!`  |

New customer accounts can also be created with **Sign up**.

## Features

**Customer**
- Browse movies (filter by genre), see screenings with format (2D/3D/IMAX/4DX) and language (dubbed/subtitled)
- Interactive seat map: free / in someone's cart / in your cart / sold
- Full or student ticket for every seat (student tickets are 25% off)
- Selected seats are held for **5 minutes**; other users see them as taken. If the
  purchase is not completed in time the seats are released automatically
- My Tickets: see and cancel reservations; edit profile and password

**Admin** (role `admin`)
- Dashboard: totals, revenue per movie, movies without screenings
- Insert / update / delete movies (with poster image stored in the database), cinemas,
  halls (seats are generated automatically), screenings and users (change role)
- See and cancel any reservation

## Database rules (enforced by PostgreSQL, see `db/01_schema.sql`)

- PK / FK / UNIQUE / CHECK constraints on all 8 tables
  (`users`, `movie`, `cinema`, `hall`, `seat`, `screening`, `reservation`, `ticket`)
- A seat can be sold only once per screening (`UNIQUE (screening_id, seat_id)`)
- Triggers: a ticket's seat must be in the screening's hall; expired carts do not block
  seats; an expired cart cannot be confirmed; cancelling a reservation releases its seats;
  the price of a screening cannot change after tickets are sold
- `ticket_price()` computes the price (student −25%); `release_expired_holds()` cleans
  expired carts
- Passwords are stored as salted scrypt hashes (`werkzeug.security`)

## Project structure

```
├── docker-compose.yml       # db + web services
├── .env.example             # optional settings (port, passwords)
├── db/
│   ├── 01_schema.sql        # tables, constraints, functions, triggers
│   └── 02_data.sql          # sample data
├── report/
│   └── queries.sql          # report queries (JOIN, GROUP BY/ORDER BY, subquery)
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py               # Flask routes and SQL
    ├── templates/           # Jinja HTML pages (customer + admin/)
    └── static/              # CSS, Bootstrap (bundled, works offline)
```

## Useful commands

| What | Command |
|---|---|
| Start in the background | `docker compose up -d` |
| Stop | `docker compose down` |
| Reset the database to the sample data | `docker compose down -v` then `docker compose up` |
| Rebuild after changing the code | `docker compose up --build` |
| Logs | `docker compose logs -f web` |

The SQL files in `db/` run **only when the database volume is created for the first
time**; use `docker compose down -v` to start again from scratch.

To connect with DBeaver / pgAdmin: host `localhost`, port `5433`, database `cinema`,
user `cinema`, password `cinema123`.

## Configuration

Copy `.env.example` to `.env` to change settings:

| Variable | Default | Meaning |
|---|---|---|
| `WEB_PORT` | `8080` | Port of the website on the host (use `80` on the server) |
| `DB_PASSWORD` | `cinema123` | PostgreSQL password |
| `SECRET_KEY` | (dev value) | Flask session signing key — change it in production |

## Team

Group 6 — CMPE341, Atılım University, Fall 2026–2027

23244710037 Berat Özkaner 
