-- =====================================================================
-- Big data : statistiques d'avis par jeu (Spark SQL via Thrift Server)
-- Source : data lake Parquet steam_reviews (~21 M avis, partitionné par year)
-- Résultat : 1 ligne par jeu
-- =====================================================================
SELECT
    app_id,
    COUNT(*)                                            AS nb_reviews,
    -- Taux de recommandation : moyenne d'un booléen converti en 0/1
    ROUND(AVG(CAST(recommended AS INT)) * 100, 2)       AS pct_recommended,
    -- Médiane approchée : exacte au millième près, bien moins coûteuse qu'un tri complet
    PERCENTILE_APPROX(author_playtime_at_review, 0.5)   AS median_playtime_at_review_min,
    ROUND(AVG(votes_helpful), 2)                        AS avg_votes_helpful,
    COUNT(DISTINCT language)                            AS nb_languages,
    SUM(CAST(steam_purchase AS INT))                    AS nb_steam_purchases,
    SUM(CAST(received_for_free AS INT))                 AS nb_received_for_free,
    MIN(year)                                           AS first_review_year,
    MAX(year)                                           AS last_review_year
FROM steam_reviews
-- Filtrage : avis exploitables uniquement (temps de jeu connu)
WHERE author_playtime_at_review IS NOT NULL
GROUP BY app_id
-- Seuil : moins de 50 avis, les pourcentages ne sont pas représentatifs
HAVING COUNT(*) >= 50
ORDER BY nb_reviews DESC
