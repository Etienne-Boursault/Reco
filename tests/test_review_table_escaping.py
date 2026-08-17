"""Tests d'ÉCHAPPEMENT de la page /tableau (`tools/review_table.py`).

POURQUOI CES TESTS SONT À PART, ET POURQUOI ILS SONT ÉCRITS AINSI
----------------------------------------------------------------
Les tests d'échappement d'origine étaient de la forme :

    assert "<script>boom" not in sortie

C'est une assertion faible, et elle se trompe dans les DEUX sens :

  - elle passe alors qu'une injection a réussi, dès que la charge prend une
    autre forme — `<img onerror=…>`, ou la fermeture d'un attribut suivie d'un
    gestionnaire d'événement, qui ne contiennent aucune balise `<script>` ;
  - elle échoue sur du texte parfaitement échappé, `&lt;script&gt;boom` restant
    une sous-chaîne acceptable selon la manière dont on cherche.

J'ai moi-même écrit un test de ce genre dans cette EPIC, et il a produit une
fausse alerte de sécurité qu'il a fallu trois tentatives pour lever.

L'assertion retenue ici porte donc sur le SQUELETTE du document : on retire le
CONTENU des valeurs d'attributs, et ce qui reste est exactement l'ensemble des
balises et des attributs que le navigateur créera. Une charge hostile ne peut
alors se manifester que d'une seule façon — en y faisant apparaître une balise
ou un gestionnaire qui n'y était pas.

La page est construite par f-strings, sans moteur de gabarit : rien n'échappe
par défaut. C'est précisément pourquoi l'invariant mérite d'être vérifié sur
CHAQUE champ, et non sur le titre seulement.
"""
from __future__ import annotations

import re

import review_table as rtab
from fixtures_review_table import _patch, _reco

# Trois familles de charges, parce qu'elles n'exploitent pas la même faiblesse.
CHARGES = [
    # Injection de balise : échoue dès que `<` est échappé.
    '<script>alert(1)</script>',
    # Gestionnaire d'événement : ne contient AUCUNE balise `<script>`, et passe
    # donc sous le radar de l'assertion par sous-chaîne.
    '<img src=x onerror=alert(1)>',
    # Sortie d'attribut : la seule qui compte vraiment ici, puisque presque
    # toutes les données de la page atterrissent dans des attributs `data-*`.
    '" onmouseover="alert(1)" x="',
    # Sortie d'attribut à guillemet simple.
    "' onfocus='alert(1)' y='",
    # Fermeture d'un conteneur textuel : le commentaire est rendu dans un
    # `<textarea>`, où `</textarea>` suffit à sortir du contexte.
    '</textarea><script>boom</script>',
]

# Balises légitimement présentes dans la page. Toute AUTRE balise apparaissant
# après injection est le signe que la charge a été interprétée.
BALISES_ATTENDUES = {
    'html', 'head', 'meta', 'title', 'style', 'body', 'main', 'header', 'h1',
    'h2', 'h3', 'p', 'div', 'span', 'nav', 'a', 'table', 'thead', 'tbody',
    'tr', 'th', 'td', 'button', 'input', 'label', 'textarea', 'select',
    'option', 'form', 'script', 'iframe', 'svg', 'path', 'small', 'strong',
    'em', 'br', 'details', 'summary', 'ul', 'li', 'ol', 'dl', 'dt', 'dd',
    'audio', 'section', 'figure', 'template',
}


def squelette(html: str) -> str:
    """Le document PRIVÉ du contenu de ses attributs.

    Sans cette étape, toute recherche se trompe de cible : une expression
    régulière voit `data-k-title="<script>…"` et croit à une balise, alors que
    le navigateur n'y lit qu'une chaîne de caractères.
    """
    return re.sub(r'="[^"]*"', '=""', html)


def _sans_corps_de_code(html: str) -> str:
    """Vide le CONTENU des `<script>` et `<style>`, en gardant leurs balises.

    La page embarque son JavaScript, où une comparaison comme `i < drag.length`
    ressemble trait pour trait à l'ouverture d'une balise `<drag>`. Sans ce
    nettoyage, le détecteur de balises signalait `drag` comme une injection —
    un faux positif produit par le test, pas par le code.

    Les balises SONT conservées : les supprimer masquerait un `<script>`
    réellement injecté, c'est-à-dire exactement ce qu'on cherche.
    """
    return re.sub(r'(<(script|style)\b[^>]*>).*?(</\2\s*>)', r'\1\3',
                  html, flags=re.DOTALL | re.IGNORECASE)


def balises_de(html: str) -> set[str]:
    return {m.lower() for m in
            re.findall(r'<\s*([a-zA-Z][a-zA-Z0-9]*)', _sans_corps_de_code(html))}


def attribut_present(html: str, nom: str) -> bool:
    """L'attribut `nom` figure-t-il DANS une balise ?

    La contrainte « dans une balise » est ce qui sépare une vraie injection du
    même texte rendu inoffensif : `&quot; onmouseover=&quot;` est une chaîne
    affichée, pas un gestionnaire d'événement. Chercher le simple mot déclenche
    sur le second — c'est le faux positif que ce fichier documente, et dans
    lequel sa propre première version est retombée.
    """
    return re.search(rf'<[a-zA-Z][^>]*\s{nom}\s*=', html, re.IGNORECASE) is not None


def _page_hostile(monkeypatch, charge: str) -> str:
    """La page rendue avec la charge dans TOUS les champs libres à la fois."""
    _patch(
        monkeypatch,
        [_reco("ubm-1", title=charge, creator=charge, recommendedBy=charge,
               types=["film"],
               links=[{"url": "https://exemple.fr/a", "label": charge}])],
        episodes={"g1": {"guid": "g1", "title": charge, "season": 1,
                         "number": 3, "date": "2021-02-14"}},
        curation={"ubm-1": {"comment": charge, "checked": True}},
    )
    return rtab.render_table_page("src", flash=charge, flash_kind="info")


# ---------------------------------------------------------------------------
# L'invariant, sur chaque famille de charges
# ---------------------------------------------------------------------------
def test_aucune_charge_ne_cree_de_balise(monkeypatch):
    """Aucune charge ne doit faire APPARAÎTRE une balise absente de la page saine."""
    _patch(monkeypatch, [_reco("ubm-1")], curation={"ubm-1": {"comment": "ok"}})
    saines = balises_de(squelette(rtab.render_table_page("src")))
    # Garde-fou : si la page de référence contenait déjà une balise inattendue,
    # la comparaison ci-dessous serait faussée dès le départ.
    assert saines <= BALISES_ATTENDUES, saines - BALISES_ATTENDUES

    for charge in CHARGES:
        sortie = squelette(_page_hostile(monkeypatch, charge))
        assert balises_de(sortie) <= BALISES_ATTENDUES, (
            f"charge « {charge} » : balises inattendues "
            f"{balises_de(sortie) - BALISES_ATTENDUES}")


def test_aucune_charge_ne_cree_de_gestionnaire_devenement(monkeypatch):
    """`on…=` ne doit jamais apparaître À L'INTÉRIEUR d'une balise.

    La contrainte « dans une balise » est essentielle : cherchée sans elle,
    l'expression se déclenche sur le texte échappé `&lt;img … onerror=…&gt;`,
    qui est inoffensif. C'est exactement le faux positif dans lequel la
    première version de ces tests est tombée.
    """
    for charge in CHARGES:
        sortie = squelette(_page_hostile(monkeypatch, charge))
        trouve = re.search(r'<[a-zA-Z][^>]*\son[a-zA-Z]+\s*=', sortie)
        assert trouve is None, f"charge « {charge} » : {trouve.group(0)!r}"


def test_aucune_charge_nouvre_de_bloc_script(monkeypatch):
    """La page embarque son propre `<script>` : on compte, on ne cherche pas.

    Une assertion « pas de `<script>` » serait fausse par construction ici. Ce
    qui doit rester constant, c'est le NOMBRE de blocs.
    """
    _patch(monkeypatch, [_reco("ubm-1")])
    attendu = squelette(rtab.render_table_page("src")).lower().count('<script')
    for charge in CHARGES:
        sortie = squelette(_page_hostile(monkeypatch, charge)).lower()
        assert sortie.count('<script') == attendu, f"charge « {charge} »"


def test_le_texte_hostile_reste_lisible(monkeypatch):
    """Échapper ne doit pas ESCAMOTER la donnée.

    Sans cette vérification, un rendu qui supprimerait purement et simplement
    les champs suspects passerait tous les tests ci-dessus — en cassant
    l'outil : on ne verrait plus les recos dont le titre contient un chevron.
    """
    sortie = _page_hostile(monkeypatch, '<script>alert(1)</script>')
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in sortie


def test_le_guillemet_est_echappe_dans_les_attributs(monkeypatch):
    """La sortie d'attribut est la voie réellement exploitable ici, presque
    toutes les données partant dans des `data-*`."""
    sortie = _page_hostile(monkeypatch, '" onmouseover="alert(1)" x="')
    assert '&quot;' in sortie
    # Aucune BALISE ne doit porter l'attribut : le mot lui-même figure bien
    # dans la page, mais sous forme de texte échappé — donc inoffensif.
    assert not attribut_present(squelette(sortie), 'onmouseover')


# ---------------------------------------------------------------------------
# Le seul fragment volontairement NON ré-échappé
# ---------------------------------------------------------------------------
def test_la_cellule_timecode_ne_recoit_jamais_de_saisie_libre(monkeypatch):
    """`tc_html` est inséré tel quel (il vient de `_yt_timecode_link`, déjà
    échappé). L'exception ne tient que tant que ce fragment ne dépend d'AUCUN
    champ libre : on le vérifie plutôt que de s'en remettre au commentaire qui
    l'affirme."""
    sortie = _page_hostile(monkeypatch, '<script>alert(1)</script>')
    cellule = re.search(r'<td class="tbl-c-timecode">.*?</td>', sortie, re.DOTALL)
    assert cellule is not None
    assert '<script>alert' not in cellule.group(0)
