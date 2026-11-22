-- =====================================================================
-- CMPE341 - Movie Ticket Reservation System (Group 6)
-- 02_data.sql : sample data (run after 01_schema.sql)
-- =====================================================================

-- Empty all tables and reset the SERIAL counters so ids start from 1
TRUNCATE users, movie, cinema, hall, seat, screening, reservation, ticket
RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------------
-- USERS  (passwords: admin=Admin123!, manager=Manager123!,
--         ayse=Ayse123!, mehmet=Mehmet123!, zeynep=Zeynep123!)
-- ---------------------------------------------------------------------
INSERT INTO users (username, password_hash, full_name, email, phone, role) VALUES
('admin',   'scrypt:32768:8:1$2OW8bcTESvi6WMba$15071c4debd2a61c4efa82f37b212a6617de6498bafd6c7d88badff50e5720991f192bd2cabdc8e61563313fb2b5e4af89d0295423b6d759a99b9eae1f72f4a2', 'Ercüment Aydın', 'admin@cinema.com',   '05301112233', 'admin'),
('manager', 'scrypt:32768:8:1$K6ozTPd2X0nVzDlR$34bd29dd426f58d41392fcdd26eebb68f8c770e1529ce2b853ddf5f9f0fdbb208d97e5827e279cbd135a45fd48a824fdf4b47317320645d238ddf1f5c2f08b6b', 'Cinema Manager', 'manager@cinema.com', '05302223344', 'admin'),
('ayse',    'scrypt:32768:8:1$ZKfmPmazahz2wVKj$540b9c17e2df9344023ca1955bea445a6e535ed6e5b70c9c4ce5b4705419d3c4e19e883517b0470020297cf066c5ab22228e3e794dd650e5c988c7bc5e619fd5', 'Ayse Yilmaz',    'ayse@mail.com',      '05321234567', 'customer'),
('mehmet',  'scrypt:32768:8:1$Zd0hWDUDIeFHoY9f$6ba04032450e380365b172b8733649257f36cb0bf5e8c04610d51cb30a44b4cf26245482b764166fd099b098744451e7e13fa36e740df9180483d6207d0eff83', 'Mehmet Kaya',    'mehmet@mail.com',    '05337654321', 'customer'),
('zeynep',  'scrypt:32768:8:1$tYloQGzAOjRE81BK$0dd67cfa9472311ff880660c15336c9474b6f111a6cbf4047dee17bb85b8ffdd751caa9ea109ff9bb9c896103a76387d63252f47ff5e0fe93bb45a9609ccd0a9', 'Zeynep Demir',   'zeynep@mail.com',    '05449876543', 'customer');

-- ---------------------------------------------------------------------
-- MOVIE
-- ---------------------------------------------------------------------
INSERT INTO movie (title, director, duration_min, age_rating, release_date, description, genre) VALUES
('A Beautiful Mind', 'Ron Howard', 135, '13+', '2026-12-12', 'A mathematical genius, John Nash made an astonishing discovery early in his career and stood on the brink of international acclaim. But Nash soon found himself on a harrowing journey of self-discovery.', 'Psychological Drama'),
('Eternal Sunshine of the Spotless Mind', 'Michel Gondry', 108, '13+', '2026-12-13', 'When their relationship turns sour, a couple undergoes a medical procedure to have each other erased from their memories forever.', 'Psychological Drama'),
('Çöpçüler Kralı', 'Zeki Ökten', 80, '13+', '2026-12-11', 'Going through his daily routine in a stereotypical neighborhood, a street cleaner falls in love with a charwoman. Unfortunately for him, so does his boss.', 'Comedy'),
('Big Hero 6', 'Don Hall', 102, 'G', '2026-12-14', 'A special bond develops between plus-sized inflatable robot Baymax and prodigy Hiro Hamada, who together team up with a group of friends to form a band of high-tech heroes.', 'Animation');

-- ---------------------------------------------------------------------
-- CINEMA
-- ---------------------------------------------------------------------
INSERT INTO cinema (name, city, address) VALUES
('Büyülü Fener', 'Ankara', 'Kocatepe Mh Meşrutiyet Cad, Hatay Sk. No:18, 06420 Çankaya/Ankara'),
('Paribu Cineverse Forum Trabzon', 'Trabzon', 'Devlet Sahil Yolu Cad. 100.Yıl Parkı Yanı'),
('Paribu Cineverse Erzurum MNG', 'Erzurum', 'LALAPAŞA MAH. SOMUNOĞLU CAD.NO:83 İÇ KAPI NO:181, 25100 Yakutiye/Erzurum');

-- ---------------------------------------------------------------------
-- HALL  (1-2: Ankara, 3-5: Trabzon, 6-7: Erzurum)
-- ---------------------------------------------------------------------
INSERT INTO hall (cinema_id, hall_name) VALUES
(1, 'Salon 1'),
(1, 'Salon 2'),
(2, 'Salon 1'),
(2, 'Salon 2'),
(2, 'Salon 3'),
(3, 'Salon 1'),
(3, 'Salon 2');

-- ---------------------------------------------------------------------
-- SEAT
-- a) a few seats inserted one by one
-- ---------------------------------------------------------------------
INSERT INTO seat (hall_id, row_letter, seat_number) VALUES
(1, 'A', 1), (1, 'A', 2), (1, 'A', 3), (1, 'A', 4), (1, 'A', 5), (1, 'A', 6),
(1, 'B', 1), (1, 'B', 2), (1, 'B', 3), (1, 'B', 4), (1, 'B', 5), (1, 'B', 6);

-- b) all remaining seats generated in bulk:
--    (hall, number of rows, seats per row); rows are lettered A, B, C ...
--    seats that already exist are skipped thanks to the UNIQUE constraint
INSERT INTO seat (hall_id, row_letter, seat_number)
SELECT v.hall_id, chr(64 + r), n
FROM (VALUES
        (1, 6, 10), (2, 4, 8), (3, 5, 10), (4, 4, 8),
        (5, 8, 12), (6, 5, 10), (7, 4, 8)
     ) AS v(hall_id, row_count, seats_per_row),
     generate_series(1, v.row_count)     AS r,
     generate_series(1, v.seats_per_row) AS n
ON CONFLICT ON CONSTRAINT uq_seat DO NOTHING;

-- ---------------------------------------------------------------------
-- SCREENING
-- ---------------------------------------------------------------------
INSERT INTO screening (movie_id, hall_id, start_time, format, language, price) VALUES
(1, 1, '2026-12-15 20:30', '2D',   'subtitled', 200),
(2, 1, '2026-12-15 16:30', 'IMAX', 'dubbed',    200),
(2, 2, '2026-12-15 16:00', '2D',   'subtitled', 200),
(4, 3, '2026-12-17 17:02', '3D',   'dubbed',    200);

-- ---------------------------------------------------------------------
-- RESERVATION (all start as 'pending' = in the cart)
-- ---------------------------------------------------------------------
INSERT INTO reservation (user_id) VALUES
(3),   -- 1: ayse
(4),   -- 2: mehmet
(5),   -- 3: zeynep
(3),   -- 4: ayse   (will be cancelled)
(4);   -- 5: mehmet

-- ---------------------------------------------------------------------
-- TICKET: the seat is looked up by hall + row + number and must be in
--         the hall of the screening
--         (screening 1, 2 -> hall 1 | screening 3 -> hall 2 | screening 4 -> hall 3)
-- ---------------------------------------------------------------------
INSERT INTO ticket (reservation_id, screening_id, seat_id, ticket_type) VALUES
-- ayse: A Beautiful Mind, 2D
(1, 1, (SELECT seat_id FROM seat WHERE hall_id = 1 AND row_letter = 'C' AND seat_number = 5), 'full'),
(1, 1, (SELECT seat_id FROM seat WHERE hall_id = 1 AND row_letter = 'C' AND seat_number = 6), 'student'),
-- mehmet: Eternal Sunshine, 2D
(2, 3, (SELECT seat_id FROM seat WHERE hall_id = 2 AND row_letter = 'B' AND seat_number = 3), 'full'),
(2, 3, (SELECT seat_id FROM seat WHERE hall_id = 2 AND row_letter = 'B' AND seat_number = 4), 'full'),
(2, 3, (SELECT seat_id FROM seat WHERE hall_id = 2 AND row_letter = 'B' AND seat_number = 5), 'student'),
-- zeynep: Big Hero 6, 3D
(3, 4, (SELECT seat_id FROM seat WHERE hall_id = 3 AND row_letter = 'E' AND seat_number = 5), 'student'),
(3, 4, (SELECT seat_id FROM seat WHERE hall_id = 3 AND row_letter = 'E' AND seat_number = 6), 'student'),
-- ayse: Eternal Sunshine, IMAX (cancelled below)
(4, 2, (SELECT seat_id FROM seat WHERE hall_id = 1 AND row_letter = 'D' AND seat_number = 7), 'full'),
-- mehmet: Eternal Sunshine, IMAX
(5, 2, (SELECT seat_id FROM seat WHERE hall_id = 1 AND row_letter = 'A' AND seat_number = 1), 'full'),
(5, 2, (SELECT seat_id FROM seat WHERE hall_id = 1 AND row_letter = 'A' AND seat_number = 2), 'full');

-- Final statuses
UPDATE reservation SET status = 'confirmed' WHERE reservation_id IN (1, 2, 3, 5);
UPDATE reservation SET status = 'cancelled' WHERE reservation_id = 4;
