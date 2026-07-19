"""Helpers de test pour parser le HTML rendu par review_server.

Utilise BeautifulSoup (parser stdlib 'html.parser') pour des assertions
structurelles robustes aux changements de markup : espaces, ordre d'attributs,
indentation des f-strings, ajout de data-attributes.

Convention : tout NOUVEAU test qui vérifie du HTML rendu DOIT utiliser ces
helpers plutôt que des `assert 'foo' in html`.
"""
from bs4 import BeautifulSoup, Tag


def parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def find_input(soup, name, value=None, *, type=None):
    attrs = {"name": name}
    if value is not None:
        attrs["value"] = value
    if type is not None:
        attrs["type"] = type
    return soup.find("input", attrs)


def find_radio(soup, name, value):
    return find_input(soup, name, value, type="radio")


def find_checkbox(soup, name, value):
    return find_input(soup, name, value, type="checkbox")


def is_checked(tag):
    return tag is not None and tag.has_attr("checked")


def has_class(tag, *classes):
    if tag is None:
        return False
    tag_classes = tag.get("class", [])
    return all(c in tag_classes for c in classes)


def find_rows(soup, *, cls=None):
    rows = soup.find_all("li", class_="row")
    if cls is None:
        return rows
    return [r for r in rows if cls in r.get("class", [])]


def find_form(soup, action):
    return soup.find("form", action=action)


def find_link(soup, *, href_contains=None, target=None):
    for a in soup.find_all("a"):
        if href_contains and href_contains not in (a.get("href") or ""):
            continue
        if target and a.get("target") != target:
            continue
        return a
    return None


def text_of(tag):
    return tag.get_text(" ", strip=True) if tag is not None else ""
