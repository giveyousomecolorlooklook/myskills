---
name: user-ui-preview-atlas
description: Generate a sliced UI component atlas from a single UI preview image, especially game UI mockups with green-screen/chroma backgrounds. Use when Codex needs to turn an input preview/screenshot into a component summary sheet, separated UI assets, or a prompt for user-imagegen that preserves real preview components, ratios, borders, bevels, and state effects without inventing old-version or nonexistent elements.
---

# UI Preview Atlas

## Core Rule

Use `user-imagegen` as the underlying image-generation skill. Read its `SKILL.md` before calling the generator. Use its bundled `scripts/image_gen.py` CLI; do not use another image-generation path.

This skill is for **preview image ->拆件汇总图**. Treat the input preview as the only visual reference unless the user explicitly provides more references.

## Workflow

1. Confirm the input preview image path and output target.
   - If the user gives an output path or says to overwrite, follow it.
   - If not specified, create a versioned sibling such as `NameAssetsVxx.png`; do not overwrite existing assets.

2. Inspect the preview.
   - Open/view the image and read its dimensions.
   - Identify only components that visibly exist in the preview.
   - Distinguish independent components from states, outlines, child controls, and repeated instances.
   - When a detail is fragile, estimate or measure the preview bounding box and width/height ratio before prompting.

3. Build a component-analysis table in Chinese before generation.
   Include these fields for every component:
   - 组件名
   - 在预览图中的存在形式：独立组件 / 父组件 / 子组件 / 状态描边
   - 预估预览图坐标或区域
   - 预估宽高比
   - 是否保留为拆件
   - 是否有浮雕
   - 外描边
   - 内描边
   - 填充材质
   - 禁止误生成点

4. Generate the atlas prompt in Chinese.
   - Use `references/prompt-template.md` when composing the prompt.
   - The prompt must say the preview image is the only reference.
   - The prompt must include canvas size, green background, output layout boxes, component ratios, bevel/border properties, and a ban on invented components.
   - For state effects, never ask for a standalone component unless it visibly exists as an independent component. Example: a cyan selected outline on a list row must not become a separate cyan strip/button.

5. Call `user-imagegen` CLI in edit mode with the preview as the only `--image`.
   Recommended shape:
   ```powershell
   python "C:\Users\admin\.codex\skills\user-imagegen\scripts\image_gen.py" edit `
     --model gpt-image-2 `
     --image "<preview.png>" `
     --prompt "<Chinese prompt>" `
     --size 2048x2048 `
     --quality high `
     --output-format png `
     --out "<atlas.png>"
   ```
   Add `--force` only when the user explicitly requested overwrite.

6. Validate the output visually.
   Check:
   - pure green background
   - all components separated and crop-friendly
   - no old-version or non-preview elements
   - no text/watermark unless requested
   - ratios and visual properties match the analysis
   - state outlines did not become invented standalone buttons

7. Report the saved path, the final prompt summary or full prompt if requested, and whether the output appears to satisfy the component-analysis table.

## Prompting Rules

- Use Chinese prompts by default.
- Be literal and conservative. Do not add decorative pieces, icons, characters, scenery, labels, or extra UI controls.
- Parent panels should be empty if child controls will be sliced separately.
- Buttons, text placeholders, framed panel backgrounds, close buttons, slots, and state-row backgrounds are separate only when that split matches the preview.
- Repeated components should appear once unless the user asks for all instances.
- Keep each atlas component inside a specified bounding box with green spacing around it.
- Specify whether each component has no bevel, subtle bevel, or obvious bevel; do not let the generator invent thick relief.
- Specify outer and inner border separately.
- Specify “细描边” vs “厚边框” when important.

## Reference

For the reusable Chinese analysis checklist and prompt skeleton, read `references/prompt-template.md`.
