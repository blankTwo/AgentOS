# Tailwind Conventions

## Goal
Keep Tailwind usage stable, readable, reusable, and consistent with existing project pages.

## Rules
- Prefer standard Tailwind tokens.
- Avoid arbitrary values unless necessary.
- Reuse existing patterns for type, spacing, radius, width, and height.
- Keep class structure consistent for similar components.
- Extract shared classes or components when repetition becomes meaningful.

## Prefer
- `text-xs` over `text-[12px]`
- `rounded-md` over `rounded-[6px]`
- `px-3 py-2` over fragmented arbitrary values
- `gap-2`, `gap-3`, `gap-4` over `gap-[10px]`

## Avoid
- one-off colors
- one-off shadows
- one-off radius values
- magic spacing
- large arbitrary viewport assumptions

## Exception
Arbitrary values are allowed only when:
1. the design source has a hard constraint
2. component-library overrides are difficult
3. the project already commonly uses the value
4. no equivalent token exists

When using arbitrary values, first check whether the project already has the same kind of pattern.
