# Lucky Doctor - 幸运医生

药品说明书智能识别与语音播报系统，同时充当用户的**私人药物助理**：维护历史药品记录、检测重复用药与药物相互作用，帮助老年人看清读懂药品说明书。核心用法：照护者用 Skill 整理药品资料、生成语音与**药盒二维码贴纸**并打印贴到药盒；App 用户**扫码即得**资料与语音播报——二维码读取是确定性的，替代易出错的"拍药盒 OCR 文字识别"（OCR 保留为无贴纸药盒的兜底）。

## 项目结构

```
lucky-doctor/
├── skill/                    # Agent SKILL (Python)
│   ├── SKILL.md              # 技能说明
│   ├── scripts/              # 可执行脚本 (识别/录音/打包/贴纸/记录管理)
│   ├── lib/                  # 核心推理库
│   ├── data/                 # 用户私人药品记录 + 内置冲突规则
│   └── examples/             # 示例图片
│
└── mobile/                   # Flutter Android 应用
    ├── lib/
    │   ├── models/           # 数据模型
    │   ├── services/         # OCR / 匹配 / 音频 / 导入
    │   ├── screens/          # UI 界面
    │   └── widgets/          # 可复用组件
    └── assets/
```

## 子项目 1: Agent SKILL

### 功能
- 药盒/说明书图片 OCR 文字识别 (PaddleOCR-VL)
- Agent 归纳总结说明书内容，生成老年人友好的播报文本
- Agent 引导用户协作编辑播报文本
- **私人药物助理**：
  - 维护历史药品记录（增删改查）
  - 识别新药时与历史记录比对，检测**重复用药**与**药物相互作用**
  - 生成用药分析报告（含免责声明）
- 文字转语音合成 (Qwen3-TTS)
- Agent 生成识别数据、打包为可导入移动应用的数据包
- 生成**药盒二维码贴纸**（PNG 二维码 + A4 打印页），打印贴盒后手机 App 扫码直达资料与语音

> **说明**：本 SKILL 只需要 OCR + TTS 两个模型。理解说明书、归纳总结、
> 编辑引导、生成关键词、药物相互作用语义分析等都由 Agent 完成，无需额外的 VLM 模型。
> 冲突检测采用"脚本确定性规则 + Agent 药理知识"结合的方式。

### 快速开始

> **环境要求**：Python 3.10+（Windows / macOS / Linux 均支持）、OpenVINO >= 2025.4、两个模型（PaddleOCR-VL / Qwen3-TTS）。
> 首次使用前需先完成一次环境配置；配置结果保存到 `skill/data/skill_config.json`，之后不用重复配置。
> 所有依赖都会安装到**项目内专用 venv（`skill/.venv`）**，不会污染你的默认/系统 Python 环境。

```bash
cd skill

# (1) 环境检查 —— 用任意 python 运行（仅需标准库），输出环境状态 JSON
python scripts/setup.py check

# (2) 若未配置 / 部分缺失：两种方式任选
python scripts/setup.py install      # 自动配置：创建/复用 skill/.venv → 装依赖 → 下模型 → 写配置
python scripts/setup.py --guided     # 引导配置：分阶段逐步让用户确认（更细粒度）

# 以上任一完成后，脚本会确定 python 解释器；此后用 `<py>`（配置里的解释器路径）运行：

# 步骤1: OCR 识别药盒（输出原始文字）
<py> scripts/recognize.py --image examples/1.jpg --output text

# 步骤2: 由 Agent 阅读 OCR 文字并归纳播报文本（交互式）
# 步骤3: 由 Agent 整理 metadata + 运行冲突检测
<py> scripts/records.py check-conflict medicine_info.json   # 与历史记录比对

# 步骤4: 生成语音（用户确认后）
<py> scripts/generate_audio.py --text "归纳好的播报文本" --output audio.wav

# 步骤5: 打包数据包（含记录 id；小更新沿用旧 id 用 --id <旧id>）
<py> scripts/create_package.py --info medicine_info.json --audio audio.wav

# 步骤5b: 生成药盒二维码贴纸（打印贴到药盒，用户确认后）
<py> scripts/create_sticker.py --package medicine_package_阿莫西林胶囊.zip

# 步骤6: 保存到历史记录（用户确认后）
<py> scripts/records.py add medicine_info.json
```

> **跨平台说明**：所有脚本都锁定 Python **解释器的绝对路径**（`<py>`），不依赖 `source .../activate`
> 之类的平台激活语法。Windows 的 venv 解释器在 `skill/.venv/Scripts/python.exe`，
> macOS/Linux 在 `skill/.venv/bin/python`，由 `setup.py` 自动创建并写入配置。

### 历史记录管理（私人药物助理 CRUD）
```bash
<py> scripts/records.py list                                  # 查看我的药
<py> scripts/records.py search 阿莫西林                        # 搜索
<py> scripts/records.py get 感冒灵                             # 查看单条
<py> scripts/records.py update <id> changes.json              # 更新
<py> scripts/records.py off 感冒灵                             # 停用
<py> scripts/records.py remove 阿司匹林                        # 删除
<py> scripts/records.py check-conflict medicine_info.json     # 冲突检测
```

### 模型文件
模型自动下载到 `skill/models/`（已 gitignore），通过 `setup.py install`/`--guided` 处理。
等效的手动命令（供参考）：
```bash
<py> -m modelscope download --model megemini/PaddleOCR-VL-1.5-OpenVINO --local_dir skill/models/PaddleOCR-VL-1.5-OpenVINO
<py> -m modelscope download --model snake7gun/Qwen3-TTS-CustomVoice-0.6B-fp16-ov --local_dir skill/models/Qwen3-TTS-CustomVoice-0.6B-fp16-ov
```

## 子项目 2: Android 应用

### 功能
- **主入口**：扫码识别药盒贴纸 → 按 payload 中的记录 id 精确命中本地药库 → 展示资料并**自动播放语音**
- **兜底**：相机拍照 / 相册选图 → Google ML Kit 本地 OCR 文字识别 + 关键词模糊匹配（用于未贴码药盒）
- 音频播放
- 数据包导入 (ZIP)
- ML Kit 条形码解码（`google_mlkit_barcode_scanning`）

### 构建与运行
```bash
cd mobile

# 初始化 Flutter 项目（首次）
flutter create .

# 安装依赖
flutter pub get

# 运行（Linux 桌面模式）
flutter run -d linux

# 运行（Android 设备）
flutter run -d android
```

### 识别路径
**主路径 — 扫码（确定性，推荐）**：
1. 扫描药盒贴纸上的二维码，解码 payload `LD|1|<id>|<药名>`
2. 校验为 Lucky Doctor 二维码后，按 `<id>` 在本地药库**精确匹配**（O(n)）
3. 命中 → 展示资料并自动播放语音；未命中 → 显示药名并引导先导入数据包

**兜底路径 — OCR 关键词匹配（无贴纸药盒）**：
1. OCR 提取图片文字
2. 与本地数据库的 keywords 字段比对
3. 精确包含匹配 (高分) + 编辑距离模糊匹配 (辅助)
4. 返回最佳匹配结果

## 数据包格式

ZIP 文件包含：
- `metadata.json` - 药品元数据 (名称、关键词、用法等)
- `audio.wav` - TTS 生成的语音文件

```json
{
  "id": "uuid",
  "medicine_name": "阿莫西林胶囊",
  "keywords": ["阿莫西林", "消炎", "胶囊"],
  "audio_path": "audio.wav"
}
```

## 药盒二维码贴纸

- Skill 用 `create_sticker.py` 从数据包 ZIP 生成：`PNG` 高分辨率二维码 + `A4` 单页 6 枚可裁剪贴纸（每枚含药名、二维码与扫码提示），打印裁剪后贴到药盒。
- 二维码 payload：`LD|1|<记录id>|<药名>`，其中 `<记录id>` 与数据包 metadata 的 `id` 完全一致。
- 手机 App 扫码 → 按 id 精确匹配本地已导入记录；**数据包由照护者一次性导入**（语音在包内），之后每天扫码即可看资料 + 自动播放语音，全离线可用。
- 更新边界：资料小幅更新可用 `create_package.py --id <旧id>` 保持旧贴纸有效；换新 id 的新包会使旧贴纸引导重新导入。

## 工作流程

```
（照护者）药盒照片 → [SKILL] OCR(建资料) → Agent归纳 → 冲突检测(历史记录) → 用户确认
                                                                ↓
                                                    TTS → 数据包.zip
                                                          ├──► [App] 一次性导入(本地药库)
                                                          └──► create_sticker.py → 贴纸打印贴药盒
                                                          ↓
                                                  保存到历史记录(私人药物库)

（App 用户）扫码药盒贴纸 → 按 id 精确匹配 ──命中──► 资料 + 自动播放语音
                                      └─未命中─► 显示药名 + 引导导入
（兜底）   手机拍照 → [App] OCR → 关键词模糊匹配 → 播放音频
```
