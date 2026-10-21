-- =====================================================================
-- Extraction des fiches catalogue du partenaire pour les jeux GameScope
-- Système : PostgreSQL 17 (base steam_partner), rôle gamescope_reader
-- Paramètre : :appids -> liste des app_id suivis (issus de SteamSpy)
-- Résultat  : 1 ligne par jeu, référentiels agrégés en tableaux
-- =====================================================================
WITH cible AS (
    -- Sélection : on ne lit que les ~2000 jeux suivis, pas les 110 000 du catalogue
    SELECT unnest(CAST(:appids AS integer[])) AS app_id
)
SELECT
    g.app_id,
    g.name,
    g.release_date,
    g.estimated_owners,
    g.peak_ccu,
    g.price_usd,
    g.dlc_count,
    g.metacritic_score,
    g.positive,
    g.negative,
    g.achievements,
    g.avg_playtime_min,
    g.median_playtime_min,
    g.windows,
    g.mac,
    g.linux,
    dev.developers,
    pub.publishers,
    gen.genres,
    tg.top_tags
FROM cible c
-- Jointure interne : un app_id absent du catalogue partenaire n'est pas renvoyé
JOIN games g ON g.app_id = c.app_id
-- LATERAL : chaque sous-requête n'agrège que les lignes du jeu courant,
-- via la clé primaire (app_id, ...) dont app_id est la 1re colonne -> index utilisé
LEFT JOIN LATERAL (
    SELECT array_agg(d.name ORDER BY d.name) AS developers
    FROM game_developers gd JOIN developers d USING (developer_id)
    WHERE gd.app_id = g.app_id
) dev ON TRUE
LEFT JOIN LATERAL (
    SELECT array_agg(p.name ORDER BY p.name) AS publishers
    FROM game_publishers gp JOIN publishers p USING (publisher_id)
    WHERE gp.app_id = g.app_id
) pub ON TRUE
LEFT JOIN LATERAL (
    SELECT array_agg(ge.name ORDER BY ge.name) AS genres
    FROM game_genres gg JOIN genres ge USING (genre_id)
    WHERE gg.app_id = g.app_id
) gen ON TRUE
-- Filtrage : seuls les 10 tags les plus votés, au-delà ils sont peu significatifs
LEFT JOIN LATERAL (
    SELECT array_agg(t.name ORDER BY gt.tag_rank) AS top_tags
    FROM game_tags gt JOIN tags t USING (tag_id)
    WHERE gt.app_id = g.app_id AND gt.tag_rank <= 10
) tg ON TRUE
ORDER BY g.app_id;
