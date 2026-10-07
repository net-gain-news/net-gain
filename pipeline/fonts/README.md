# Fonts used by the episode card renderer (`pipeline/cards.py`)

All three families are open fonts licensed under the SIL Open Font License 1.1.
The licence texts sit next to the font files and must stay with them (the OFL
requires that the licence and copyright notice accompany any redistribution).
They are used here only to draw text into images the show publishes - the font
files themselves are shipped inside this repository, unmodified.

| Files | Family | Licence text | Used for |
|---|---|---|---|
| `Archivo[wdth,wght].ttf` | Archivo (variable: weight 100-900, width 62-125) | `OFL-archivo.txt` | headlines, big numerals, display words (Bold 700; width axis 78 for the condensed display words) |
| `IBMPlexSans[wdth,wght].ttf` | IBM Plex Sans (variable) | `OFL-ibmplexsans.txt` | supporting text ("today", index sub-heads, key caption) |
| `IBMPlexMono-Regular.ttf`, `IBMPlexMono-Medium.ttf` | IBM Plex Mono | `OFL-ibmplexmono.txt` | small labels, tickers, numbering |

The site's logo wordmark is Familjen Grotesk, but the cards never draw it as
text: the logo is part of each show's uploaded frame template (PNG).
