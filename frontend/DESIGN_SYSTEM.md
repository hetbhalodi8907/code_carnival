# Nexora frontend design system

**NEXORA · Secure AI Workspace.** A calm, dark-first enterprise interface. It should read as *secure, private, intelligent*: quiet surfaces, one confident accent, and status colours used only where they carry meaning.

## Principles

1. **Security is visible but never invented.** The UI shows what the server decided. It never computes access itself and never shows per-request "checks" the backend did not return.
2. **Answers first.** Text is readable at a comfortable measure (`max-w-3xl`). Decoration never competes with content.
3. **One accent.** Signal blue marks interaction. Emerald means *secure mode*, amber means *restricted*, red means *error*. These colours are not used for anything else.
4. **Subtle motion.** 150–250 ms fades and lifts. Everything respects `prefers-reduced-motion`.

## Colour tokens

Defined as CSS variables in `src/index.css` (OKLCH). Dark is the default; light is opt-in via the theme toggle.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--background` | deep graphite-navy | near-white | page |
| `--card` | +1 step | white | surfaces, message cards |
| `--muted` / `--muted-foreground` | low-contrast fill / secondary text | | metadata, hints |
| `--border` | white at 9 % | slate at 12 % | hairlines |
| `--primary` | signal blue (L 0.72) on dark text | deeper blue (L 0.52) on white | buttons, focus ring, user bubble tint |
| `--success` | emerald | emerald | secure-mode dot and badge |
| `--warning` | amber | amber | access-restricted state |
| `--destructive` | red | red | errors |

Contrast targets: body text ≥ 7:1, secondary text ≥ 4.5:1, focus ring ≥ 3:1 against both surfaces.

## Typography

- Family: **Inter Variable** (self-hosted via `@fontsource-variable/inter`, so it works offline), falling back to the system UI stack.
- Display: 28–32 px / semibold / tight tracking (`text-3xl font-semibold tracking-tight`).
- Page title: 20 px semibold. Card title: 15 px semibold.
- Body: 15 px / 1.65 for chat answers, 14 px for UI.
- Eyebrow labels: 11 px, uppercase, `tracking-[0.14em]`, muted.
- Numbers in citations (page, similarity): `tabular-nums`.

## Spacing, radius, elevation

- 4 px grid. Page gutters are 16 px on mobile, 24 px on tablet and 32 px on desktop.
- Radius: `--radius: 0.75rem`. Cards use `rounded-xl`, inputs and buttons `rounded-lg`, chips `rounded-full`.
- Elevation: borders do most of the work. Cards get `shadow-sm`; the login card and composer get a soft, wide shadow. A faint primary-tinted radial glow appears only on the login backdrop and the empty chat state.

## Components

| Component | Spec |
|---|---|
| **Button** | `default` (primary fill), `secondary`, `outline`, `ghost`, `link`; sizes `sm`, `default`, `lg`, `icon`. Visible 2 px focus ring. Loading shows a spinner and keeps the label. |
| **Input / Textarea** | 40 px tall, `bg-background/60`, hairline border, primary focus ring. Each has a `<Label>`. |
| **Badge** | `outline` (role), `success` (secure mode), `warning` (restricted), `muted`. |
| **Card** | Hairline border, `bg-card`, `rounded-xl`. |
| **Tooltip** | Radix, 200 ms delay, small dark surface. Used for the secure-mode explanation. |

## Layout

- **Login:** two columns on `lg+` (product statement on the left, sign-in card on the right); a single centred card below that.
- **App shell:** top bar (64 px) with brand, secure-mode pill, user badge, theme toggle and logout. A 240 px side navigation (*AI Assistant*, *Profile*) on `md+`. Below `md`, navigation becomes icon buttons in the top bar.
- **Chat:** header (title + subtitle), a scrollable conversation (`max-w-3xl`), and a composer pinned to the bottom with quick-prompt chips above it.

## Chat states

| State | Treatment |
|---|---|
| Empty | Brand mark, "Secure AI Workspace", invitation line, 4 example cards (clicking fills the input; nothing is sent). |
| User message | Right-aligned, primary-tinted bubble. |
| Loading | Assistant card with three pulsing dots: "Retrieving authorized sources…". No fake percentages or steps. |
| Answer | Assistant card titled "Nexora AI". Readable text, then a hairline and a **Sources** row of citation chips. |
| Authorized passages | Shown when the backend has retrieval but no answer generation yet. The card explains this and lists the passages as expandable source cards. |
| Access restricted | Amber shield icon, "Access restricted", one neutral sentence. **No document names, departments or counts.** A static, muted "secure retrieval policy" note describes the product rule, not per-request results. |
| Error | Red-tinted card with a friendly message by status (session expired, unavailable, invalid request, unexpected). Raw server payloads are never shown. |

## Citations

A chip shows `Document title · p. N` (or `Authorized source · p. N` when the backend does not return a title). Clicking a chip expands its source card: excerpt, page and similarity as a percentage with `tabular-nums`. File paths, database IDs and access-control internals are never shown.
