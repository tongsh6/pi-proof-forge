# PiProofForge 应用图标规范

本文件是 PiProofForge 桌面应用图标（品牌资产）的唯一规范与使用说明。图标属于独立品牌资产，不属于 9 页 GUI 的信息架构、组件、Design Tokens、导航或交互变更，因此不在 `ui/design/piproofforge.pen` 画布内维护；其色彩与质感遵循 `ui/design/DESIGN.md` 的暗色 + 青色设计语言。

## 设计概念

**Forged π — 一枚锻打成型的 π。**

- **π（Pi）**：品牌首字，单件、几何化的希腊字母 π 是图标唯一主形，小尺寸下仍然成立。
- **Proof**：不额外叠加对勾、印章、卡片或盾牌。这些元素要么在 16–32 px 退化成噪点，要么把工具图标变成通用「认证」符号；π 本身承担品牌识别，`Proof` 由产品名与 evidence-first 定位承担。
- **Forge**：用材质而不是火花贴纸表达锻造——青色阳极氧化金属渐变、左上高光、右上受击端残留的暖色回火以及低亮度 forge glow。没有金色四角星、没有发光粒子，避免「AI 闪光」与游戏化观感。
- **底座**：深蓝黑 macOS 圆角方形（squircle），与 App 的暗色面板、青色强调色一致；去掉蓝色占位方块。

## 构成规格

| 项 | 规格 |
| --- | --- |
| 画布 | 1024 × 1024，透明背景 |
| 平台留白 | 四周 100 px（macOS 图标栅格，内容区 824 × 824） |
| 圆角底板 | 824 × 824，圆角半径 185 px，填充 `#132A50 → #09162C → #050B18` 对角渐变 |
| 主形 | 单路径 π，光学盒 600 × 520，居于画面中心；水平端点外挑 42 px，竖笔宽 104 px，笔端斜切 |
| 主色 | `#CFFAFE → #67E8F9 → #22D3EE → #0EA5E9 → #0891B2 → #0B6B86`（青色阳极氧化金属） |
| 强调 | `#F59E0B / #FDE68A` 仅用于受击端余温与 forge glow，面积 < 3% |
| 细节 | 左上白色高光边缘、右侧暗面、底部内阴影；不使用点阵纹理、外发光光斑或投影贴纸 |
| 平台输出 | macOS `.icns`、Windows `.ico`、PNG 32 / 64 / 128 / 128@2x / 256 / 512 |

## 资产与调用位置

| 文件 | 用途 |
| --- | --- |
| `ui/design/brand/app-icon.svg` | 矢量主源（唯一可编辑源） |
| `ui/design/brand/app-icon-1024.png` | 1024 RGBA 栅格主源，供 `tauri icon` 生成平台图标 |
| `ui/src-tauri/icons/32x32.png` | 通用小尺寸 / Linux |
| `ui/src-tauri/icons/64x64.png` | 通用小尺寸 |
| `ui/src-tauri/icons/128x128.png` | 通用 / Linux |
| `ui/src-tauri/icons/128x128@2x.png` | 256 px 高清 PNG |
| `ui/src-tauri/icons/256x256.png` | 兼容旧路径的大尺寸 PNG |
| `ui/src-tauri/icons/icon.png` | 512 px PNG |
| `ui/src-tauri/icons/icon.icns` | macOS 应用包图标 |
| `ui/src-tauri/icons/icon.ico` | Windows 可执行文件 / 安装包图标 |
| `ui/src-tauri/tauri.conf.json` → `bundle.icon` | Tauri 打包图标入口 |

## 使用规则

- 优先使用 `ui/design/brand/app-icon.svg`；位图只从 1024 PNG 等比例生成，禁止拉伸、旋转、加描边或重新上色。
- App 图标最小使用尺寸 16 px；16–32 px 下只保留 π 主体与青蓝层次，暖色回火细节自然消失属预期行为，不另做小尺寸特供版。
- 图标不包含文字；不要将 `PiProofForge` 字样塞进图标。
- 背景必须保留透明留白；不要给图标再加白色或黑色底板，也不要自行补投影（macOS / Windows 会处理）。
- 用于深色、浅色背景时均使用原图；浅色背景下依赖 824 px 深色底板保证对比度。

## 重新生成

修改 `app-icon.svg` 后，按以下步骤同步所有位图（步骤 2–4 在 `ui/` 目录执行）：

1. 导出 1024 × 1024、保留透明通道、不裁切的 `app-icon-1024.png`（任意高质量 SVG 栅格化工具，sRGB）。
2. 生成平台图标到临时目录（避免提交 Android / iOS 资源）：

   ```bash
   cd ui
   ./node_modules/.bin/tauri icon "$(pwd)/design/brand/app-icon-1024.png" -o "$(pwd)/../.tmp/app-icons"
   ```

3. 只拷贝桌面端资源：

   ```bash
   cp ../.tmp/app-icons/{32x32.png,64x64.png,128x128.png,128x128@2x.png,icon.icns,icon.ico,icon.png} src-tauri/icons/
   ```

4. 可选：同步旧路径的 256 px PNG：`python3 -c "from PIL import Image; Image.open('design/brand/app-icon-1024.png').convert('RGBA').resize((256,256), Image.Resampling.LANCZOS).save('src-tauri/icons/256x256.png')"`。

5. `bundle.icon` 已列出的五项保持路径不变；若增删平台资源，同步更新 `ui/src-tauri/tauri.conf.json`。

## 验收要点

- 16 / 24 / 32 / 48 / 64 / 128 / 256 / 512 / 1024 px 下 π 结构不粘连、不糊成色块。
- 深色、浅色背景均有清晰轮廓；透明留白保留完整。
- `icon.icns` 至少包含 16–1024 px 全套位图；`icon.ico` 至少包含 16–256 px；打包后 Dock / 任务栏 / 安装包显示新图标。
- 改动后重新构建前端与桌面壳；图标不参与页面运行时逻辑。

_Last updated: 2026-10-18_
