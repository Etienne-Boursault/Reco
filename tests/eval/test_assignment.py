"""Tests de l'assignment optimal (Hungarian pur Python)."""
from __future__ import annotations

import pytest

from tools.eval.assignment import linear_sum_assignment


class TestLinearSumAssignment:
    def test_empty(self) -> None:
        rows, cols = linear_sum_assignment([])
        assert rows == ()
        assert cols == ()

    def test_single_cell(self) -> None:
        rows, cols = linear_sum_assignment([[0.5]])
        assert rows == (0,)
        assert cols == (0,)

    def test_square_minimize(self) -> None:
        # Identité optimale.
        rows, cols = linear_sum_assignment([[1, 9], [9, 1]])
        assert list(zip(rows, cols)) == [(0, 0), (1, 1)]

    def test_square_maximize(self) -> None:
        rows, cols = linear_sum_assignment(
            [[0.9, 0.1], [0.1, 0.9]], maximize=True,
        )
        assert list(zip(rows, cols)) == [(0, 0), (1, 1)]

    def test_rectangular_more_cols(self) -> None:
        # 2 lignes × 3 colonnes, maximisation.
        cost = [[0.1, 0.9, 0.4], [0.8, 0.2, 0.3]]
        rows, cols = linear_sum_assignment(cost, maximize=True)
        # Optimal : ligne0→col1 (0.9), ligne1→col0 (0.8). Total = 1.7
        assert dict(zip(rows, cols)) == {0: 1, 1: 0}

    def test_rectangular_more_rows(self) -> None:
        cost = [[0.9, 0.1], [0.8, 0.2], [0.1, 0.7]]
        rows, cols = linear_sum_assignment(cost, maximize=True)
        # 2 paires max ; choisir ligne0→col0 (0.9) + ligne2→col1 (0.7) = 1.6
        assigned = dict(zip(rows, cols))
        assert assigned[0] == 0
        assert assigned[2] == 1
        assert 1 not in assigned

    def test_not_rectangular_raises(self) -> None:
        with pytest.raises(ValueError):
            linear_sum_assignment([[1, 2], [3]])

    def test_beats_greedy(self) -> None:
        # Cas où greedy choisit mal : score diagonal optimal.
        # Greedy choisirait (0,1)=0.95, puis (1,0)=0.1 → 1.05.
        # Optimal : (0,0)=0.9 + (1,1)=0.9 → 1.8.
        cost = [[0.9, 0.95], [0.1, 0.9]]
        rows, cols = linear_sum_assignment(cost, maximize=True)
        total = sum(cost[r][c] for r, c in zip(rows, cols))
        assert total == pytest.approx(1.8)
