/**
 * tests/tracking/test_metrics.test.ts — Compteurs in-memory par status
 * (R-P3-22).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  recordClickStatus,
  getClickMetrics,
  resetClickMetrics,
} from '../../src/lib/tracking/metrics.ts';

beforeEach(() => {
  resetClickMetrics();
});

describe('metrics', () => {
  it('compteurs partent à zéro après reset', () => {
    expect(getClickMetrics()).toEqual({ total: 0, byStatus: {} });
  });

  it('incrémente par status', () => {
    recordClickStatus(204);
    recordClickStatus(204);
    recordClickStatus(403);
    const m = getClickMetrics();
    expect(m.total).toBe(3);
    expect(m.byStatus['204']).toBe(2);
    expect(m.byStatus['403']).toBe(1);
  });

  it('ignore les non-entiers', () => {
    recordClickStatus(Number.NaN);
    recordClickStatus(1.5);
    expect(getClickMetrics().total).toBe(0);
  });

  it('B-MED-21 ignore les status hors plage 100-599', () => {
    recordClickStatus(99);
    recordClickStatus(600);
    recordClickStatus(-1);
    recordClickStatus(99_999);
    expect(getClickMetrics().total).toBe(0);
    // Edge inclusifs : 100 et 599 acceptés.
    recordClickStatus(100);
    recordClickStatus(599);
    expect(getClickMetrics().total).toBe(2);
  });
});
