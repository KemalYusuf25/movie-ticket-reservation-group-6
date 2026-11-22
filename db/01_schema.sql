-- =====================================================================
-- CMPE341 - Movie Ticket Reservation System (Group 6)
-- 01_schema.sql : creates all tables with their constraints (PostgreSQL)
-- =====================================================================

-- Drop tables in reverse dependency order so the script can be re-run
DROP TABLE IF EXISTS ticket       CASCADE;
DROP TABLE IF EXISTS reservation  CASCADE;
DROP TABLE IF EXISTS screening    CASCADE;
DROP TABLE IF EXISTS seat         CASCADE;
DROP TABLE IF EXISTS hall         CASCADE;
DROP TABLE IF EXISTS cinema       CASCADE;
DROP TABLE IF EXISTS movie        CASCADE;
DROP TABLE IF EXISTS users        CASCADE;

-- ---------------------------------------------------------------------
-- USERS : system users (customers and admins)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id        SERIAL PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(100) NOT NULL,
    email          VARCHAR(100) NOT NULL,
    phone          VARCHAR(20)  NOT NULL,
    role           VARCHAR(10)  NOT NULL DEFAULT 'customer',
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email    UNIQUE (email),
    CONSTRAINT chk_users_phone   CHECK (phone ~ '^\+?[0-9]{10,15}$'),
    CONSTRAINT chk_users_role    CHECK (role IN ('admin', 'customer'))
);

-- ---------------------------------------------------------------------
-- MOVIE
-- ---------------------------------------------------------------------
CREATE TABLE movie (
    movie_id      SERIAL PRIMARY KEY,
    title         VARCHAR(150) NOT NULL,
    director      VARCHAR(100) NOT NULL,
    duration_min  INT          NOT NULL,
    age_rating    VARCHAR(5)   NOT NULL,
    release_date  DATE         NOT NULL,
    description   TEXT         NOT NULL,
    genre         VARCHAR(30)  NOT NULL,
    poster        BYTEA,                      -- poster image file (optional)
    CONSTRAINT chk_movie_duration   CHECK (duration_min > 0),
    CONSTRAINT chk_movie_age_rating CHECK (age_rating IN ('G', '7+', '13+', '18+'))
);

-- ---------------------------------------------------------------------
-- CINEMA
-- ---------------------------------------------------------------------
CREATE TABLE cinema (
    cinema_id  SERIAL PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    city       VARCHAR(50)  NOT NULL,
    address    VARCHAR(200)
);

-- ---------------------------------------------------------------------
-- HALL : a cinema has many halls
--        (capacity is derived: number of seats in the hall)
-- ---------------------------------------------------------------------
CREATE TABLE hall (
    hall_id    SERIAL PRIMARY KEY,
    cinema_id  INT         NOT NULL,
    hall_name  VARCHAR(30) NOT NULL,
    CONSTRAINT uq_hall_name      UNIQUE (cinema_id, hall_name),
    CONSTRAINT fk_hall_cinema    FOREIGN KEY (cinema_id)
        REFERENCES cinema(cinema_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- SEAT : a hall has many seats
-- ---------------------------------------------------------------------
CREATE TABLE seat (
    seat_id      SERIAL PRIMARY KEY,
    hall_id      INT     NOT NULL,
    row_letter   CHAR(1) NOT NULL,
    seat_number  INT     NOT NULL,
    CONSTRAINT chk_seat_number CHECK (seat_number > 0),
    CONSTRAINT uq_seat         UNIQUE (hall_id, row_letter, seat_number),
    CONSTRAINT fk_seat_hall    FOREIGN KEY (hall_id)
        REFERENCES hall(hall_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- SCREENING : a movie shown in a hall at a given time,
--             in a given format (2D/3D/IMAX/4DX) and language
-- ---------------------------------------------------------------------
CREATE TABLE screening (
    screening_id   SERIAL PRIMARY KEY,
    movie_id       INT          NOT NULL,
    hall_id        INT          NOT NULL,
    start_time     TIMESTAMP    NOT NULL,
    format         VARCHAR(5)   NOT NULL DEFAULT '2D',
    language       VARCHAR(10)  NOT NULL,
    price          NUMERIC(6,2) NOT NULL,     -- full ticket price
    CONSTRAINT chk_screening_format    CHECK (format IN ('2D', '3D', 'IMAX', '4DX')),
    CONSTRAINT chk_screening_language  CHECK (language IN ('dubbed', 'subtitled')),
    CONSTRAINT chk_screening_price     CHECK (price >= 0),
    CONSTRAINT uq_screening_hall_time  UNIQUE (hall_id, start_time),
    CONSTRAINT fk_screening_movie FOREIGN KEY (movie_id)
        REFERENCES movie(movie_id) ON DELETE RESTRICT,
    CONSTRAINT fk_screening_hall  FOREIGN KEY (hall_id)
        REFERENCES hall(hall_id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------
-- RESERVATION : made by a user, groups one or more tickets
--   pending   : seats are in the user's cart, held until expires_at (5 min)
--   confirmed : purchase completed
--   cancelled : reservation cancelled, its seats are released
-- ---------------------------------------------------------------------
CREATE TABLE reservation (
    reservation_id    SERIAL PRIMARY KEY,
    user_id           INT         NOT NULL,
    reservation_date  TIMESTAMP   NOT NULL DEFAULT now(),
    status            VARCHAR(10) NOT NULL DEFAULT 'pending',
    expires_at        TIMESTAMP   DEFAULT (now() + INTERVAL '5 minutes'),
    CONSTRAINT chk_reservation_status CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    CONSTRAINT chk_reservation_expiry CHECK (
        (status = 'pending'  AND expires_at IS NOT NULL) OR
        (status <> 'pending' AND expires_at IS NULL)),
    CONSTRAINT fk_reservation_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- TICKET : one seat for one screening, belongs to a reservation.
--          ticket_type: 'full' pays the screening price,
--                       'student' pays 25% less (see ticket_price()).
-- ---------------------------------------------------------------------
CREATE TABLE ticket (
    ticket_id       SERIAL PRIMARY KEY,
    reservation_id  INT          NOT NULL,
    screening_id    INT          NOT NULL,
    seat_id         INT          NOT NULL,
    ticket_type     VARCHAR(10)  NOT NULL DEFAULT 'full',
    CONSTRAINT chk_ticket_type  CHECK (ticket_type IN ('full', 'student')),
    CONSTRAINT uq_ticket_seat UNIQUE (screening_id, seat_id),
    CONSTRAINT fk_ticket_reservation FOREIGN KEY (reservation_id)
        REFERENCES reservation(reservation_id) ON DELETE CASCADE,
    CONSTRAINT fk_ticket_screening FOREIGN KEY (screening_id)
        REFERENCES screening(screening_id) ON DELETE RESTRICT,
    CONSTRAINT fk_ticket_seat FOREIGN KEY (seat_id)
        REFERENCES seat(seat_id) ON DELETE RESTRICT
);

-- =====================================================================
-- BUSINESS RULES (functions and triggers)
-- =====================================================================

-- ---------------------------------------------------------------------
-- Rule 1: a ticket's seat must be in the hall of its screening.
-- Rule 2: an expired cart hold must not block other customers, so
--         expired pending tickets for the same seat are removed first.
-- Rule 3: tickets cannot be added to a cancelled or expired reservation.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION check_ticket() RETURNS TRIGGER AS $$
DECLARE
    v_seat_hall       INT;
    v_screening_hall  INT;
    v_status          VARCHAR(10);
    v_expires         TIMESTAMP;
BEGIN
    SELECT hall_id INTO v_seat_hall FROM seat WHERE seat_id = NEW.seat_id;
    SELECT hall_id INTO v_screening_hall FROM screening WHERE screening_id = NEW.screening_id;

    IF v_seat_hall <> v_screening_hall THEN
        RAISE EXCEPTION 'Seat % is not in the hall of screening %', NEW.seat_id, NEW.screening_id;
    END IF;

    SELECT status, expires_at INTO v_status, v_expires
    FROM reservation WHERE reservation_id = NEW.reservation_id;

    IF v_status = 'cancelled' OR (v_status = 'pending' AND v_expires < now()) THEN
        RAISE EXCEPTION 'Reservation % is cancelled or its hold has expired', NEW.reservation_id;
    END IF;

    DELETE FROM ticket t
    USING reservation r
    WHERE t.reservation_id = r.reservation_id
      AND r.status = 'pending' AND r.expires_at < now()
      AND t.screening_id = NEW.screening_id
      AND t.seat_id = NEW.seat_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_ticket
    BEFORE INSERT OR UPDATE ON ticket
    FOR EACH ROW EXECUTE FUNCTION check_ticket();

-- ---------------------------------------------------------------------
-- Rule 4: an expired hold cannot be confirmed.
-- Rule 5: leaving 'pending' clears expires_at.
-- Rule 6: cancelling a reservation releases its seats (deletes tickets).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION check_reservation_status() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'pending' AND NEW.status = 'confirmed' AND OLD.expires_at < now() THEN
        RAISE EXCEPTION 'The 5 minute hold of reservation % has expired', OLD.reservation_id;
    END IF;

    IF NEW.status <> 'pending' THEN
        NEW.expires_at := NULL;
    END IF;

    IF NEW.status = 'cancelled' AND OLD.status <> 'cancelled' THEN
        DELETE FROM ticket WHERE reservation_id = NEW.reservation_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_reservation_status
    BEFORE UPDATE OF status ON reservation
    FOR EACH ROW EXECUTE FUNCTION check_reservation_status();

-- ---------------------------------------------------------------------
-- Housekeeping: deletes expired pending reservations (and their tickets).
-- Called by the web application before showing a seat map.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION release_expired_holds() RETURNS INT AS $$
DECLARE
    v_count INT;
BEGIN
    DELETE FROM reservation
    WHERE status = 'pending' AND expires_at < now();
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- Rule 7: price of a ticket = screening price for 'full',
--         25% discount for 'student'. Used by queries and the web app.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ticket_price(p_price NUMERIC, p_ticket_type VARCHAR)
RETURNS NUMERIC AS $$
BEGIN
    IF p_ticket_type = 'student' THEN
        RETURN ROUND(p_price * 0.75, 2);
    END IF;
    RETURN p_price;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ---------------------------------------------------------------------
-- Rule 8: the price of a screening cannot be changed once tickets of a
--         confirmed reservation exist for it, so completed purchases
--         keep their price. (Cancelled reservations have no tickets;
--         pending ones are not paid yet and simply see the new price.)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION check_screening_price() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.price <> OLD.price AND EXISTS (
        SELECT 1
        FROM ticket t
        JOIN reservation r ON r.reservation_id = t.reservation_id
        WHERE t.screening_id = OLD.screening_id
          AND r.status = 'confirmed')
    THEN
        RAISE EXCEPTION 'Price of screening % cannot be changed: tickets have already been sold', OLD.screening_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_screening_price
    BEFORE UPDATE OF price ON screening
    FOR EACH ROW EXECUTE FUNCTION check_screening_price();
