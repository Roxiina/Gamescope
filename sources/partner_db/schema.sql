-- Base du partenaire "steam_partner" : catalogue Steam (Kaggle, FronkonGames)
-- Système SOURCE simulé : GameScope ne fait qu'y lire (rôle en lecture seule).
-- Exécuté automatiquement au premier démarrage du conteneur partner-db.

CREATE TABLE games (
    app_id              INTEGER PRIMARY KEY,
    name                TEXT,           -- nullable : le dataset source contient des jeux sans nom
    release_date        DATE,
    estimated_owners    TEXT,           -- fourchette telle que publiée : "20000 - 50000"
    peak_ccu            INTEGER,
    required_age        SMALLINT,
    price_usd           NUMERIC(8, 2),
    discount_pct        SMALLINT,
    dlc_count           INTEGER,
    windows             BOOLEAN,
    mac                 BOOLEAN,
    linux               BOOLEAN,
    metacritic_score    SMALLINT,
    user_score          SMALLINT,
    positive            INTEGER,
    negative            INTEGER,
    achievements        INTEGER,
    recommendations     INTEGER,
    avg_playtime_min    INTEGER,
    median_playtime_min INTEGER
);

-- Référentiels + tables d'association (relations n,n)
CREATE TABLE developers (developer_id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE publishers (publisher_id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE genres     (genre_id     SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE tags       (tag_id       SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE categories (category_id  SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);

CREATE TABLE game_developers (
    app_id INTEGER REFERENCES games ON DELETE CASCADE,
    developer_id INTEGER REFERENCES developers,
    PRIMARY KEY (app_id, developer_id)
);
CREATE TABLE game_publishers (
    app_id INTEGER REFERENCES games ON DELETE CASCADE,
    publisher_id INTEGER REFERENCES publishers,
    PRIMARY KEY (app_id, publisher_id)
);
CREATE TABLE game_genres (
    app_id INTEGER REFERENCES games ON DELETE CASCADE,
    genre_id INTEGER REFERENCES genres,
    PRIMARY KEY (app_id, genre_id)
);
CREATE TABLE game_tags (
    app_id INTEGER REFERENCES games ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags,
    tag_rank SMALLINT,          -- 1 = tag le plus voté par les joueurs
    PRIMARY KEY (app_id, tag_id)
);
CREATE TABLE game_categories (
    app_id INTEGER REFERENCES games ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories,
    PRIMARY KEY (app_id, category_id)
);
-- Volontairement AUCUN index secondaire ici : leur effet est mesuré
-- avec EXPLAIN ANALYZE dans sql/partner/02_optimisation.sql (C2).
