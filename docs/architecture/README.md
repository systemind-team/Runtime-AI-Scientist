# Interactive architecture map

`index.html` is a standalone, English-language architecture viewer. Download it
and open it in a browser, or serve this directory with a static HTTP server.
GitHub's file viewer does not execute the HTML. This change does not deploy a
website or change GitHub Pages settings.

The README image and `../assets/runtime-architecture.svg` are native exports of
the same diagram. The viewer supports node focus, source references, relationship
exploration, keyboard controls and static export. Optional Effects are finite
relationship cues, not evidence of live execution; reduced-motion preferences
disable them.

## Provenance and maintenance

- The map describes repository revision `bf11766341e2fbf60612bf486f577d6db33ea259`.
  Source links intentionally remain pinned to that reviewed revision.
- `architecture.json` preserves the 16 authored components, 18 directed
  relationships and source references. It does not change runtime configuration.
- The viewer is adapted from [Archify](https://github.com/tt-a1i/archify) 3.0.1,
  with RAC-specific inline SVG icons, brand styling, caption callouts, focus
  framing and finite interaction cues. The generated HTML includes these
  customizations; stock Archify plus the JSON alone will not reproduce every
  visual or interaction detail.
- For edits, keep the HTML, specification and both static exports synchronized.
  Use the viewer's Export menu for PNG and SVG so transient focus/animation
  overlays do not enter the static preview. Inspect labels and links at the
  README's actual display width before committing.
- Preserve [Archify's MIT notice](ARCHIFY-LICENSE.txt) and the embedded
  [JetBrains Mono font's OFL notice](FONT-LICENSE.txt). Main diagram labels use
  the system font stack; the viewer also contains the bundled font.

## Known limitation

Manual zoom in a short viewport can clip a right-side title. Reset or return to
automatic node focus to recover the view. This documentation addition does not
claim a complete mobile/accessibility audit or change the experiment runtime.
