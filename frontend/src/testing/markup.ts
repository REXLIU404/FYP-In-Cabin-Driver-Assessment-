// Test-only helpers for STATIC RENDERING React components in the node vitest
// environment (no DOM, no new dependency): `react-dom/server` is already installed
// and `renderToStaticMarkup` needs nothing but a React element. Nothing in the app
// imports this file.
//
// The extractors tie a value to the row LABEL it sits under (`<span>label</span>`
// followed by the value), so a test can tell "the vision row says expired" from
// "some pill on the page says expired" - a swapped or dropped prop on one branch
// changes exactly one of these results.
import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** Markup of `element`, without React's `<!-- -->` text-node separators. */
export const markup = (element: ReactElement): string =>
  renderToStaticMarkup(element).replace(/<!-- -->/g, "");

const escapeRegExp = (text: string) =>
  text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Every pill that directly follows `<span>{label}</span>`, in document order, as
 * `"<tone>:<text>"` - e.g. `"expired:expired (4 s)"`, `"missing:missing"`.
 */
export const pillsAfter = (html: string, label: string): string[] =>
  [
    ...html.matchAll(
      new RegExp(
        `<span>${escapeRegExp(label)}</span><span class="pill pill--([^"]*)">([^<]*)</span>`,
        "g",
      ),
    ),
  ].map((match) => `${match[1]}:${match[2]}`);

/**
 * The text of every `<strong>` that directly follows `<span>{label}</span>`, in
 * document order (up to any nested tag, so `<strong>0.30<small>30%</small></strong>`
 * yields `"0.30"`).
 */
export const valuesAfter = (html: string, label: string): string[] =>
  [
    ...html.matchAll(
      new RegExp(`<span>${escapeRegExp(label)}</span><strong>([^<]*)`, "g"),
    ),
  ].map((match) => match[1]);

/**
 * One Live Monitor `ModalityCard`, as `"<big number> | <tone>:<pill text> | <small
 * text>"` - e.g. `"— | expired:expired (4 s) | Expired"`. `null` if the page has no
 * card with that title.
 */
export const modalityCard = (html: string, title: string): string | null => {
  const match = new RegExp(
    `<div class="modality-card"><span>${escapeRegExp(title)}</span><strong>([^<]*)</strong><div><span class="pill pill--([^"]*)">([^<]*)</span><small>([^<]*)</small></div></div>`,
  ).exec(html);
  return match ? `${match[1]} | ${match[2]}:${match[3]} | ${match[4]}` : null;
};

/**
 * Every element in the tree of `node`, depth first, that satisfies `match`. The tree
 * is the one a function component RETURNS (call the component directly - it must use
 * no hooks): host elements such as `button` are found with their props, which is how
 * a test "clicks" without a DOM - `find(...)[0].props.onClick()`. Component elements
 * inside it are visited but not expanded.
 */
export const findElements = (
  node: ReactNode,
  match: (element: ReactElement) => boolean,
): ReactElement[] => {
  const found: ReactElement[] = [];
  const visit = (child: ReactNode) => {
    if (!isValidElement(child)) return;
    if (match(child)) found.push(child);
    Children.forEach((child.props as { children?: ReactNode }).children, visit);
  };
  visit(node);
  return found;
};
