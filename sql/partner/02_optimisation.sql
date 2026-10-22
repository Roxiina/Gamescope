-- =====================================================================
-- Démonstration d'optimisation (C2) sur la base partenaire
-- Exécution (compte propriétaire, création d'index) :
--   docker cp sql/partner/02_optimisation.sql gamescope_partner_db:/tmp/
--   docker exec gamescope_partner_db sh -c 'psql -U "$POSTGRES_USER" -d steam_partner -f /tmp/02_optimisation.sql'
-- Chaque cas : mesure AVANT, création de l'index, mesure APRÈS.
-- =====================================================================

DROP INDEX IF EXISTS idx_game_tags_tag_id;
DROP INDEX IF EXISTS idx_games_metacritic_release;
ANALYZE;

-- ---------------------------------------------------------------------
-- CAS A - "Tous les jeux portant le tag Rogue-like"
-- La clé primaire de game_tags est (app_id, tag_id) : elle sert à trouver
-- les tags D'UN jeu, pas les jeux D'UN tag (tag_id n'est pas en 1re
-- position). Sans index sur tag_id : lecture des 1,2 M de liens.
-- ---------------------------------------------------------------------
\echo '===== CAS A - AVANT ====='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT g.app_id, g.name
FROM tags t
JOIN game_tags gt ON gt.tag_id = t.tag_id
JOIN games g      ON g.app_id = gt.app_id
WHERE t.name = 'Rogue-like';

CREATE INDEX idx_game_tags_tag_id ON game_tags (tag_id);
ANALYZE game_tags;

\echo '===== CAS A - APRES ====='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT g.app_id, g.name
FROM tags t
JOIN game_tags gt ON gt.tag_id = t.tag_id
JOIN games g      ON g.app_id = gt.app_id
WHERE t.name = 'Rogue-like';

-- ---------------------------------------------------------------------
-- CAS B - "Jeux bien notés (Metacritic >= 80) sortis depuis 2015"
-- Sans index : lecture séquentielle des 125 855 jeux.
-- Index composite (note, date) dans l'ordre des filtres, et PARTIEL :
-- seuls les jeux notés (metacritic_score > 0, environ 4 %) sont indexés,
-- l'index est donc environ 25 fois plus petit qu'un index complet.
-- ---------------------------------------------------------------------
\echo '===== CAS B - AVANT ====='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT app_id, name, metacritic_score, release_date
FROM games
WHERE metacritic_score >= 80
  AND release_date >= DATE '2015-01-01'
ORDER BY metacritic_score DESC;

CREATE INDEX idx_games_metacritic_release
    ON games (metacritic_score, release_date)
    WHERE metacritic_score > 0;
ANALYZE games;

\echo '===== CAS B - APRES ====='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT app_id, name, metacritic_score, release_date
FROM games
WHERE metacritic_score >= 80
  AND release_date >= DATE '2015-01-01'
ORDER BY metacritic_score DESC;
