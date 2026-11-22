"""
CMPE341 - Movie Ticket Reservation System (Group 6)
Flask web application.

Architecture: the browser sends a request -> Flask runs plain SQL on
PostgreSQL through psycopg2 -> the result is rendered into an HTML page
with a Jinja template. Business rules (seat holds, prices, cancellations)
are enforced by the database itself (constraints and triggers in
db/01_schema.sql); the application only reports their errors nicely.
"""
import functools
import os

import psycopg2
import psycopg2.extras
from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024         # poster upload limit: 10 MB
DATABASE_URL = os.environ.get("DATABASE_URL",
                              "postgresql://cinema:cinema123@localhost:5432/cinema")

FORMATS = ["2D", "3D", "IMAX", "4DX"]
LANGUAGES = {"dubbed": "Dubbed", "subtitled": "Subtitled"}
AGE_RATINGS = ["G", "7+", "13+", "18+"]
TICKET_TYPES = {"full": "Full", "student": "Student (-25%)"}
MAX_SEATS_PER_BOOKING = 10


# =====================================================================
# Database helpers
# =====================================================================
def get_db():
    """One connection per request, rows are returned as dictionaries."""
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    """Run a SELECT and return all rows (or only the first one)."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    get_db().commit()
    if one:
        return rows[0] if rows else None
    return rows


def db_error_message(err):
    """Turn a PostgreSQL error into a short message for the user."""
    code = getattr(err, "pgcode", None)
    diag = getattr(err, "diag", None)
    constraint = diag.constraint_name if diag else None
    if code == "P0001":                                   # RAISE EXCEPTION in a trigger
        return diag.message_primary
    if code == "23505":                                   # unique_violation
        return {
            "uq_users_username": "This username is already taken.",
            "uq_users_email": "This e-mail address is already registered.",
            "uq_ticket_seat": "Sorry, one of the selected seats has just been taken by someone else.",
            "uq_hall_name": "This cinema already has a hall with that name.",
            "uq_screening_hall_time": "This hall already has a screening at that time.",
            "uq_seat": "This seat already exists.",
        }.get(constraint, "This record already exists.")
    if code == "23503":                                   # foreign_key_violation
        return "This record is still used by other records, so it cannot be deleted."
    if code == "23514":                                   # check_violation
        return {
            "chk_users_phone": "Phone number must contain 10-15 digits (an optional + at the start).",
            "chk_screening_price": "Price cannot be negative.",
            "chk_movie_duration": "Duration must be greater than zero.",
        }.get(constraint, "One of the values is not valid.")
    if code == "23502":                                   # not_null_violation
        return "Please fill in all required fields."
    if code == "22P02" or code == "22007" or code == "22008":
        return "One of the values has the wrong format."
    return "Database error: " + (diag.message_primary if diag else str(err))


def modify(sql, params=(), success=None):
    """Run one INSERT/UPDATE/DELETE in its own transaction.
    Returns the RETURNING row (or True) on success, None on error."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone() if cur.description else None
        db.commit()
    except psycopg2.Error as err:
        db.rollback()
        flash(db_error_message(err), "danger")
        return None
    if success:
        flash(success, "success")
    return row if row is not None else True


def release_expired_holds():
    """Delete carts whose 5 minute hold is over (function in the schema)."""
    query("SELECT release_expired_holds() AS released")


# =====================================================================
# Authentication and authorization
# =====================================================================
@app.before_request
def load_user():
    g.user = None
    if "user_id" in session:
        g.user = query("SELECT user_id, username, full_name, email, phone, role "
                       "FROM users WHERE user_id = %s", (session["user_id"],), one=True)
        if g.user is None:
            session.clear()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.route("/register", methods=["GET", "POST"])
def register():
    form = request.form
    if request.method == "POST":
        if len(form.get("password", "")) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif form.get("password") != form.get("password2"):
            flash("Passwords do not match.", "danger")
        else:
            row = modify(
                "INSERT INTO users (username, password_hash, full_name, email, phone, role) "
                "VALUES (%s, %s, %s, %s, %s, 'customer') RETURNING user_id",
                (form["username"].strip(), generate_password_hash(form["password"]),
                 form["full_name"].strip(), form["email"].strip().lower(),
                 form["phone"].strip().replace(" ", "")))
            if row:
                session.clear()
                session["user_id"] = row["user_id"]
                flash("Welcome! Your account has been created.", "success")
                return redirect(url_for("index"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = query("SELECT user_id, password_hash FROM users WHERE username = %s",
                     (request.form["username"].strip(),), one=True)
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["user_id"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") else url_for("index"))
        flash("Wrong username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        f = request.form
        ok = modify("UPDATE users SET full_name = %s, email = %s, phone = %s WHERE user_id = %s",
                    (f["full_name"].strip(), f["email"].strip().lower(),
                     f["phone"].strip().replace(" ", ""), g.user["user_id"]))
        if ok and f.get("new_password"):
            if len(f["new_password"]) < 6:
                flash("New password must be at least 6 characters.", "danger")
                return redirect(url_for("profile"))
            modify("UPDATE users SET password_hash = %s WHERE user_id = %s",
                   (generate_password_hash(f["new_password"]), g.user["user_id"]))
        if ok:
            flash("Your profile has been updated.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html")


# =====================================================================
# Public pages: movies and screenings
# =====================================================================
@app.route("/")
def index():
    genre = request.args.get("genre", "")
    movies = query("""
        SELECT m.movie_id, m.title, m.director, m.duration_min, m.age_rating,
               m.genre, m.release_date, (m.poster IS NOT NULL) AS has_poster,
               (SELECT COUNT(*) FROM screening s
                 WHERE s.movie_id = m.movie_id AND s.start_time > now()) AS upcoming
        FROM movie m
        WHERE (%s = '' OR m.genre = %s)
        ORDER BY upcoming DESC, m.title""", (genre, genre))
    genres = query("SELECT DISTINCT genre FROM movie ORDER BY genre")
    return render_template("index.html", movies=movies, genres=genres, genre=genre)


@app.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    movie = query("SELECT *, (poster IS NOT NULL) AS has_poster FROM movie WHERE movie_id = %s",
                  (movie_id,), one=True)
    if movie is None:
        abort(404)
    screenings = query("""
        SELECT s.screening_id, s.start_time, s.format, s.language, s.price,
               h.hall_name, c.name AS cinema, c.city,
               (SELECT COUNT(*) FROM seat se WHERE se.hall_id = h.hall_id)
             - (SELECT COUNT(*) FROM ticket t WHERE t.screening_id = s.screening_id) AS free_seats
        FROM screening s
        JOIN hall h   ON h.hall_id   = s.hall_id
        JOIN cinema c ON c.cinema_id = h.cinema_id
        WHERE s.movie_id = %s AND s.start_time > now()
        ORDER BY c.city, s.start_time""", (movie_id,))
    return render_template("movie.html", movie=movie, screenings=screenings)


PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600">
<rect width="400" height="600" fill="#1f1538"/><rect x="20" y="20" width="360" height="560" fill="none"
stroke="#4a3a80" stroke-width="2" stroke-dasharray="8 8"/><text x="200" y="300" fill="#a99dc9"
font-family="Georgia, serif" font-size="30" text-anchor="middle">No poster</text><text x="200" y="250" fill="#e8c26b" font-size="34" text-anchor="middle">✦</text></svg>"""


def image_mimetype(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@app.route("/poster/<int:movie_id>")
def poster(movie_id):
    row = query("SELECT poster FROM movie WHERE movie_id = %s", (movie_id,), one=True)
    if row is None or row["poster"] is None:
        resp = Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")
    else:
        data = bytes(row["poster"])
        resp = Response(data, mimetype=image_mimetype(data) or "application/octet-stream")
    # no-cache + ETag: the browser always asks again, so a new poster shows up at once
    resp.headers["Cache-Control"] = "no-cache"
    resp.add_etag()
    return resp.make_conditional(request)


# =====================================================================
# Booking: seat map -> cart (5 minute hold) -> confirm / cancel
# =====================================================================
def screening_info(screening_id):
    return query("""
        SELECT s.*, m.title, m.movie_id, m.duration_min, m.age_rating,
               h.hall_name, c.name AS cinema, c.city,
               (s.start_time > now()) AS is_future
        FROM screening s
        JOIN movie m  ON m.movie_id  = s.movie_id
        JOIN hall h   ON h.hall_id   = s.hall_id
        JOIN cinema c ON c.cinema_id = h.cinema_id
        WHERE s.screening_id = %s""", (screening_id,), one=True)


@app.route("/screening/<int:screening_id>")
@login_required
def seat_map(screening_id):
    release_expired_holds()
    scr = screening_info(screening_id)
    if scr is None:
        abort(404)
    seats = query("""
        SELECT se.seat_id, se.row_letter, se.seat_number,
               CASE WHEN t.ticket_id IS NULL      THEN 'free'
                    WHEN r.status = 'confirmed'   THEN 'sold'
                    WHEN r.user_id = %s           THEN 'mine'
                    ELSE 'held' END AS state
        FROM seat se
        LEFT JOIN ticket t      ON t.seat_id = se.seat_id AND t.screening_id = %s
        LEFT JOIN reservation r ON r.reservation_id = t.reservation_id
        WHERE se.hall_id = %s
        ORDER BY se.row_letter, se.seat_number""",
                  (g.user["user_id"], screening_id, scr["hall_id"]))
    rows = {}
    for s in seats:
        rows.setdefault(s["row_letter"], []).append(s)
    student_price = query("SELECT ticket_price(%s, 'student') AS p", (scr["price"],), one=True)["p"]
    return render_template("seats.html", scr=scr, rows=rows, student_price=student_price,
                           max_seats=MAX_SEATS_PER_BOOKING)


@app.route("/screening/<int:screening_id>/book", methods=["POST"])
@login_required
def book(screening_id):
    scr = screening_info(screening_id)
    if scr is None:
        abort(404)
    if not scr["is_future"]:
        flash("This screening has already started.", "danger")
        return redirect(url_for("movie_detail", movie_id=scr["movie_id"]))
    chosen = []
    for key, value in request.form.items():
        if key.startswith("type_") and value in TICKET_TYPES:
            chosen.append((int(key[5:]), value))
    if not chosen:
        flash("Please select at least one seat.", "warning")
        return redirect(url_for("seat_map", screening_id=screening_id))
    if len(chosen) > MAX_SEATS_PER_BOOKING:
        flash(f"You can book at most {MAX_SEATS_PER_BOOKING} seats at once.", "warning")
        return redirect(url_for("seat_map", screening_id=screening_id))

    db = get_db()
    try:                     # reservation + all its tickets in ONE transaction
        with db.cursor() as cur:
            cur.execute("INSERT INTO reservation (user_id) VALUES (%s) RETURNING reservation_id",
                        (g.user["user_id"],))
            reservation_id = cur.fetchone()["reservation_id"]
            for seat_id, ticket_type in chosen:
                cur.execute("INSERT INTO ticket (reservation_id, screening_id, seat_id, ticket_type) "
                            "VALUES (%s, %s, %s, %s)",
                            (reservation_id, screening_id, seat_id, ticket_type))
        db.commit()
    except psycopg2.Error as err:
        db.rollback()
        flash(db_error_message(err), "danger")
        return redirect(url_for("seat_map", screening_id=screening_id))
    flash("Seats are held for you for 5 minutes. Please complete your purchase.", "info")
    return redirect(url_for("checkout", reservation_id=reservation_id))


def reservation_tickets(reservation_id):
    return query("""
        SELECT t.ticket_id, t.ticket_type, se.row_letter, se.seat_number,
               s.screening_id, s.start_time, s.format, s.language, s.price,
               ticket_price(s.price, t.ticket_type) AS paid,
               m.title, m.movie_id, h.hall_name, c.name AS cinema, c.city
        FROM ticket t
        JOIN seat se     ON se.seat_id     = t.seat_id
        JOIN screening s ON s.screening_id = t.screening_id
        JOIN movie m     ON m.movie_id     = s.movie_id
        JOIN hall h      ON h.hall_id      = s.hall_id
        JOIN cinema c    ON c.cinema_id    = h.cinema_id
        WHERE t.reservation_id = %s
        ORDER BY se.row_letter, se.seat_number""", (reservation_id,))


@app.route("/checkout/<int:reservation_id>", methods=["GET", "POST"])
@login_required
def checkout(reservation_id):
    release_expired_holds()
    res = query("""
        SELECT reservation_id, user_id, status, expires_at,
               GREATEST(0, EXTRACT(EPOCH FROM (expires_at - now())))::int AS seconds_left
        FROM reservation WHERE reservation_id = %s""", (reservation_id,), one=True)
    if res is None or res["user_id"] != g.user["user_id"]:
        flash("Your 5 minute hold has expired and the seats were released. Please select again.",
              "warning")
        return redirect(url_for("index"))
    if res["status"] != "pending":
        return redirect(url_for("my_reservations"))

    if request.method == "POST":
        if request.form.get("action") == "confirm":
            if modify("UPDATE reservation SET status = 'confirmed' WHERE reservation_id = %s",
                      (reservation_id,), success="Payment completed. Enjoy the movie!"):
                return redirect(url_for("my_reservations"))
        else:
            modify("UPDATE reservation SET status = 'cancelled' WHERE reservation_id = %s",
                   (reservation_id,), success="Your selection has been cancelled.")
            return redirect(url_for("index"))
        return redirect(url_for("checkout", reservation_id=reservation_id))

    tickets = reservation_tickets(reservation_id)
    total = sum(t["paid"] for t in tickets)
    return render_template("checkout.html", res=res, tickets=tickets, total=total)


@app.route("/my-reservations")
@login_required
def my_reservations():
    release_expired_holds()
    reservations = query("""
        SELECT r.reservation_id, r.reservation_date, r.status, r.expires_at,
               COUNT(t.ticket_id) AS ticket_count,
               COALESCE(SUM(ticket_price(s.price, t.ticket_type)), 0) AS total,
               BOOL_AND(s.start_time > now()) AS is_future
        FROM reservation r
        LEFT JOIN ticket t    ON t.reservation_id = r.reservation_id
        LEFT JOIN screening s ON s.screening_id   = t.screening_id
        WHERE r.user_id = %s
        GROUP BY r.reservation_id
        ORDER BY r.reservation_date DESC""", (g.user["user_id"],))
    tickets = {r["reservation_id"]: reservation_tickets(r["reservation_id"])
               for r in reservations}
    return render_template("my_reservations.html", reservations=reservations, tickets=tickets)


@app.route("/reservation/<int:reservation_id>/cancel", methods=["POST"])
@login_required
def cancel_reservation(reservation_id):
    res = query("""
        SELECT r.user_id, r.status, BOOL_AND(s.start_time > now()) AS is_future
        FROM reservation r
        LEFT JOIN ticket t    ON t.reservation_id = r.reservation_id
        LEFT JOIN screening s ON s.screening_id   = t.screening_id
        WHERE r.reservation_id = %s
        GROUP BY r.reservation_id""", (reservation_id,), one=True)
    is_admin = g.user["role"] == "admin"
    if res is None or (res["user_id"] != g.user["user_id"] and not is_admin):
        abort(404)
    if res["status"] == "cancelled":
        flash("This reservation is already cancelled.", "info")
    elif res["is_future"] is False and not is_admin:
        flash("Reservations for past screenings cannot be cancelled.", "danger")
    else:
        modify("UPDATE reservation SET status = 'cancelled' WHERE reservation_id = %s",
               (reservation_id,), success="Reservation cancelled. The seats are free again.")
    return redirect(request.referrer or url_for("my_reservations"))


# =====================================================================
# Admin panel
# =====================================================================
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = query("""
        SELECT (SELECT COUNT(*) FROM movie)                                  AS movies,
               (SELECT COUNT(*) FROM cinema)                                 AS cinemas,
               (SELECT COUNT(*) FROM screening WHERE start_time > now())     AS upcoming,
               (SELECT COUNT(*) FROM users WHERE role = 'customer')          AS customers,
               (SELECT COUNT(*) FROM ticket t JOIN reservation r
                    ON r.reservation_id = t.reservation_id
                 WHERE r.status = 'confirmed')                               AS tickets_sold,
               (SELECT COALESCE(SUM(ticket_price(s.price, t.ticket_type)), 0)
                  FROM ticket t
                  JOIN reservation r ON r.reservation_id = t.reservation_id
                  JOIN screening s   ON s.screening_id   = t.screening_id
                 WHERE r.status = 'confirmed')                               AS revenue""",
                  one=True)
    # report query 2: tickets sold and revenue per movie
    per_movie = query("""
        SELECT m.title, COUNT(t.ticket_id) AS tickets_sold,
               SUM(ticket_price(s.price, t.ticket_type)) AS revenue
        FROM movie m
        JOIN screening s   ON s.movie_id       = m.movie_id
        JOIN ticket t      ON t.screening_id   = s.screening_id
        JOIN reservation r ON r.reservation_id = t.reservation_id
        WHERE r.status = 'confirmed'
        GROUP BY m.movie_id, m.title
        ORDER BY revenue DESC""")
    # report query 3: movies without any screening
    no_screening = query("""
        SELECT m.movie_id, m.title FROM movie m
        WHERE m.movie_id NOT IN (SELECT s.movie_id FROM screening s)
        ORDER BY m.title""")
    return render_template("admin/dashboard.html", stats=stats, per_movie=per_movie,
                           no_screening=no_screening)


# ---------- movies ----------
@app.route("/admin/movies")
@admin_required
def admin_movies():
    movies = query("""
        SELECT m.movie_id, m.title, m.director, m.genre, m.duration_min, m.age_rating,
               m.release_date, (m.poster IS NOT NULL) AS has_poster,
               (SELECT COUNT(*) FROM screening s WHERE s.movie_id = m.movie_id) AS screenings
        FROM movie m ORDER BY m.title""")
    return render_template("admin/movies.html", movies=movies)


def read_poster():
    """Return the uploaded poster bytes, False if invalid, None if none uploaded."""
    file = request.files.get("poster")
    if not file or not file.filename:
        return None
    data = file.read()
    if image_mimetype(data) is None:
        flash("The poster was not saved: it must be a PNG, JPG, GIF or WEBP image (HEIC photos are not supported).", "danger")
        return False
    return data


@app.route("/admin/movies/new", methods=["GET", "POST"])
@app.route("/admin/movies/<int:movie_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_movie_form(movie_id=None):
    movie = None
    if movie_id:
        movie = query("SELECT *, (poster IS NOT NULL) AS has_poster FROM movie WHERE movie_id = %s",
                      (movie_id,), one=True)
        if movie is None:
            abort(404)
    if request.method == "POST":
        f = request.form
        poster_data = read_poster()
        if poster_data is not False:
            values = (f["title"].strip(), f["director"].strip(), f["duration_min"],
                      f["age_rating"], f["release_date"], f["description"].strip(),
                      f["genre"].strip())
            if movie_id:
                ok = modify("""UPDATE movie SET title = %s, director = %s, duration_min = %s,
                               age_rating = %s, release_date = %s, description = %s, genre = %s
                               WHERE movie_id = %s""", values + (movie_id,))
                if ok and poster_data:
                    modify("UPDATE movie SET poster = %s WHERE movie_id = %s",
                           (psycopg2.Binary(poster_data), movie_id))
                elif ok and f.get("remove_poster"):
                    modify("UPDATE movie SET poster = NULL WHERE movie_id = %s", (movie_id,))
                if ok:
                    flash("Movie updated.", "success")
                    return redirect(url_for("admin_movies"))
            else:
                ok = modify("""INSERT INTO movie (title, director, duration_min, age_rating,
                               release_date, description, genre, poster)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            values + (psycopg2.Binary(poster_data) if poster_data else None,),
                            success="Movie added.")
                if ok:
                    return redirect(url_for("admin_movies"))
        movie = dict(movie or {}, **f.to_dict())
    genres = [r["genre"] for r in query("SELECT DISTINCT genre FROM movie ORDER BY genre")]
    return render_template("admin/movie_form.html", movie=movie, genres=genres,
                           ratings=AGE_RATINGS)


@app.route("/admin/movies/<int:movie_id>/delete", methods=["POST"])
@admin_required
def admin_movie_delete(movie_id):
    modify("DELETE FROM movie WHERE movie_id = %s", (movie_id,), success="Movie deleted.")
    return redirect(url_for("admin_movies"))


# ---------- cinemas and halls ----------
@app.route("/admin/cinemas")
@admin_required
def admin_cinemas():
    cinemas = query("""
        SELECT c.cinema_id, c.name, c.city, c.address,
               COUNT(DISTINCT h.hall_id) AS halls, COUNT(se.seat_id) AS seats
        FROM cinema c
        LEFT JOIN hall h  ON h.cinema_id = c.cinema_id
        LEFT JOIN seat se ON se.hall_id  = h.hall_id
        GROUP BY c.cinema_id
        ORDER BY c.city, c.name""")
    return render_template("admin/cinemas.html", cinemas=cinemas)


@app.route("/admin/cinemas/new", methods=["GET", "POST"])
@app.route("/admin/cinemas/<int:cinema_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_cinema_form(cinema_id=None):
    cinema = None
    if cinema_id:
        cinema = query("SELECT * FROM cinema WHERE cinema_id = %s", (cinema_id,), one=True)
        if cinema is None:
            abort(404)
    if request.method == "POST":
        f = request.form
        values = (f["name"].strip(), f["city"].strip(), f["address"].strip() or None)
        if cinema_id:
            ok = modify("UPDATE cinema SET name = %s, city = %s, address = %s WHERE cinema_id = %s",
                        values + (cinema_id,), success="Cinema updated.")
        else:
            ok = modify("INSERT INTO cinema (name, city, address) VALUES (%s, %s, %s) "
                        "RETURNING cinema_id", values, success="Cinema added.")
            if ok:
                cinema_id = ok["cinema_id"]
        if ok:
            return redirect(url_for("admin_cinema_detail", cinema_id=cinema_id))
        cinema = f.to_dict()
    return render_template("admin/cinema_form.html", cinema=cinema)


@app.route("/admin/cinemas/<int:cinema_id>")
@admin_required
def admin_cinema_detail(cinema_id):
    cinema = query("SELECT * FROM cinema WHERE cinema_id = %s", (cinema_id,), one=True)
    if cinema is None:
        abort(404)
    halls = query("""
        SELECT h.hall_id, h.hall_name,
               COUNT(se.seat_id) AS capacity,
               COUNT(DISTINCT se.row_letter) AS row_count,
               (SELECT COUNT(*) FROM screening s WHERE s.hall_id = h.hall_id) AS screenings
        FROM hall h
        LEFT JOIN seat se ON se.hall_id = h.hall_id
        WHERE h.cinema_id = %s
        GROUP BY h.hall_id
        ORDER BY h.hall_name""", (cinema_id,))
    return render_template("admin/cinema_detail.html", cinema=cinema, halls=halls)


@app.route("/admin/cinemas/<int:cinema_id>/delete", methods=["POST"])
@admin_required
def admin_cinema_delete(cinema_id):
    if modify("DELETE FROM cinema WHERE cinema_id = %s", (cinema_id,), success="Cinema deleted."):
        return redirect(url_for("admin_cinemas"))
    return redirect(url_for("admin_cinema_detail", cinema_id=cinema_id))


@app.route("/admin/cinemas/<int:cinema_id>/halls", methods=["POST"])
@admin_required
def admin_hall_add(cinema_id):
    f = request.form
    try:
        rows, per_row = int(f["rows"]), int(f["seats_per_row"])
    except ValueError:
        rows = per_row = 0
    if not (1 <= rows <= 26 and 1 <= per_row <= 40):
        flash("Rows must be 1-26 and seats per row 1-40.", "danger")
        return redirect(url_for("admin_cinema_detail", cinema_id=cinema_id))
    db = get_db()
    try:                     # hall + all its seats in ONE transaction
        with db.cursor() as cur:
            cur.execute("INSERT INTO hall (cinema_id, hall_name) VALUES (%s, %s) RETURNING hall_id",
                        (cinema_id, f["hall_name"].strip()))
            hall_id = cur.fetchone()["hall_id"]
            cur.execute("""INSERT INTO seat (hall_id, row_letter, seat_number)
                           SELECT %s, chr(64 + r), n
                           FROM generate_series(1, %s) AS r, generate_series(1, %s) AS n""",
                        (hall_id, rows, per_row))
        db.commit()
        flash(f"Hall added with {rows * per_row} seats.", "success")
    except psycopg2.Error as err:
        db.rollback()
        flash(db_error_message(err), "danger")
    return redirect(url_for("admin_cinema_detail", cinema_id=cinema_id))


@app.route("/admin/halls/<int:hall_id>/rename", methods=["POST"])
@admin_required
def admin_hall_rename(hall_id):
    row = modify("UPDATE hall SET hall_name = %s WHERE hall_id = %s RETURNING cinema_id",
                 (request.form["hall_name"].strip(), hall_id), success="Hall renamed.")
    cinema_id = row["cinema_id"] if row else request.form.get("cinema_id")
    return redirect(url_for("admin_cinema_detail", cinema_id=cinema_id))


@app.route("/admin/halls/<int:hall_id>/delete", methods=["POST"])
@admin_required
def admin_hall_delete(hall_id):
    modify("DELETE FROM hall WHERE hall_id = %s", (hall_id,), success="Hall deleted.")
    return redirect(url_for("admin_cinema_detail", cinema_id=request.form.get("cinema_id")))


# ---------- screenings ----------
@app.route("/admin/screenings")
@admin_required
def admin_screenings():
    show = request.args.get("show", "upcoming")
    screenings = query("""
        SELECT s.screening_id, s.start_time, s.format, s.language, s.price,
               m.title, h.hall_name, c.name AS cinema, c.city,
               (SELECT COUNT(*) FROM ticket t JOIN reservation r
                    ON r.reservation_id = t.reservation_id
                 WHERE t.screening_id = s.screening_id AND r.status = 'confirmed') AS sold,
               (SELECT COUNT(*) FROM seat se WHERE se.hall_id = s.hall_id) AS capacity
        FROM screening s
        JOIN movie m  ON m.movie_id  = s.movie_id
        JOIN hall h   ON h.hall_id   = s.hall_id
        JOIN cinema c ON c.cinema_id = h.cinema_id
        WHERE (%s = 'all' OR s.start_time > now())
        ORDER BY s.start_time""", (show,))
    return render_template("admin/screenings.html", screenings=screenings, show=show)


@app.route("/admin/screenings/new", methods=["GET", "POST"])
@app.route("/admin/screenings/<int:screening_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_screening_form(screening_id=None):
    scr = None
    if screening_id:
        scr = query("SELECT * FROM screening WHERE screening_id = %s", (screening_id,), one=True)
        if scr is None:
            abort(404)
        scr = dict(scr, start_time=scr["start_time"].strftime("%Y-%m-%dT%H:%M"))
    if request.method == "POST":
        f = request.form
        values = (f["movie_id"], f["hall_id"], f["start_time"], f["format"],
                  f["language"], f["price"])
        if screening_id:
            ok = modify("""UPDATE screening SET movie_id = %s, hall_id = %s, start_time = %s,
                           format = %s, language = %s, price = %s WHERE screening_id = %s""",
                        values + (screening_id,), success="Screening updated.")
        else:
            ok = modify("""INSERT INTO screening (movie_id, hall_id, start_time, format, language, price)
                           VALUES (%s, %s, %s, %s, %s, %s)""", values, success="Screening added.")
        if ok:
            return redirect(url_for("admin_screenings"))
        scr = f.to_dict()
    movies = query("SELECT movie_id, title FROM movie ORDER BY title")
    halls = query("""SELECT h.hall_id, c.city || ' - ' || c.name || ' - ' || h.hall_name AS label
                     FROM hall h JOIN cinema c ON c.cinema_id = h.cinema_id
                     ORDER BY c.city, c.name, h.hall_name""")
    return render_template("admin/screening_form.html", scr=scr, movies=movies, halls=halls,
                           formats=FORMATS, languages=LANGUAGES)


@app.route("/admin/screenings/<int:screening_id>/delete", methods=["POST"])
@admin_required
def admin_screening_delete(screening_id):
    modify("DELETE FROM screening WHERE screening_id = %s", (screening_id,),
           success="Screening deleted.")
    return redirect(url_for("admin_screenings"))


# ---------- users ----------
@app.route("/admin/users")
@admin_required
def admin_users():
    users = query("""
        SELECT u.user_id, u.username, u.full_name, u.email, u.phone, u.role,
               COUNT(r.reservation_id) FILTER (WHERE r.status = 'confirmed') AS purchases
        FROM users u
        LEFT JOIN reservation r ON r.user_id = u.user_id
        GROUP BY u.user_id
        ORDER BY u.role, u.username""")
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_user_role(user_id):
    if user_id == g.user["user_id"]:
        flash("You cannot change your own role.", "warning")
    else:
        modify("UPDATE users SET role = %s WHERE user_id = %s",
               (request.form["role"], user_id), success="Role updated.")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_user_delete(user_id):
    if user_id == g.user["user_id"]:
        flash("You cannot delete your own account.", "warning")
    else:
        modify("DELETE FROM users WHERE user_id = %s", (user_id,),
               success="User and all of their reservations deleted.")
    return redirect(url_for("admin_users"))


# ---------- reservations ----------
@app.route("/admin/reservations")
@admin_required
def admin_reservations():
    release_expired_holds()
    status = request.args.get("status", "")
    reservations = query("""
        SELECT r.reservation_id, r.reservation_date, r.status, r.expires_at,
               u.username, u.full_name,
               COUNT(t.ticket_id) AS ticket_count,
               COALESCE(SUM(ticket_price(s.price, t.ticket_type)), 0) AS total,
               STRING_AGG(DISTINCT m.title, ', ') AS movies
        FROM reservation r
        JOIN users u          ON u.user_id        = r.user_id
        LEFT JOIN ticket t    ON t.reservation_id = r.reservation_id
        LEFT JOIN screening s ON s.screening_id   = t.screening_id
        LEFT JOIN movie m     ON m.movie_id       = s.movie_id
        WHERE (%s = '' OR r.status = %s)
        GROUP BY r.reservation_id, u.username, u.full_name
        ORDER BY r.reservation_date DESC""", (status, status))
    return render_template("admin/reservations.html", reservations=reservations, status=status)


# =====================================================================
# Template helpers and error pages
# =====================================================================
@app.template_filter("dt")
def format_datetime(value, fmt="%d %b %Y, %H:%M"):
    return value.strftime(fmt) if value else ""


@app.template_filter("money")
def format_money(value):
    return f"{value:,.2f} TL"


@app.context_processor
def inject_constants():
    return {"LANGUAGES": LANGUAGES, "TICKET_TYPES": TICKET_TYPES}


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403,
                           message="This page is only for administrators."), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(413)
def too_large(_e):
    flash("The poster was not saved: the file is too large (maximum 10 MB).", "danger")
    return redirect(request.referrer or url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
