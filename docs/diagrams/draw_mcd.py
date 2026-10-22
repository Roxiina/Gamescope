"""Dessine le MCD Merise de GameScope (docs/img/mcd.png) pour le rapport.

Usage : python docs/diagrams/draw_mcd.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "img" / "mcd.png"
BLUE, DARK, RED = "#3D85C6", "#0B5394", "#990000"

# nom : (x, y, identifiant, [attributs])
ENTITIES = {
    "JEU": (11, 8, "app_id", ["nom", "date_sortie", "prix_eur, prix_initial_eur", "remise_pct, gratuit",
                              "age_requis", "proprietaires_min, _max", "note_metacritic",
                              "avis_positifs, avis_negatifs", "pct_positif", "pct_avis_recents",
                              "temps_jeu_moyen_min, _median", "pic_joueurs, nb_dlc", "nb_succes, nb_langues"]),
    "STATS_AVIS_2021": (11, 15.2, None, ["nb_avis, pct_recommande", "temps_jeu_median_min", "nb_langues"]),
    "DEVELOPPEUR": (1.9, 14.2, "id_developpeur", ["nom"]),
    "GENRE": (1.9, 11.3, "id_genre", ["nom"]),
    "CATEGORIE": (1.9, 8.4, "id_categorie", ["nom"]),
    "TAG": (1.9, 5.5, "id_tag", ["nom"]),
    "SYSTEME": (1.9, 2.6, "id_systeme", ["nom"]),
    "AVIS": (18.6, 12.2, "id_avis", ["texte, recommande", "votes_utiles", "temps_jeu_min, source",
                                      "date_publication", "date_collecte"]),
    "AUTEUR": (24.6, 14.6, "id_auteur", ["empreinte"]),
    "LANGUE": (24.6, 9.6, "id_langue", ["code"]),
    "VENTE": (18.6, 3.4, "id_vente", ["nom_vgsales, annee", "genre_vgsales", "ventes_na, _eu, _jp",
                                       "ventes_autres, _monde", "methode_rapprochement"]),
    "PLATEFORME": (24.6, 1.2, "id_plateforme", ["nom"]),
    "EDITEUR": (11, 0.9, "id_editeur", ["nom"]),
}
# association : (x, y, attribut, [(entité, cardinalité), ...])
ASSOCIATIONS = {
    "DÉVELOPPE": (5.6, 14.2, None, [("JEU", "0,n"), ("DEVELOPPEUR", "1,n")]),
    "APPARTIENT": (5.6, 11.3, None, [("JEU", "0,n"), ("GENRE", "1,n")]),
    "CLASSE": (5.6, 8.4, None, [("JEU", "0,n"), ("CATEGORIE", "1,n")]),
    "ÉTIQUETTE": (5.6, 5.5, "rang", [("JEU", "0,n"), ("TAG", "1,n")]),
    "FONCTIONNE_SUR": (5.6, 2.6, None, [("JEU", "0,n"), ("SYSTEME", "1,n")]),
    "RÉSUME": (11, 12.75, None, [("JEU", "0,1"), ("STATS_AVIS_2021", "(1,1)")]),  # identification relative
    "CONCERNE": (15.4, 10.6, None, [("JEU", "0,n"), ("AVIS", "1,1")]),
    "RÉDIGE": (21.2, 14.6, None, [("AUTEUR", "1,n"), ("AVIS", "1,1")]),
    "ÉCRIT_EN": (21.2, 10.4, None, [("AVIS", "0,1"), ("LANGUE", "1,n")]),
    "VEND": (15.4, 5.2, None, [("JEU", "0,n"), ("VENTE", "1,1")]),
    "SUR": (21.6, 2.0, None, [("VENTE", "1,1"), ("PLATEFORME", "1,n")]),
    "ÉDITE": (11, 3.15, None, [("JEU", "0,n"), ("EDITEUR", "0,n")]),
    "PUBLIE": (15.4, 1.6, None, [("VENTE", "0,1"), ("EDITEUR", "0,n")]),
}
LINE_H = 0.36


def entity_size(ident, attrs):
    lines = len(attrs) + (1 if ident else 0)
    width = max(len(s) for s in [*attrs, ident or "", "STATS_AVIS_2021"]) * 0.135 + 0.5
    return max(width, 2.6), 0.75 + lines * LINE_H


def main():
    fig, ax = plt.subplots(figsize=(17.6, 11.5))
    ax.set_xlim(-0.2, 26.6)
    ax.set_ylim(-0.3, 16.9)
    ax.axis("off")

    for name, (x, y, attr, links) in ASSOCIATIONS.items():
        for entity, card in links:
            ex, ey = ENTITIES[entity][:2]
            ax.plot([x, ex], [y, ey], color="#555555", lw=1.1, zorder=1)
            # Point de sortie du segment hors de la boîte de l'entité
            w, h = entity_size(*ENTITIES[entity][2:])
            dx, dy = x - ex, y - ey
            t_box = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
            bx, by = ex + dx * t_box, ey + dy * t_box
            # Cardinalité au milieu du segment visible, entre l'ellipse et le bord de l'entité
            dist = (dx ** 2 + dy ** 2) ** 0.5
            sx, sy = x - dx / dist * 0.8, y - dy / dist * 0.8
            lx, ly = (sx + bx) / 2, (sy + by) / 2
            ax.text(lx, ly, card, ha="center", va="center", fontsize=9.5,
                    color=RED, fontweight="bold", zorder=4,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.5))

    for name, (x, y, ident, attrs) in ENTITIES.items():
        w, h = entity_size(ident, attrs)
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02",
                                    facecolor="white", edgecolor=DARK, lw=1.6, zorder=2))
        top = y + h / 2
        ax.add_patch(FancyBboxPatch((x - w / 2, top - 0.55), w, 0.55, boxstyle="square,pad=0",
                                    facecolor=BLUE, edgecolor=DARK, lw=1.6, zorder=2))
        ax.text(x, top - 0.28, name, ha="center", va="center", fontsize=10.5,
                fontweight="bold", color="white", zorder=3)
        rows = ([ident] if ident else []) + attrs
        for i, row in enumerate(rows):
            text = ax.text(x - w / 2 + 0.18, top - 0.82 - i * LINE_H, row, ha="left", va="center",
                           fontsize=8.6, zorder=3, fontweight="bold" if row == ident else "normal")
            if row == ident:  # identifiant souligné (convention Merise)
                fig.canvas.draw()
                box = text.get_window_extent().transformed(ax.transData.inverted())
                ax.plot([box.x0, box.x1], [box.y0 - 0.02] * 2, color="black", lw=0.9, zorder=3)

    for name, (x, y, attr, _) in ASSOCIATIONS.items():
        w = max(len(name) * 0.16 + 0.7, 1.9)
        h = 1.05 if attr else 0.72
        ax.add_patch(Ellipse((x, y), w, h, facecolor="#FDF3E7", edgecolor=RED, lw=1.4, zorder=2))
        ax.text(x, y + (0.15 if attr else 0), name, ha="center", va="center", fontsize=8.6,
                fontweight="bold", color=RED, zorder=3)
        if attr:
            ax.text(x, y - 0.22, attr, ha="center", va="center", fontsize=8.4, zorder=3)

    ax.text(0, 16.6, "MCD GameScope (Merise) : identifiants soulignés, cardinalités (min,max) "
            "lues depuis l'entité", fontsize=10, color="#444444")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=170, bbox_inches="tight", facecolor="white")
    print(f"MCD écrit dans {OUT}")


if __name__ == "__main__":
    main()
