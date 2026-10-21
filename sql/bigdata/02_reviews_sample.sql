-- =====================================================================
-- Big data : échantillon d'avis récents en anglais, par jeu
-- Usage : textes pour l'analyse de sentiment (blocs E2/E3)
-- Résultat : au plus 200 avis par jeu, les plus utiles en premier
-- =====================================================================
WITH ranked AS (
    SELECT
        review_id,
        app_id,
        author_hash,                -- identifiant déjà pseudonymisé à l'ingestion
        review,
        recommended,
        votes_helpful,
        author_playtime_at_review,
        timestamp_created,
        -- Fenêtre : classement des avis au sein de chaque jeu
        ROW_NUMBER() OVER (PARTITION BY app_id
                           ORDER BY votes_helpful DESC, timestamp_created DESC) AS rn
    FROM steam_reviews
    -- Partition pruning : seuls les dossiers year=2019..2021 sont lus
    WHERE year >= 2019
      AND language = 'english'
      -- Avis vides ou trop courts ("good", "10/10") : inutiles pour l'analyse
      AND LENGTH(review) >= 20
)
SELECT review_id, app_id, author_hash, review, recommended, votes_helpful,
       author_playtime_at_review, timestamp_created
FROM ranked
WHERE rn <= 200
