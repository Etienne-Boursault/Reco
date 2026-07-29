/**
 * `resolveClientIp` — quelle IP sert de clé de rate-limit.
 *
 * LE PIÈGE, corrigé ici (revue de sécurité du 2026-07-29).
 *
 * `X-Forwarded-For` s'écrit `<client>, <proxy1>, <proxy2>` : un proxy AJOUTE
 * l'adresse qu'il voit, il n'écrase pas ce que le client a envoyé. Donc :
 *
 *   - le PREMIER élément est la valeur fournie par le CLIENT → forgeable ;
 *   - le DERNIER est celle posée par NOTRE propre proxy → digne de foi.
 *
 * Les deux endpoints lisaient `xff.split(',')[0]`. Un attaquant faisait donc
 * varier l'en-tête à chaque requête (`1.2.3.4`, `1.2.3.5`, …), tombait dans un
 * bucket neuf à chaque fois, et le rate-limit ne se déclenchait jamais. Chaque
 * requête acceptée écrit un fichier sur le disque du serveur.
 *
 * Prendre le DERNIER élément est également correct quand le proxy REMPLACE
 * l'en-tête au lieu de l'étendre (nginx `$remote_addr`) : la liste ne contient
 * alors qu'une entrée, premier et dernier se confondent.
 *
 * Cette logique vivait en DOUBLE, recopiée dans les deux endpoints — c'est le
 * motif qui a déjà produit deux bugs dans ce dépôt (une parade appliquée à un
 * module et jamais reportée sur son jumeau). Elle vit désormais ici.
 */
import { describe, it, expect } from 'vitest';
import { resolveClientIp } from '../../src/lib/http/resolveClientIp';

const TRUSTED = new Set(['10.0.0.1']);

const resoudre = (clientAddress: string | null, forwardedFor: string | null = null) =>
  resolveClientIp({ clientAddress, forwardedFor, trustedProxies: TRUSTED });

describe('resolveClientIp — sans proxy de confiance', () => {
  it('renvoie le pair direct et IGNORE l’en-tête forgé', () => {
    expect(resoudre('203.0.113.9', '1.2.3.4')).toBe('203.0.113.9');
  });

  it('renvoie le pair direct quand aucun en-tête n’est présent', () => {
    expect(resoudre('203.0.113.9')).toBe('203.0.113.9');
  });
});

describe('resolveClientIp — derrière un proxy de confiance', () => {
  it('prend le DERNIER élément, celui posé par notre proxy', () => {
    // `1.2.3.4` est ce que l'attaquant a envoyé ; `203.0.113.9` est ce que
    // notre proxy a constaté. C'est la seconde valeur qui fait foi.
    expect(resoudre('10.0.0.1', '1.2.3.4, 203.0.113.9')).toBe('203.0.113.9');
  });

  it('résiste à une chaîne forgée de plusieurs entrées', () => {
    expect(resoudre('10.0.0.1', '1.1.1.1, 2.2.2.2, 3.3.3.3, 203.0.113.9'))
      .toBe('203.0.113.9');
  });

  it('fonctionne aussi quand le proxy REMPLACE l’en-tête (une seule entrée)', () => {
    expect(resoudre('10.0.0.1', '203.0.113.9')).toBe('203.0.113.9');
  });

  it('tolère les espaces et les entrées vides', () => {
    expect(resoudre('10.0.0.1', ' 1.2.3.4 ,  , 203.0.113.9 ,, ')).toBe('203.0.113.9');
  });

  it('retombe sur le proxy quand l’en-tête est absent ou vide', () => {
    // M25-18 : le proxy est de confiance, son adresse reste exploitable
    // (health-check interne, tests) — mieux qu'un `null` qui ferait tomber
    // tous les clients dans le même bucket.
    expect(resoudre('10.0.0.1')).toBe('10.0.0.1');
    expect(resoudre('10.0.0.1', '')).toBe('10.0.0.1');
    expect(resoudre('10.0.0.1', '   ,  ')).toBe('10.0.0.1');
  });
});

describe('resolveClientIp — adresse indisponible', () => {
  it('renvoie null quand il n’y a pas de pair direct', () => {
    expect(resoudre(null)).toBeNull();
    expect(resoudre(null, '1.2.3.4')).toBeNull();
  });

  it('traite la CHAÎNE VIDE comme une absence, pas comme une adresse', () => {
    // `tryClientAddress` préserve `''` volontairement et laisse l'appelant
    // décider. Ici la décision est prise : une chaîne vide hashée mettrait
    // tous les clients concernés dans un bucket unique — exactement le
    // DoS auto-infligé que le court-circuit cherche à éviter.
    expect(resoudre('')).toBeNull();
    expect(resoudre('', '1.2.3.4')).toBeNull();
  });
});

describe('resolveClientIp — l’en-tête seul ne suffit jamais', () => {
  it('un attaquant sans proxy de confiance ne choisit pas sa clé', () => {
    const cles = new Set(
      ['1.2.3.4', '1.2.3.5', '1.2.3.6', '1.2.3.7'].map(
        (forge) => resoudre('198.51.100.7', forge),
      ),
    );
    // Quelles que soient ses tentatives, la clé de rate-limit ne bouge pas.
    expect(cles).toEqual(new Set(['198.51.100.7']));
  });
});
