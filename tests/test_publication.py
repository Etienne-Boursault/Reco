"""Tests de `tools/publication.py` — venus pousse un épisode relu sur GitHub.

Le git est RÉEL : chaque test monte un dépôt temporaire et un `origin` nu
(`git init --bare`), et la poussée est vraiment faite. Un double qui dirait oui à
tout ne prouverait rien de ce qui compte ici — que la branche distante porte le
commit attendu avant qu'on retire quoi que ce soit du clone.

Aucun test ne touche au dépôt Reco ni au réseau : `origin` est un chemin local et
l'ouverture de PR passe par un poseur injecté.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import publication as pub

SOURCE = "demo-source"
GUID = "yt-abc"


def _git(racine: Path, *args: str) -> str:
    fini = subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return (fini.stdout or "").strip()


def _ecrire(chemin: Path, contenu: dict) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return chemin


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Un clone sur `main`, son `origin` nu, et le corpus branché dessus.

    Reproduit la situation de venus : `main` est à jour, et les fichiers du
    nouvel épisode sont là, non suivis par git.
    """
    import common

    origine = tmp_path / "origine.git"
    racine = tmp_path / "clone"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origine))
    racine.mkdir()
    _git(racine, "init", "-b", "main")
    _git(racine, "remote", "add", "origin", str(origine))
    _git(racine, "config", "user.name", "Reco (essai)")
    _git(racine, "config", "user.email", "essai@example.test")
    (racine / "LISEZMOI.md").write_text("dépôt d'essai\n", encoding="utf-8")
    # Un corpus DÉJÀ suivi, comme sur venus : sans lui, git annoncerait le dossier
    # neuf « src/content/ » et non les fichiers, et le périmètre serait faux.
    _ecrire(racine / "src/content/recos" / SOURCE / "0001.json",
            {"id": "ubm-0001", "episodeGuid": "yt-ancien", "sourceId": SOURCE,
             "title": "Reco d'un ancien épisode", "types": ["album"], "status": "validated"})
    _ecrire(racine / "src/content/episodes" / SOURCE / "yt-ancien.json",
            {"sourceId": SOURCE, "guid": "yt-ancien", "title": "Ancien"})
    _git(racine, "add", "LISEZMOI.md", "src")
    _git(racine, "commit", "-m", "depart")
    _git(racine, "push", "-u", "origin", "main")

    contenu = racine / "src" / "content"
    for nom, sous in (("CONTENT_DIR", ""), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos")):
        monkeypatch.setattr(common, nom, contenu / sous if sous else contenu)
    monkeypatch.setattr(common, "PROJECT_ROOT", racine)
    return racine


def _episode(racine: Path, guid: str = GUID) -> Path:
    return _ecrire(racine / "src/content/episodes" / SOURCE / f"{guid.lower()}.json",
                   {"sourceId": SOURCE, "guid": guid, "title": f"Titre {guid}"})


def _reco(racine: Path, numero: str, reco_id: str, *, guid: str = GUID,
          status: str = "validated") -> Path:
    return _ecrire(racine / "src/content/recos" / SOURCE / f"{numero}.json",
                   {"id": reco_id, "episodeGuid": guid, "sourceId": SOURCE,
                    "title": f"Titre {reco_id}", "types": ["album"], "status": status})


def _mention(racine: Path, reco_id: str, item_id: str) -> Path:
    return _ecrire(racine / "src/content/mentions" / SOURCE / f"{reco_id}.json",
                   {"id": reco_id, "itemId": item_id})


def _item(racine: Path, item_id: str) -> Path:
    return _ecrire(racine / "src/content/items" / SOURCE / f"{item_id}.json",
                   {"id": item_id, "title": "Une œuvre"})


def _episode_complet(racine: Path) -> None:
    _episode(racine)
    _reco(racine, "3001", "ubm-3001")
    _mention(racine, "ubm-3001", "aaa111")
    _item(racine, "aaa111")


def _publier(racine: Path, **kwargs):
    return pub.publier_episode(SOURCE, GUID, f"Titre {GUID}",
                               racine / "src/content/episodes" / SOURCE / f"{GUID.lower()}.json",
                               racine=racine, **kwargs)


# ===== le chemin heureux =====================================================
def test_the_episode_lands_on_a_remote_branch_and_leaves_the_clone_clean(depot):
    _episode_complet(depot)

    resultat = _publier(depot)

    assert not resultat.refuse and resultat.branche == "contenu/yt-abc"
    # La branche distante porte bien le commit : c'est la condition du nettoyage.
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/yt-abc").split()[0] \
        == resultat.sha
    # `main` est revenu sur `origin/main` : le prochain « git pull --ff-only » passe.
    assert _git(depot, "rev-parse", "HEAD") == _git(depot, "rev-parse", "origin/main")
    assert _git(depot, "status", "--porcelain") == ""
    assert not (depot / "src/content/recos" / SOURCE / "3001.json").exists()


def test_only_the_files_of_that_episode_are_committed(depot):
    _episode_complet(depot)
    _episode(depot, "yt-autre")
    _reco(depot, "3002", "ubm-3002", guid="yt-autre")

    resultat = _publier(depot)

    assert resultat.refus.startswith("le clone porte des modifications étrangères")
    assert "yt-autre" in resultat.refus
    # Rien n'a été commité ni retiré : le travail de l'autre épisode est intact.
    assert _git(depot, "rev-parse", "HEAD") == _git(depot, "rev-parse", "origin/main")
    assert (depot / "src/content/recos" / SOURCE / "3002.json").exists()


def test_the_commit_carries_the_episode_and_its_works(depot):
    _episode_complet(depot)

    resultat = _publier(depot)

    fichiers = _git(depot, "show", "--name-only", "--pretty=format:", resultat.sha).split()
    assert sorted(fichiers) == [
        "src/content/episodes/demo-source/yt-abc.json",
        "src/content/items/demo-source/aaa111.json",
        "src/content/mentions/demo-source/ubm-3001.json",
        "src/content/recos/demo-source/3001.json",
    ]


def test_a_work_reused_from_another_episode_is_not_committed_twice(depot):
    """Une œuvre déjà suivie par git n'a rien à ajouter : elle est simplement là."""
    _item(depot, "bbb222")
    _git(depot, "add", "src/content/items/demo-source/bbb222.json")
    _git(depot, "commit", "-m", "oeuvre deja publiee")
    _git(depot, "push", "origin", "main")
    _episode(depot)
    _reco(depot, "3001", "ubm-3001")
    _mention(depot, "ubm-3001", "bbb222")

    resultat = _publier(depot)

    assert not resultat.refuse
    fichiers = _git(depot, "show", "--name-only", "--pretty=format:", resultat.sha).split()
    assert "src/content/items/demo-source/bbb222.json" not in fichiers
    # Et elle reste sur le disque : on n'a retiré que ce qu'on venait de pousser.
    assert (depot / "src/content/items" / SOURCE / "bbb222.json").exists()


# ===== les refus =============================================================
def test_a_draft_reco_stops_everything(depot):
    _episode(depot)
    _reco(depot, "3001", "ubm-3001")
    _reco(depot, "3002", "ubm-3002", status="draft")

    resultat = _publier(depot)

    assert resultat.refus == "1 reco(s) encore en brouillon"
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/yt-abc") == ""


def test_an_episode_without_recos_is_refused(depot):
    _episode(depot)

    assert _publier(depot).refus == "aucune reco pour cet épisode"


def test_an_episode_already_on_main_pushes_nothing(depot):
    """Le vrai cas d'idempotence : la PR a été fusionnée, les fichiers sont suivis.

    L'état de la chaîne suffit d'ordinaire à ne pas repasser, mais s'il était
    perdu, un second passage ne doit ni commiter à vide ni repousser.
    """
    _episode_complet(depot)
    _git(depot, "add", "src")
    _git(depot, "commit", "-m", "fusion de la PR")
    _git(depot, "push", "origin", "main")

    resultat = _publier(depot)

    assert resultat.deja_publie and not resultat.refuse and resultat.branche == ""
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/yt-abc") == ""


def test_after_publication_the_files_are_gone_and_nothing_is_pushed_again(depot):
    """Deux passages de suite ne créent pas deux commits.

    Après la poussée, les fichiers ont quitté le clone : l'épisode n'a plus de
    reco à publier. C'est l'état de la chaîne qui l'écarte des passages suivants
    (`published`), et un appel direct refuse sans rien pousser.
    """
    _episode_complet(depot)
    premier = _publier(depot)

    second = _publier(depot)

    assert second.refus == "aucune reco pour cet épisode"
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/yt-abc").split()[0] \
        == premier.sha


def test_nothing_is_deleted_when_the_push_fails(depot, monkeypatch):
    _episode_complet(depot)
    monkeypatch.setattr(pub.Git, "pousser",
                        lambda *_a, **_k: (_ for _ in ()).throw(pub.ErreurGit("réseau coupé")))

    with pytest.raises(pub.ErreurGit):
        _publier(depot)

    assert (depot / "src/content/recos" / SOURCE / "3001.json").exists()
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/yt-abc") == ""


def test_a_remote_branch_without_our_commit_stops_the_cleanup(depot, monkeypatch):
    """Si la vérification de la poussée échoue, le clone garde ses fichiers."""
    _episode_complet(depot)
    monkeypatch.setattr(pub.Git, "sha_distant", lambda *_a, **_k: "0000000")

    resultat = _publier(depot)

    assert resultat.refus.startswith("la branche distante ne porte pas le commit")
    assert (depot / "src/content/recos" / SOURCE / "3001.json").exists()


# ===== la PR =================================================================
def test_without_a_token_the_message_carries_the_comparison_link(depot):
    _episode_complet(depot)
    _git(depot, "remote", "set-url", "origin", "git@github.com:Ed/Reco.git")
    # `origin` ne répond plus : on n'a besoin que de l'URL pour le lien.
    _git(depot, "remote", "add", "pousser", str(depot.parent / "origine.git"))

    resultat = _publier(depot, git=_git_qui_pousse_ailleurs(depot))

    assert not resultat.pr_ouverte
    assert resultat.lien == ("https://github.com/Ed/Reco/compare/main...contenu/yt-abc"
                             "?expand=1")


def _git_qui_pousse_ailleurs(racine: Path) -> pub.Git:
    """Un Git qui lit l'URL GitHub déclarée mais pousse vers le dépôt nu local."""
    class GitDetourne(pub.Git):
        def pousser(self, branche: str) -> None:
            self._git("push", "pousser", f"HEAD:refs/heads/{branche}")

        def sha_distant(self, branche: str) -> str:
            sortie = self._git("ls-remote", "pousser", f"refs/heads/{branche}")
            return sortie.split()[0] if sortie else ""

    return GitDetourne(racine)


def test_with_a_token_the_pull_request_is_opened(depot):
    _episode_complet(depot)
    _git(depot, "remote", "set-url", "origin", "https://github.com/Ed/Reco.git")
    _git(depot, "remote", "add", "pousser", str(depot.parent / "origine.git"))
    appels = []

    def poster(url, jeton, charge):
        appels.append((url, jeton, charge))
        return {"html_url": "https://github.com/Ed/Reco/pull/7"}

    resultat = _publier(depot, git=_git_qui_pousse_ailleurs(depot), jeton="jeton-test",
                        poster=poster)

    assert resultat.pr_ouverte and resultat.lien == "https://github.com/Ed/Reco/pull/7"
    url, jeton, charge = appels[0]
    assert url == "https://api.github.com/repos/Ed/Reco/pulls" and jeton == "jeton-test"
    assert charge["head"] == "contenu/yt-abc" and charge["base"] == "main"


def test_a_refused_api_call_falls_back_on_the_link(depot):
    _episode_complet(depot)
    _git(depot, "remote", "set-url", "origin", "git@github.com:Ed/Reco.git")
    _git(depot, "remote", "add", "pousser", str(depot.parent / "origine.git"))

    def poster(*_a, **_k):
        raise OSError("401")

    resultat = _publier(depot, git=_git_qui_pousse_ailleurs(depot), jeton="j", poster=poster)

    assert not resultat.pr_ouverte
    assert "compare/main...contenu/yt-abc" in resultat.lien
    assert resultat.avertissements and "PR non ouverte" in resultat.avertissements[0]
    # L'épisode est publié malgré tout : le nettoyage a bien eu lieu.
    assert not (depot / "src/content/recos" / SOURCE / "3001.json").exists()


@pytest.mark.parametrize(("url", "attendu"), [
    ("git@github.com:Ed/Reco.git", ("Ed", "Reco")),
    ("https://github.com/Ed/Reco.git", ("Ed", "Reco")),
    ("https://github.com/Ed/Reco", ("Ed", "Reco")),
    ("ssh://git@gitlab.com/Ed/Reco.git", ("", "")),
    ("https://github.com/Ed", ("", "")),
])
def test_the_owner_and_repo_are_read_from_the_remote(url, attendu):
    assert pub.depot_github(url) == attendu


def test_the_api_call_carries_the_token_and_posts_json(monkeypatch):
    """La vraie requête : méthode, en-têtes et corps, sans réseau."""
    vues = {}

    class FausseReponse:
        def read(self):
            return b'{"html_url": "https://github.com/Ed/Reco/pull/9"}'

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def faux_urlopen(requete, timeout=None):
        vues["url"] = requete.full_url
        vues["methode"] = requete.get_method()
        vues["entetes"] = {c.lower(): v for c, v in requete.header_items()}
        vues["corps"] = json.loads(requete.data.decode("utf-8"))
        vues["delai"] = timeout
        return FausseReponse()

    monkeypatch.setattr(pub.urllib.request, "urlopen", faux_urlopen)

    reponse = pub._poster_api("https://api.github.com/repos/Ed/Reco/pulls", "jeton",
                              {"title": "t", "head": "b", "base": "main"})

    assert reponse["html_url"].endswith("/pull/9")
    assert vues["methode"] == "POST" and vues["delai"] == pub.DELAI_API
    assert vues["entetes"]["authorization"] == "Bearer jeton"
    assert vues["entetes"]["accept"] == "application/vnd.github+json"
    assert vues["corps"]["base"] == "main"


# ===== les bords du périmètre ================================================
def test_an_episode_whose_recos_folder_is_missing_has_nothing_to_publish(depot, monkeypatch):
    import common

    monkeypatch.setattr(common, "RECOS_DIR", depot / "src/content/nulle-part")

    assert _publier(depot).refus == "aucune reco pour cet épisode"


def test_a_reco_without_mention_or_work_narrows_the_scope(depot):
    """Une reco pas encore convertie n'entraîne ni mention ni œuvre inexistantes."""
    _episode(depot)
    _reco(depot, "3001", "ubm-3001")          # ni mention ni œuvre
    _reco(depot, "3002", "ubm-3002")
    _mention(depot, "ubm-3002", "ccc333")      # mention sans fichier d'œuvre
    _reco(depot, "3003", "ubm-3003")
    _ecrire(depot / "src/content/mentions" / SOURCE / "ubm-3003.json",
            {"id": "ubm-3003"})                # mention sans `itemId`

    fichiers = pub.fichiers_episode(
        SOURCE, GUID, depot / "src/content/episodes" / SOURCE / f"{GUID.lower()}.json")

    noms = sorted(c.name for c in fichiers)
    assert noms == ["3001.json", "3002.json", "3003.json", "ubm-3002.json",
                    "ubm-3003.json", "yt-abc.json"]


def test_a_failed_cleanup_is_signalled_but_the_episode_stays_published(depot, monkeypatch):
    """Le contenu est sur GitHub : un nettoyage raté se signale, il n'annule rien."""
    _episode_complet(depot)
    monkeypatch.setattr(pub.Git, "revenir_sur_origin_main",
                        lambda *_a: (_ for _ in ()).throw(pub.ErreurGit("index verrouillé")))

    resultat = _publier(depot)

    assert not resultat.refuse and resultat.sha
    assert resultat.avertissements and "clone non nettoyé" in resultat.avertissements[0]
    # Les fichiers restent : le prochain passage le dira, rien n'est perdu.
    assert (depot / "src/content/recos" / SOURCE / "3001.json").exists()


# ===== le message et l'orchestration =========================================
def test_the_message_warns_that_the_episode_leaves_the_review_page():
    resultat = pub.Publication(GUID, branche="contenu/yt-abc", fichiers=4,
                               lien="https://exemple.test/pr/1", pr_ouverte=True)

    texte = pub.message("Titre", resultat)

    assert "PR ouverte" in texte and "https://exemple.test/pr/1" in texte
    assert "n'apparaît plus sur la page de validation" in texte


def test_the_message_says_when_the_cleanup_failed():
    resultat = pub.Publication(GUID, fichiers=1, avertissements=["clone non nettoyé (OSError)"])

    assert "⚠️ clone non nettoyé" in pub.message("Titre", resultat)


def test_a_failing_episode_does_not_block_the_next_one(depot, monkeypatch):
    _episode_complet(depot)
    inbox, erreurs = [], []
    episodes = [(Path("a.json"), {"guid": "yt-1", "title": "Un"}),
                (Path("b.json"), {"guid": "yt-2", "title": "Deux"})]

    def publier(source_id, guid, *_a, **_k):
        if guid == "yt-1":
            raise RuntimeError("clé ssh refusée")
        return pub.Publication(guid, fichiers=2, lien="https://exemple.test/c")

    monkeypatch.setattr(pub, "publier_episode", publier)
    state = {"published": []}
    code = pub.publier_les_episodes(
        SOURCE, episodes, inbox.append, state,
        rapporter=lambda _s, _c, message, _n: erreurs.append(message),
        oublier=lambda *_a: None)

    assert code == 0 and state["published"] == ["yt-2"]
    assert len(erreurs) == 1 and "clé ssh refusée" in erreurs[0]
    assert len(inbox) == 1 and "Deux" in inbox[0]


def test_a_refusal_is_reported_and_the_episode_stays_to_be_retried(depot, monkeypatch):
    inbox, erreurs = [], []
    monkeypatch.setattr(pub, "publier_episode",
                        lambda *_a, **_k: pub.Publication(GUID, refus="clone sali"))
    state = {"published": []}

    pub.publier_les_episodes(SOURCE, [(Path("a.json"), {"guid": GUID, "title": "Un"})],
                             inbox.append, state,
                             rapporter=lambda _s, _c, message, _n: erreurs.append(message),
                             oublier=lambda *_a: None)

    assert state["published"] == [] and inbox == []
    assert "clone sali" in erreurs[0]


def test_an_already_published_episode_is_marked_without_a_message(depot, monkeypatch):
    inbox = []
    monkeypatch.setattr(pub, "publier_episode",
                        lambda *_a, **_k: pub.Publication(GUID, deja_publie=True))
    state = {"published": []}

    pub.publier_les_episodes(SOURCE, [(Path("a.json"), {"guid": GUID, "title": "Un"})],
                             inbox.append, state,
                             rapporter=lambda *_a: None, oublier=lambda *_a: None)

    assert state["published"] == [GUID] and inbox == []


def test_the_token_comes_from_the_environment_by_default(depot, monkeypatch):
    monkeypatch.setenv("RECO_GITHUB_TOKEN", "jeton-env")
    vus = []
    monkeypatch.setattr(pub, "publier_episode",
                        lambda *_a, jeton="", **_k: vus.append(jeton) or pub.Publication(GUID))

    pub.publier_les_episodes(SOURCE, [(Path("a.json"), {"guid": GUID, "title": "Un"})],
                             lambda _m: None, {"published": []},
                             rapporter=lambda *_a: None, oublier=lambda *_a: None)

    assert vus == ["jeton-env"]


def test_a_git_failure_says_what_git_said(depot):
    git = pub.Git(depot)

    with pytest.raises(pub.ErreurGit, match="rev-parse"):
        git._git("rev-parse", "une-reference-qui-nexiste-pas")


def test_the_commit_message_stays_in_ascii(depot):
    _episode_complet(depot)

    resultat = pub.publier_episode(
        SOURCE, GUID, "Géraldine Nakache et Clémentine Célarié",
        depot / "src/content/episodes" / SOURCE / f"{GUID.lower()}.json", racine=depot)

    sujet = _git(depot, "show", "-s", "--pretty=format:%s", resultat.sha)
    assert sujet == "contenu: publier Geraldine Nakache et Clementine Celarie"
