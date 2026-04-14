# Tailwind Conventions

## Goal
保持 Tailwind 写法稳定、可读、可复用，并与项目现有页面一致。

## Rules
- 优先使用标准 Tailwind token
- 非必要禁止 arbitrary values
- 字号、间距、圆角、宽高优先复用现有模式
- 同类组件保持一致 class 结构
- 能抽公共 class / 组件时，不重复散写

## Prefer
- `text-xs text-sm text-base`
- `px-3 py-2`
- `gap-2 gap-3 gap-4`
- `rounded-md rounded-lg`
- `w-full max-w-*`
- `flex items-center justify-between`

## Avoid
- `text-[12px]`
- `leading-[17px]`
- `mt-[13px]`
- `rounded-[5px]`
- `w-[318px]`

## Exception
仅在以下情况允许 arbitrary values：
1. 设计稿强约束
2. 组件库覆盖困难
3. 已确认项目中普遍采用该值
4. 无等价 token 可替代

使用 arbitrary values 时，必须先判断项目中是否已有同类写法。