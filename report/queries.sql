-- =====================================================================
-- CMPE341 - Movie Ticket Reservation System (Group 6)
-- Report queries (Chapter 5). Run after 01_schema.sql and 02_data.sql.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Query 1 (JOIN): sold tickets with the customer, the movie,
-- the screening time and the price paid (student tickets 25% off).
-- ---------------------------------------------------------------------
SELECT u.full_name                          AS customer,
       m.title                              AS movie,
       s.start_time,
       t.ticket_type,
       ticket_price(s.price, t.ticket_type) AS price
FROM ticket t
JOIN reservation r ON r.reservation_id = t.reservation_id
JOIN users u       ON u.user_id        = r.user_id
JOIN screening s   ON s.screening_id   = t.screening_id
JOIN movie m       ON m.movie_id       = s.movie_id
WHERE r.status = 'confirmed'
ORDER BY u.full_name, s.start_time;

-- ---------------------------------------------------------------------
-- Query 2 (GROUP BY + ORDER BY): tickets sold and revenue per movie,
-- best-selling movie first.
-- ---------------------------------------------------------------------
SELECT m.title,
       COUNT(t.ticket_id)                        AS tickets_sold,
       SUM(ticket_price(s.price, t.ticket_type)) AS revenue
FROM movie m
JOIN screening s   ON s.movie_id       = m.movie_id
JOIN ticket t      ON t.screening_id   = s.screening_id
JOIN reservation r ON r.reservation_id = t.reservation_id
WHERE r.status = 'confirmed'
GROUP BY m.movie_id, m.title
ORDER BY revenue DESC;

-- ---------------------------------------------------------------------
-- Query 3 (SUBQUERY): movies that have no screening yet
-- ---------------------------------------------------------------------
SELECT m.title, m.director, m.genre
FROM movie m
WHERE m.movie_id NOT IN (SELECT s.movie_id FROM screening s);

-- ---------------------------------------------------------------------
-- Extra (GROUP BY + ORDER BY): capacity of each hall,
-- computed from the number of seats (capacity is a derived attribute)
-- ---------------------------------------------------------------------
SELECT c.name             AS cinema,
       h.hall_name,
       COUNT(se.seat_id)  AS capacity
FROM hall h
JOIN cinema c     ON c.cinema_id = h.cinema_id
LEFT JOIN seat se ON se.hall_id  = h.hall_id
GROUP BY c.name, h.hall_id, h.hall_name
ORDER BY capacity DESC;
