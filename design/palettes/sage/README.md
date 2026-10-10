# Sage palette (Net Gain Edtech, original scheme)

The dark green scheme Net Gain Edtech used from launch until **2026-10-09**, when the Edtech section was recolored to
Denim (Claude Design handoff "denim recolor"). Archived here so it can be revived for another show.

Files in this folder:

| File | What it is |
|---|---|
| `sage-tokens.css` | The palette as CSS custom properties plus the body-scope block - the part you re-use |
| `style.css.pre-denim-2026-10-09` | The theme's complete `style.css` exactly as it was in production just before the recolor (Net Gain News child theme 0.5.3) |

## Palette

| Role | Hex |
|---|---|
| Page background | `#1e2620` |
| Section / header / footer / network-strip background | `#1a221d` |
| Deepest band (in the design handoff, unused in the theme) | `#131a15` |
| Primary text (ink) | `#f5f6f2` |
| Light accent (links, "Edtech", labels, nav active) | `#85a870` |
| Accent (primary buttons, rules) | `#3d6b4a` |
| Muted text | `#8a9e8c` (handoff also lists `#5c7060`) |
| Borders / rules | `#2e3a2e` (strong border `#3a4a3a`, frame border `#0e1410`) |
| Thumbnail placeholder | `#253228` |
| "Latest" tag red | `#d42b2b` (white text) |
| Index up / down | `#85a870` / `#e87c50` |
| Hero glow | radial gradient from `#3d6b4a` at opacity 0.45 (in `page-edtech.php`) |
| Accent hover tints | `rgba(61,107,74,a)` |
| Duration chip on thumbnails | `rgba(26,34,29,0.9)` |

Header: dark green bar (`#1a221d`), light logo; logo mark and "Edtech" in the light accent `#85a870`, "Net Gain" in `#f5f6f2`;
the primary button ("Follow Show") is the green accent with light text.

## Episode graphics duotone (AI-generated art, before code-built cards)

Shadow `#1e2620` (the palette's ink-dark), highlight `#6a9470`. The code-built cards (`pipeline/cards.py`) were designed in
this palette's greens: tiles `#2e4437`, ground `#222f27`, brand dark green `#3d6b4a`, brand light green `#85a870`.

## How the theme applies a palette

The Net Gain News child theme keeps each section's colours in variables (`--<name>-bg/-hbg/-fg/-ac/-acl/-mu/-bd/-th`), selects
them with a body class (`body.ng-show-<slug>`, set by `ng_body_class()` in `functions.php`), and writes every component in
terms of the semantic tokens - so a new show with this palette needs only: a `--<name>-*` block (or reuse `--sage-*`),
a `body.ng-show-<slug>` scope like the one in `sage-tokens.css`, and the show's own logo assets. The theme itself is
deployed outside git (`~/netgain.news/wp-content/themes/net-gain-news/`); `functions.php` is deliberately NOT archived here
because it contains the contact-form destination addresses and this repository is public.

A full backup of the pre-denim theme directory also exists on the production server:
`~/net-gain-news-theme-pre-denim-20261009.tgz`.
