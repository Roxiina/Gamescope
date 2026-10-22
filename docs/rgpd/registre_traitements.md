# Registre des traitements de données personnelles - GameScope

Registre tenu au titre de l'article 30 du RGPD, sur le modèle proposé par la CNIL.
Dernière mise à jour : 22/10/2026.

## Responsable du traitement

> **Projet personnel et RGPD.** L'exemption « usage strictement personnel ou domestique »
> (art. 2.2.c) ne s'applique pas : les données de tiers sont collectées à grande
> échelle et l'API peut ouvrir un accès à d'autres personnes. Le registre est donc
> tenu comme pour un traitement professionnel.

| | |
|---|---|
| Organisme | Projet personnel GameScope (réalisé dans le cadre de la formation Simplon) |
| Responsable de la mise en œuvre | Responsable data du projet GameScope |
| Contact pour l'exercice des droits | adresse dédiée à communiquer sur la page d'information du projet |
| Délégué à la protection des données (DPO) | non désigné (non obligatoire : pas de traitement à grande échelle de données sensibles ni de suivi systématique) |

---

## Traitement n°1 : collecte et analyse des avis de joueurs Steam

| Rubrique | Description |
|---|---|
| **Finalité** | Analyser la réception des jeux vidéo (taux de recommandation, sentiment exprimé, temps de jeu) pour orienter la conception de mon futur jeu vidéo sur Steam (genre, prix, attentes des joueurs). Sert aussi à entraîner un modèle d'analyse de sentiment (blocs E2/E3). |
| **Base légale** | Intérêt légitime (art. 6.1.f) : les avis sont **publiés volontairement** et publiquement par leurs auteurs sur Steam, et l'analyse est statistique et agrégée. Elle ne vise aucune personne en particulier. |
| **Personnes concernées** | Auteurs d'avis publics sur le Steam Store |
| **Données collectées** | Empreinte de l'identifiant Steam (SHA-256 salé), texte de l'avis, recommandation (oui/non), langue, date de publication, temps de jeu au moment de l'avis, nombre de votes « utile » |
| **Données exclues (minimisation)** | steamid en clair, pseudo, avatar, URL du profil, nombre de jeux possédés, date de dernière connexion. Les e-mails et liens présents dans le texte sont masqués (`[email]`, `[lien]`). |
| **Données sensibles (art. 9)** | Aucune collectée volontairement. Un texte libre peut en contenir de façon fortuite, d'où le masquage des coordonnées et la durée de conservation limitée. |
| **Sources** | API publique du Steam Store (`appreviews`) ; jeu de données public Kaggle *Steam Reviews 2021* |
| **Destinataires** | Équipe data du projet (rôle `gamescope_analyst`, lecture seule) ; API GameScope (rôle `gamescope_api`). Aucune cession à des tiers. |
| **Transferts hors UE** | Aucun : base hébergée en France / UE |
| **Durée de conservation** | **3 ans à compter de la collecte** (`collected_at`), puis suppression automatique. Un auteur sans plus aucun avis est supprimé. |
| **Mesures de sécurité** | Pseudonymisation dès la collecte, avant toute écriture sur disque ; sel secret hors du code (`.env`, non versionné) ; rôles PostgreSQL à moindre privilège ; accès API authentifié (C5) ; journalisation des purges (`rgpd_log`) |
| **Droits des personnes** | Information : page d'information du projet. Effacement et opposition : sur communication de son steamid, la personne obtient la suppression de tous ses avis (`rgpd_cleanup.py --erase-steamid`). Accès : sur la même base, extraction de ses avis. |

## Traitement n°2 : gestion des comptes d'accès à l'API

| Rubrique | Description |
|---|---|
| **Finalité** | Authentifier les utilisateurs de l'API GameScope et contrôler leurs droits (lecture, analyse, administration) |
| **Base légale** | Exécution d'un contrat ou de mesures précontractuelles (art. 6.1.b) : fourniture du service d'accès aux données |
| **Personnes concernées** | Responsable du projet et personnes auxquelles un accès est ouvert (collaborateurs, testeurs) |
| **Données collectées** | Adresse e-mail professionnelle, empreinte du mot de passe (bcrypt, jamais le mot de passe), rôle, date de création, date de dernière connexion |
| **Destinataires** | Administrateurs de l'API uniquement. La table est **inaccessible** au rôle `gamescope_analyst`. |
| **Transferts hors UE** | Aucun |
| **Durée de conservation** | Durée d'utilisation du compte. **Suppression automatique après 2 ans sans connexion.** |
| **Mesures de sécurité** | Hachage bcrypt des mots de passe ; jetons JWT à durée limitée ; HTTPS ; rôle PostgreSQL dédié |
| **Droits des personnes** | Accès, rectification, effacement : sur demande à l'administrateur |

## Traitement n°3 : journal des opérations de conformité

| Rubrique | Description |
|---|---|
| **Finalité** | Démontrer la conformité (principe de responsabilité, art. 5.2) : prouver que les purges et effacements ont bien été exécutés |
| **Base légale** | Obligation légale (art. 6.1.c) |
| **Données** | Date, type d'opération, table, nombre de lignes. **Aucune donnée identifiante** : le steamid d'une demande d'effacement n'est pas journalisé. |
| **Durée de conservation** | 5 ans |

---

## Données non personnelles (hors registre)

Les tables `game`, `sale`, les référentiels (genres, tags, développeurs, éditeurs…) et
`game_review_stats_2021` (statistiques agrégées) ne contiennent pas de données personnelles.
Les noms de développeurs et d'éditeurs désignent des **personnes morales**.

## Analyse d'impact (AIPD)

Non requise : le traitement ne remplit pas 2 des 9 critères de la CNIL. Il n'y a pas
de données sensibles collectées volontairement, pas d'évaluation ni de notation des
personnes, pas de décision automatisée et pas de croisement à des fins de profilage.
Les données sont pseudonymisées.
