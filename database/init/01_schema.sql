-- =====================================================================
-- GameScope - Modèle Physique des Données (PostgreSQL 17)
-- Dérivé du MLD (docs/merise.md). Exécuté automatiquement à la création
-- du conteneur gamescope-db (docker-entrypoint-initdb.d).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table centrale
-- ---------------------------------------------------------------------
CREATE TABLE game (
    app_id              INTEGER       PRIMARY KEY,          -- identifiant Steam
    name                VARCHAR(255)  NOT NULL,
    release_date        DATE          NOT NULL,
    price_eur           NUMERIC(7, 2) CHECK (price_eur >= 0),
    price_initial_eur   NUMERIC(7, 2) CHECK (price_initial_eur >= 0),
    discount_pct        SMALLINT      CHECK (discount_pct BETWEEN 0 AND 100),
    is_free             BOOLEAN       NOT NULL,
    required_age        SMALLINT      CHECK (required_age BETWEEN 0 AND 21),
    owners_min          INTEGER       CHECK (owners_min >= 0),
    owners_max          INTEGER       CHECK (owners_max >= owners_min),
    metacritic_score    SMALLINT      CHECK (metacritic_score BETWEEN 1 AND 100),
    positive_reviews    INTEGER       CHECK (positive_reviews >= 0),
    negative_reviews    INTEGER       CHECK (negative_reviews >= 0),
    pct_positive        NUMERIC(5, 2) CHECK (pct_positive BETWEEN 0 AND 100),
    recent_review_pct   SMALLINT      CHECK (recent_review_pct BETWEEN 0 AND 100),
    recent_review_count INTEGER,
    recent_review_desc  VARCHAR(40),
    avg_playtime_min    INTEGER,
    median_playtime_min INTEGER,
    peak_ccu            INTEGER,
    dlc_count           INTEGER,
    achievements        INTEGER,
    recommendations     INTEGER,
    languages_count     SMALLINT,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Statistiques big data 2021 : seuls ~230 jeux sont concernés.
-- Table séparée (cardinalité 0,1) plutôt que 4 colonnes NULL sur 1 982 lignes.
CREATE TABLE game_review_stats_2021 (
    app_id                  INTEGER PRIMARY KEY REFERENCES game ON DELETE CASCADE,
    nb_reviews              INTEGER NOT NULL CHECK (nb_reviews > 0),
    pct_recommended         NUMERIC(5, 2) CHECK (pct_recommended BETWEEN 0 AND 100),
    median_playtime_min     INTEGER,
    nb_languages            SMALLINT
);

-- ---------------------------------------------------------------------
-- Référentiels (relations n,n avec game)
-- ---------------------------------------------------------------------
CREATE TABLE developer        (developer_id SERIAL   PRIMARY KEY, name VARCHAR(150) NOT NULL UNIQUE);
CREATE TABLE publisher        (publisher_id SERIAL   PRIMARY KEY, name VARCHAR(150) NOT NULL UNIQUE);
CREATE TABLE genre            (genre_id     SMALLSERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL UNIQUE);
CREATE TABLE category         (category_id  SMALLSERIAL PRIMARY KEY, name VARCHAR(60) NOT NULL UNIQUE);
CREATE TABLE tag              (tag_id       SMALLSERIAL PRIMARY KEY, name VARCHAR(50) NOT NULL UNIQUE);
CREATE TABLE operating_system (os_id        SMALLSERIAL PRIMARY KEY, name VARCHAR(10) NOT NULL UNIQUE);

CREATE TABLE game_developer (
    app_id       INTEGER REFERENCES game ON DELETE CASCADE,
    developer_id INTEGER REFERENCES developer,
    PRIMARY KEY (app_id, developer_id)
);
CREATE TABLE game_publisher (
    app_id       INTEGER REFERENCES game ON DELETE CASCADE,
    publisher_id INTEGER REFERENCES publisher,
    PRIMARY KEY (app_id, publisher_id)
);
CREATE TABLE game_genre (
    app_id   INTEGER  REFERENCES game ON DELETE CASCADE,
    genre_id SMALLINT REFERENCES genre,
    PRIMARY KEY (app_id, genre_id)
);
CREATE TABLE game_category (
    app_id      INTEGER  REFERENCES game ON DELETE CASCADE,
    category_id SMALLINT REFERENCES category,
    PRIMARY KEY (app_id, category_id)
);
CREATE TABLE game_tag (
    app_id   INTEGER  REFERENCES game ON DELETE CASCADE,
    tag_id   SMALLINT REFERENCES tag,
    tag_rank SMALLINT NOT NULL CHECK (tag_rank >= 1),  -- 1 = tag le plus voté
    PRIMARY KEY (app_id, tag_id)
);
CREATE TABLE game_os (
    app_id INTEGER  REFERENCES game ON DELETE CASCADE,
    os_id  SMALLINT REFERENCES operating_system,
    PRIMARY KEY (app_id, os_id)
);

-- ---------------------------------------------------------------------
-- Avis et auteurs (DONNÉES PERSONNELLES - voir docs/rgpd/)
-- ---------------------------------------------------------------------
CREATE TABLE language (
    language_id SMALLSERIAL PRIMARY KEY,
    code        VARCHAR(10) NOT NULL UNIQUE      -- BCP 47 : en, zh-Hans, pt-BR
);

-- Auteur pseudonymisé : seul un hash SHA-256 salé du steamid est stocké.
-- Table dédiée : un avis référence un entier (4 octets) au lieu de répéter
-- le hash (65 octets), et l'effacement d'un auteur supprime ses avis en cascade.
CREATE TABLE author (
    author_id   SERIAL   PRIMARY KEY,
    author_hash CHAR(64) NOT NULL UNIQUE
);

CREATE TABLE review (
    review_id           BIGINT      PRIMARY KEY,     -- identifiant Steam
    app_id              INTEGER     NOT NULL REFERENCES game ON DELETE CASCADE,
    author_id           INTEGER     NOT NULL REFERENCES author ON DELETE CASCADE,
    language_id         SMALLINT    REFERENCES language,
    review_text         TEXT        NOT NULL CHECK (length(review_text) > 0),
    recommended         BOOLEAN     NOT NULL,
    votes_helpful       INTEGER     CHECK (votes_helpful >= 0),
    author_playtime_min INTEGER     CHECK (author_playtime_min >= 0),
    source              VARCHAR(15) NOT NULL CHECK (source IN ('steam_api', 'bigdata_2021')),
    created_at          TIMESTAMPTZ NOT NULL,        -- publication sur Steam
    collected_at        TIMESTAMPTZ NOT NULL         -- collecte : base de la durée de conservation
);

-- ---------------------------------------------------------------------
-- Ventes consoles et PC (vgsales)
-- ---------------------------------------------------------------------
CREATE TABLE platform (
    platform_id SMALLSERIAL PRIMARY KEY,
    name        VARCHAR(30) NOT NULL UNIQUE      -- PlayStation 2, Xbox 360, PC...
);

CREATE TABLE sale (
    sale_id            SERIAL       PRIMARY KEY,
    app_id             INTEGER      NOT NULL REFERENCES game ON DELETE CASCADE,
    platform_id        SMALLINT     NOT NULL REFERENCES platform,
    publisher_id       INTEGER      REFERENCES publisher,
    vgsales_name       VARCHAR(255) NOT NULL,
    release_year       SMALLINT     CHECK (release_year BETWEEN 1970 AND 2030),
    vgsales_genre      VARCHAR(20),
    sales_na_units     INTEGER      NOT NULL CHECK (sales_na_units >= 0),
    sales_eu_units     INTEGER      NOT NULL CHECK (sales_eu_units >= 0),
    sales_jp_units     INTEGER      NOT NULL CHECK (sales_jp_units >= 0),
    sales_other_units  INTEGER      NOT NULL CHECK (sales_other_units >= 0),
    sales_global_units INTEGER      NOT NULL CHECK (sales_global_units >= 0),
    match_method       VARCHAR(10)  NOT NULL CHECK (match_method IN ('exact', 'compact', 'fuzzy')),
    -- Clé naturelle : rend l'import idempotent (PostgreSQL 15+ pour NULLS NOT DISTINCT)
    UNIQUE NULLS NOT DISTINCT (app_id, platform_id, vgsales_name, release_year)
);

-- ---------------------------------------------------------------------
-- Comptes de l'API (DONNÉES PERSONNELLES - utilisés en C5)
-- ---------------------------------------------------------------------
CREATE TABLE api_user (
    user_id       SERIAL       PRIMARY KEY,
    email         VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,             -- bcrypt, jamais le mot de passe
    role          VARCHAR(20)  NOT NULL CHECK (role IN ('reader', 'analyst', 'admin')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Journal des traitements de conformité (principe de responsabilité, art. 5.2 RGPD)
CREATE TABLE rgpd_log (
    log_id        SERIAL       PRIMARY KEY,
    executed_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    action        VARCHAR(60)  NOT NULL,
    table_name    VARCHAR(30)  NOT NULL,
    rows_affected INTEGER      NOT NULL,
    detail        TEXT
);

-- ---------------------------------------------------------------------
-- Index secondaires (les clés primaires et UNIQUE sont déjà indexées)
-- ---------------------------------------------------------------------
-- Accès inverse des associations : "jeux d'un genre / d'un tag" (filtres de l'API)
CREATE INDEX idx_game_genre_genre     ON game_genre (genre_id);
CREATE INDEX idx_game_tag_tag         ON game_tag (tag_id);
CREATE INDEX idx_game_developer_dev   ON game_developer (developer_id);
CREATE INDEX idx_game_publisher_pub   ON game_publisher (publisher_id);
-- Clés étrangères les plus sollicitées
CREATE INDEX idx_review_app           ON review (app_id);
CREATE INDEX idx_review_author        ON review (author_id);
CREATE INDEX idx_sale_app             ON sale (app_id);
-- Tri et filtres fréquents
CREATE INDEX idx_game_release_date    ON game (release_date);
-- Purge RGPD : recherche des avis collectés il y a plus de N ans
CREATE INDEX idx_review_collected_at  ON review (collected_at);
