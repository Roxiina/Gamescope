#!/bin/bash
# Rôles d'accès à la base GameScope (principe du moindre privilège).
# Les mots de passe viennent des variables d'environnement du conteneur (.env).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v api_pwd="$GAMESCOPE_API_PASSWORD" -v analyst_pwd="$GAMESCOPE_ANALYST_PASSWORD" <<'SQL'
-- API REST : lecture des données, gestion de ses propres comptes utilisateurs
CREATE ROLE gamescope_api LOGIN PASSWORD :'api_pwd';
GRANT CONNECT ON DATABASE gamescope TO gamescope_api;
GRANT USAGE ON SCHEMA public TO gamescope_api;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gamescope_api;
GRANT INSERT, UPDATE ON api_user TO gamescope_api;
GRANT USAGE ON SEQUENCE api_user_user_id_seq TO gamescope_api;
REVOKE SELECT ON rgpd_log FROM gamescope_api;

-- Équipe data (analyses, entraînement de modèles) : lecture seule, SANS les comptes API
CREATE ROLE gamescope_analyst LOGIN PASSWORD :'analyst_pwd';
GRANT CONNECT ON DATABASE gamescope TO gamescope_analyst;
GRANT USAGE ON SCHEMA public TO gamescope_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gamescope_analyst;
REVOKE SELECT ON api_user, rgpd_log FROM gamescope_analyst;
SQL
