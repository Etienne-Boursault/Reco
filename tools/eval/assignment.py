"""Assignment optimal (algorithme Hungarian) — pur Python.

``scipy.optimize.linear_sum_assignment`` n'est pas une dépendance du
projet (cf. ADR 0011). On implémente donc un Hungarian minimal en O(n³)
pour le pairing expected ↔ extracted, en cherchant à *maximiser* la
somme des scores.

L'API mime ``scipy`` : ``linear_sum_assignment(cost, maximize=False)``
renvoie ``(row_ind, col_ind)`` indexant la matrice fournie.

Cas dégénérés :
- matrice vide → tuple vide.
- matrice non rectangulaire → ``ValueError``.
- ligne plus longue que colonne (ou inverse) → on pad avec un coût
  neutre (0 pour minimisation, max pour maximisation).
"""
from __future__ import annotations

from typing import Sequence

__all__ = ["linear_sum_assignment"]


def _pad_to_square(
    cost: list[list[float]], pad_value: float,
) -> tuple[list[list[float]], int, int]:
    """Pad la matrice en carrée. Retourne (matrice carrée, n_rows, n_cols)."""
    n_rows = len(cost)
    n_cols = len(cost[0]) if cost else 0
    n = max(n_rows, n_cols)
    padded = [row[:] + [pad_value] * (n - len(row)) for row in cost]
    while len(padded) < n:
        padded.append([pad_value] * n)
    return padded, n_rows, n_cols


def linear_sum_assignment(
    cost_matrix: Sequence[Sequence[float]],
    *,
    maximize: bool = False,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Résout l'assignment problem (Hungarian).

    Args:
        cost_matrix: matrice rectangulaire de coûts (floats).
        maximize: si True, maximise au lieu de minimiser.

    Returns:
        ``(row_ind, col_ind)`` — index lignes/colonnes appariées,
        triées par ``row_ind``.
    """
    if not cost_matrix or not cost_matrix[0]:
        return ((), ())

    # Vérifie rectangularité.
    width = len(cost_matrix[0])
    for row in cost_matrix:
        if len(row) != width:
            raise ValueError("cost_matrix doit être rectangulaire.")

    # Convertit en min-problem si maximize.
    if maximize:
        max_v = max(max(r) for r in cost_matrix)
        cost = [[max_v - v for v in row] for row in cost_matrix]
        pad = max_v  # padding = coût maximal (= 0 reward après inversion)
    else:
        cost = [list(row) for row in cost_matrix]
        pad = 0.0

    square, n_rows, n_cols = _pad_to_square(cost, pad_value=pad)
    n = len(square)

    # Hungarian (Kuhn-Munkres) — implémentation en O(n³), inspirée de
    # https://e-maxx.ru/algo/assignment_hungary (algorithme dual).
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)       # p[j] = ligne assignée à la colonne j
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = square[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0 != 0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    # Reconstitue l'assignment ligne→colonne.
    assignment: list[tuple[int, int]] = []
    for j in range(1, n + 1):
        i = p[j] - 1
        col = j - 1
        if i < n_rows and col < n_cols:
            assignment.append((i, col))

    assignment.sort()
    row_ind = tuple(a[0] for a in assignment)
    col_ind = tuple(a[1] for a in assignment)
    return row_ind, col_ind
