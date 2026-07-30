// @vitest-environment happy-dom
/**
 * `withJsApi` — construction de l'URL du lecteur YouTube.
 *
 * BUG CONSTATÉ EN NAVIGATEUR sur `/doutes` (2026-07-29) : la console se
 * remplissait de
 *
 *     DOMException: An invalid or illegal string was specified
 *       sendMessage  www-widgetapi.js:163
 *
 * répété à chaque interaction. Cause : le client ajoutait `enablejsapi=1` à
 * l'URL de l'iframe SANS ajouter `origin`. L'IFrame Player API émet alors ses
 * `postMessage` vers une cible qu'elle ne sait pas déterminer, et le
 * navigateur rejette la chaîne. Le lecteur reste pilotable par le clavier
 * (l'API retombe sur un `postMessage('*')`), mais chaque commande jette une
 * exception dans la console — jusqu'à noyer les vraies erreurs.
 *
 * YouTube exige que `origin` soit l'origine EXACTE de la page hôte. Le serveur
 * de relecture ne la connaît pas au rendu (elle dépend du host et du port
 * d'accès), d'où le calcul côté client.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';

const TOOLS = path.resolve(__dirname, '../../tools');

function loadScript(name: string): void {
  const code = readFileSync(path.join(TOOLS, name), 'utf-8');
  // eslint-disable-next-line no-new-func -- évaluation volontaire de l'IIFE
  new Function(code)();
}

let withJsApi: (src: string, origin: string) => string;

beforeAll(() => {
  (window as never as Record<string, unknown>).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_cluster.js');
  loadScript('review_client_keyboard.js');
  withJsApi = (
    (window as never as Record<string, Record<string, unknown>>).__recoTestHooks
      .withJsApi
  ) as typeof withJsApi;
});

const ORIGIN = 'http://127.0.0.1:8001';
const EMBED = 'https://www.youtube.com/embed/abc123?start=42';

describe('withJsApi — le paramètre origin, celui qui manquait', () => {
  it('ajoute enablejsapi ET origin', () => {
    const out = new URL(withJsApi(EMBED, ORIGIN));
    expect(out.searchParams.get('enablejsapi')).toBe('1');
    expect(out.searchParams.get('origin')).toBe(ORIGIN);
  });

  it('préserve les paramètres existants — le timecode ne doit pas sauter', () => {
    const out = new URL(withJsApi(EMBED, ORIGIN));
    expect(out.searchParams.get('start')).toBe('42');
    expect(out.pathname).toBe('/embed/abc123');
  });

  it('n’ajoute pas `origin` deux fois si l’URL en a déjà un', () => {
    const deja = `${EMBED}&enablejsapi=1&origin=${encodeURIComponent(ORIGIN)}`;
    const out = withJsApi(deja, ORIGIN);
    expect(out.match(/origin=/g)).toHaveLength(1);
    expect(out.match(/enablejsapi=/g)).toHaveLength(1);
  });

  it('complète une URL qui a déjà enablejsapi mais pas origin', () => {
    // C'est l'état exact que produisait l'ancien code, et la cause du bug.
    const out = new URL(withJsApi(`${EMBED}&enablejsapi=1`, ORIGIN));
    expect(out.searchParams.get('origin')).toBe(ORIGIN);
  });

  it('encode l’origine (le port doit survivre au passage en query)', () => {
    expect(withJsApi(EMBED, ORIGIN)).toContain(encodeURIComponent(ORIGIN));
  });
});

describe('withJsApi — cas où il ne faut RIEN faire', () => {
  it.each(['', 'about:blank'])('laisse %o intact', (src) => {
    expect(withJsApi(src, ORIGIN)).toBe(src);
  });

  it('laisse l’URL intacte si l’origine est inexploitable', () => {
    // `location.origin` vaut `'null'` (la chaîne) sur une page opaque. Ajouter
    // `origin=null` serait pire que ne rien ajouter : YouTube rejetterait la
    // valeur au lieu de retomber sur son comportement par défaut.
    for (const mauvaise of ['', 'null', 'undefined']) {
      expect(withJsApi(EMBED, mauvaise)).toBe(EMBED);
    }
  });

  it('est idempotent — deux applications ne changent rien de plus', () => {
    const une = withJsApi(EMBED, ORIGIN);
    expect(withJsApi(une, ORIGIN)).toBe(une);
  });
});
