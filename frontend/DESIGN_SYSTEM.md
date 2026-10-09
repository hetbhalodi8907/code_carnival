# Nexora frontend design system

**NEXORA · Secure Enterprise AI Knowledge Platform.** A minimal enterprise interface: white surfaces on a light grey page, thin borders, readable type and one restrained blue accent. The visual reference is [design_reference/open-design-prototype.html](design_reference/open-design-prototype.html); it is a static design reference only. The application never uses its fake accounts, simulated answers or mock sign-in.

## Principles

1. **Security is visible but never invented.** The UI shows what the server decided. It never computes access itself and never shows per-request "checks" the backend did not return.
2. **Answers first.** Text stays readable at a comfortable measure. Decoration never competes with content.
3. **One accent.** Blue marks interaction and selection. Green means an authenticated session, amber means a restricted or temporarily unavailable state, red means an error. These colours are used for nothing else.
4. **Flat and quiet.** No gradients, glow, blur or decorative shapes. Elevation comes from a hairline border and a very light shadow. The only moving element is the loading spinner, plus short colour transitions.

## Tokens

Defined as CSS variables in `src/index.css` and mapped to Tailwind colours. The app is light only.

| Token | Value | Use |
|---|---|---|
| `background` | `#F6F7F9` | page |
| `card` | `#FFFFFF` | surfaces, sidebar, top bar, answer cards |
| `surface-2` | `#FBFBFC` | hover and detail panels |
| `muted` | `#F1F3F5` | chips, icon tiles, hover fills |
| `foreground` / `muted-foreground` / `subtle` | `#1F2430` / `#5B6472` / `#8A929E` | primary, secondary, tertiary text |
| `border` / `border-strong` | `#E3E6EA` / `#D3D8DF` | hairlines / inputs and secondary buttons |
| `primary` / `primary-hover` / `primary-soft` | `#2563EB` / `#1D4FD8` / `#EAF0FE` | buttons, links, active navigation, user bubble |
| `success`, `warning`, `destructive` | `#2F855A`, `#B7791F`, `#C0392B` | each with a `-soft` fill and a `-strong` text colour for contrast on that fill |
| `ring` | `rgb(37 99 235 / 0.28)` | soft focus halo on inputs and the composer |

Keyboard focus is a 2 px blue outline with a 2 px offset (`:focus-visible`, set once in `index.css`).

## Typography, radius, elevation

- Family: **Inter Variable**, self-hosted through `@fontsource-variable/inter`, so it works offline. Monospace (system stack) is used for emails, page references and permission codes.
- Page title 16 px semibold (top bar); section and card titles 14.5–17 px semibold; body and answers 14–14.5 px; metadata 12–13 px; uppercase labels 11–12 px with 0.04–0.05 em tracking.
- Radius: `rounded-lg` 8 px for inputs, buttons and source cards; `rounded-xl` 12 px for cards and answers; pills are fully rounded.
- Shadows: `shadow-xs` on cards and buttons, `shadow-sm` on the login card and hovered demo cards, `shadow-md` only on floating menus and the mobile drawer.

## Components

| Component | Notes |
|---|---|
| `ui/button` | `default` (blue), `secondary` (white, strong border), `ghost`, `danger`, `link`; sizes `default` 40 px, `sm` 34 px, `icon` 36 px. |
| `ui/input`, `ui/textarea`, `ui/label` | 40 px inputs with a blue border and soft halo on focus; 13 px semibold labels; every field has a label. |
| `ui/badge` | Pills: `default` (blue), `muted`, `success`, `warning`, `destructive`. |
| `ui/alert` | Inline message with an icon; `role="alert"` for errors, `role="status"` for notices. |
| `ui/card`, `ui/avatar`, `ui/spinner` | Hairline card with header and content; initials avatar; loading spinner (always paired with text). |
| `feedback/StateBlock` | Titled status card used for "no authorized sources", "not enough information" and request errors. |
| `feedback/PageStatus` | Full-area loading message while a saved session is confirmed. |
| `layout/*` | `AppShell` (sidebar + top bar), `Sidebar` (a drawer below `md`), `SessionCard`, `TopBar`, `SessionPill`, `UserMenu`. |
| `auth/*` | `LoginForm` and `DemoAccounts`. |
| `chat/*` | `AssistantHeader`, `ChatEmptyState`, `Composer`, `UserMessage`, `AssistantMessage`, `AssistantStates`. |
| `citations/*` | `CitationList` and `SourceCard`: expandable cards for the sources the server retrieved. |

## Layout

- **Login:** two columns from `lg` (sign-in card 360–440 px, demo accounts to its right); a single column up to 720 px below that. The card comes first on small screens.
- **App shell:** a 248 px sidebar (brand, Assistant, Profile, then the signed-in identity and Log out) and a 60 px top bar (page title, secure-session pill, role chip, account menu). Below `md` (768 px) the sidebar becomes a drawer opened from the top bar: focus moves into it, Escape and the scrim close it and focus returns to the menu button.
- **Assistant:** a header, a scrolling conversation (max 860 px wide) and a composer pinned to the bottom.
- **Profile:** identity card, session and authentication, access permissions, and a Log out card.

## Assistant states

| State | Treatment |
|---|---|
| Empty | Icon, "Ask across your company knowledge" and four sample questions. Selecting one only fills the composer. |
| User message | Right-aligned blue bubble. |
| Loading | A card with a spinner and "Retrieving authorized sources…". There are no progress steps because the server answers in one request. |
| Answer | Card headed "NEXORA Assistant" with the answer text, "N authorized sources retrieved" and expandable source cards (title, page, similarity). The model's `[S<n>]` references are listed beneath as unverified. |
| No authorized sources | The server's fixed message; no document names, counts or policy internals. |
| Not enough information | The server's fixed message and a rephrasing hint. |
| Error | Calm fixed copy by status, never raw server text. Temporary failures (network, 500, 502, 503, 504) offer **Retry**; 403, 404 and 422 do not. |

## Sources

A source card shows the document title the server returned and the page, if any. Expanding it shows the page and the cosine similarity as a two-decimal score (a similarity, not a confidence percentage). File paths, database IDs, passage text the server did not send and access-control internals are never shown. These are sources the server retrieved, not verified citations.
