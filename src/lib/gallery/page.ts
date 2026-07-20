/**
 * src/lib/gallery/page.ts — helpers de page (JSON-LD, SEO).
 */
import { recoToSchema } from '../seo/jsonld';
import type { GalleryEntry } from './aggregate';

/**
 * Construit un `ItemList` schema.org listant les œuvres d'une galerie.
 * `url` peut être fourni (lien vers la fiche œuvre quand disponible).
 * On limite à `maxItems` pour éviter des payloads JSON-LD énormes.
 */
export function galleryItemListSchema(
  entries: readonly GalleryEntry[],
  options: {
    name: string;
    description?: string;
    maxItems?: number;
    urlBuilder?: (entry: GalleryEntry) => string | undefined;
  },
): Record<string, unknown> {
  const { name, description, maxItems = 100, urlBuilder } = options;
  const slice = entries.slice(0, maxItems);
  const itemListElement = slice.map((entry, idx) => {
    const itemSchema = recoToSchema({
      type: entry.types[0] ?? 'autre',
      title: entry.title,
      author: entry.creator ?? undefined,
      url: urlBuilder?.(entry),
    });
    // schema.org ItemList n'attend pas `@context` sur les enfants.
    delete (itemSchema as Record<string, unknown>)['@context'];
    return {
      '@type': 'ListItem',
      position: idx + 1,
      item: itemSchema,
    };
  });
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name,
    numberOfItems: entries.length,
    itemListElement,
  };
  if (description) node.description = description;
  return node;
}

/** Construit un BreadcrumbList à 3 niveaux : Accueil → Source → Galerie. */
export function galleryBreadcrumb(args: {
  homeUrl: string;
  sourceName: string;
  sourceUrl: string;
  galleryName: string;
  galleryUrl: string;
}): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Accueil', item: args.homeUrl },
      { '@type': 'ListItem', position: 2, name: args.sourceName, item: args.sourceUrl },
      { '@type': 'ListItem', position: 3, name: args.galleryName, item: args.galleryUrl },
    ],
  };
}
