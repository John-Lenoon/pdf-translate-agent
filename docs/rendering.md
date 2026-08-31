# PDF Overlay Rendering

## V1 contract

原始 PDF 永不修改。渲染器复制页面并在原文字区域创建遮盖，再绘制中文译文；图片、页面顺序、章节和页眉页脚必须保留。

## Layout policy

1. 使用 AST 中的 span/line bbox 计算 segment 区域。
2. 保持正文基准字号，先在原区域内换行。
3. 原区域不足时，在不碰撞图片、页眉页脚和相邻 segment 的前提下扩展文字框。
4. 仍不足时只做有限的局部字号/行距调整；不得截断或溢出到不可见区域。
5. 中文字体必须显式配置并验证 glyph 覆盖；缺字直接产生 `missing_glyph` 错误。

## Validation

每页渲染后执行：PDF 可重新打开、文字对象可提取、segment 输出完整、bbox 不越界、与图片/固定区域无碰撞。任何失败都使 run 进入 `render_failed`，不得标记为 `completed`。

## Known limits

复杂绘图、扫描页面、嵌入字体授权和原 PDF 注释的精确复刻不属于 V1；输入检查必须明确拒绝或标记这些情况。
