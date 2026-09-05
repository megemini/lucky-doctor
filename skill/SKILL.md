---
name: lucky-doctor
description: >
  Use when the user wants to identify medicine boxes, drug instruction leaflets,
  pharmaceutical packaging, or medication labels. Also use as a personal drug
  assistant: check new medicines against the user's history for duplicate
  medication or drug interactions, manage (add/list/update/delete) the user's
  medicine records, generate voice broadcast for medicine instructions, create
  medicine audio packages for mobile apps, or generate medicine-box QR stickers
  (to be printed and pasted onto medicine boxes so the phone app can scan them).
  Triggers on keywords:
  药盒, 药品, 说明书, 吃药, 用药, 药物, 重复用药, 药物冲突, 相互作用,
  二维码, 贴纸, 扫码, 识别, medicine, drug, pill, capsule, interaction,
  duplicate, 处方, OTC, 语音, 播报, audio, voice, QR, sticker, scan.
---

# Lucky Doctor - 药品说明书智能识别 / 私人药物助理 / 语音播报

拍照识别药品说明书，提取关键信息，与用户协作编辑后生成语音播报，打包为可供移动应用导入的数据包。
同时充当用户的私人药物助理：维护历史药品记录、检测重复用药与药物相互作用。

## 核心定位

本 SKILL 是用户的**私人药物助理**，主要职责：
1. 识别药盒/说明书（**Agent 视觉直读优先，看不清或无视觉时用 OCR 兜底**，用于**建立**药品资料）
2. 归纳、编辑播报文本（Agent 负责）
3. **对照历史记录检测重复用药与药物冲突**
4. 维护用户的历史药品记录（增删改查）
5. 生成语音播报 + 打包移动端数据包
6. 生成**药盒二维码贴纸**（打印贴到药盒，手机 App 扫码即可直达资料与语音，替代易出错的 OCR 识别）

## 核心理念

图片识别遵循「**Agent 视觉直读优先，OCR 模型兜底**」：
- **你具备视觉能力且能看清图片** → 直接查看图片识别，不运行 OCR 脚本；
- **你有视觉但看不清**（图片模糊、小字过密、只拍到局部，或你自己判断无法可靠读出）→ 用 **OCR 模型 (PaddleOCR-VL)** 兜底；
- **你没有视觉能力**（无法读取图片内容）→ 直接调用 OCR 模型。

语音播报使用 **TTS 模型 (Qwen3-TTS)**。

除以上模型外**不需要额外的 VLM 模型**，因为以下能力由 Agent（你）自己承担：
- 理解图片 / OCR 识别出的说明书内容
- 归纳总结为通俗易懂、适合老年人听的播报文本
- 引导用户审阅和编辑播报文本
- 生成移动端匹配所需的结构化数据（药品名、成分、关键词等）
- 基于药理知识做语义级的药物相互作用分析

## 环境要求

- Python 3.10+（Windows / macOS / Linux 均支持）
- OpenVINO >= 2025.4
- OpenVINO 模型：PaddleOCR-VL（OCR，仅在无视觉 / 看不清时兜底）、Qwen3-TTS（语音合成）；
  另有一个可选的 Qwen3-TTS **Base** 变体（声音克隆用）

本 SKILL 跨平台。**不要在命令里硬编码任何本机路径或激活命令**，一律从配置读取（见下文）。

## 首次使用 / 环境检查（必须先做）

本 SKILL 依赖第三方工具与模型（Python 环境、OpenVINO 依赖、OpenVINO 模型——声音克隆用的 Base 模型为可选项）。
**你（Agent）在第一次调用本 skill、或在任何识别/语音脚本运行之前，必须先做环境检查。**

### 第 0.1 步：运行环境检查

用你能找到的任意 Python（系统 `python3`/`python` 即可，此脚本无额外依赖）执行：

```bash
python scripts/setup.py check
```

（Windows 下若 `python` 不存在，用 `py scripts\setup.py check`。）

`check` 返回 JSON，重点看：
- `configured`：是否已配置过
- `deps_installed` / `missing_deps`：依赖是否完整
- `models.ocr_ready` / `models.tts_ready`：模型是否已下载（`models.tts_base_ready` 为可选的**声音克隆** Base 模型状态，未就绪不影响常规流程）
- `python.interpreter`：已选定的 Python 解释器路径（配置后才有）

### 第 0.2 步：按检查结果分流

**情况 A — 已配置且全部就绪**（`configured=true` 且 `deps_installed=true` 且 `models.ocr_ready`、`models.tts_ready` 均为 true；`tts_base_ready` 为可选项，仅声音克隆需要时才要求）：
直接进入工作流程，之后一律用配置里的解释器运行脚本：
```bash
<配置的 interpreter 路径> scripts/recognize.py ...
```
（下文统称 `<py>`。）

> 若你（Agent）具备视觉能力且能直接看清图片，识别阶段可以不运行 `recognize.py`（见 Step 1），此时 OCR 模型未就绪也不阻塞识别；只有在需要 OCR 兜底时，才要求 OCR 模型已就绪。

**情况 B — 未配置或部分缺失**：
把检查结果整理给用户，并询问：
> 检测到环境尚未配置 / 缺少以下资源：[依赖 / OCR 模型（仅需 OCR 兜底时）/ TTS 模型]。
> （1）希望我自动配置，还是（2）希望我一步步引导你配置？

所有依赖会安装到**项目内的专用 venv**（`skill/.venv`），不会污染用户的默认/系统 Python 环境。

- **自动配置** → 运行 `python scripts/setup.py install`（创建/复用 `skill/.venv`、装依赖、下模型、写配置）。
- **引导配置** → 运行 `python scripts/setup.py --guided`，**把每一步的提示与命令逐条转述给用户，由用户确认后再执行**（见下方"引导模式细节"）。

配置完成后，`setup.py` 会把结果保存到 **`skill/data/skill_config.json`**（按机器/平台独立，已 gitignore）。
**之后再次使用本 skill 时不再需要询问**，直接读配置并用 `<py>` 运行即可。

### 引导模式细节（Step-by-Step）

`setup.py --guided` 会分以下阶段逐步进行，**每一阶段都必须向用户确认后执行**：

1. **选择 Python 环境**：
   - `[0] 创建项目专用 venv（skill/.venv）` —— 推荐默认项，用当前 Python 为基础创建独立环境，
     之后所有依赖都装到这里，不碰用户已有环境。
   - 或从检测到的现有环境（conda / venv / 系统 Python）中选一个序号。
2. **创建 venv**：确认后执行 `python -m venv skill/.venv`（仅当选了选项 0）。用户可取消。
3. **安装依赖**：确认后用该环境执行 `pip install -r requirements.txt`。用户可跳过。
4. **下载 OCR 模型**：确认后执行 `modelscope download` 拉取 PaddleOCR-VL。
   用户可跳过（如已有模型）。
5. **下载 TTS 模型**：确认后执行 `modelscope download` 拉取 Qwen3-TTS。
   用户可跳过（如已有模型）。
6. **下载 TTS Base 模型**（可选，仅声音克隆需要）：确认后从 **Hugging Face**
   拉取（经 hf-mirror 镜像）社区 INT8 OpenVINO 成品
   `aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8`（与 CustomVoice 同布局，
   **不涉及本地转换**）。用户可跳过。
7. **保存配置**：写入 `skill_config.json`，供之后复用。

> 跳过某些步骤（如模型已存在）不影响配置保存；缺的模型下次检查仍会提示。

### 各平台要点

- **专用 venv**：所有依赖默认安装到项目内 `skill/.venv`（跨平台），不污染用户默认/系统 Python。
  该目录已 gitignore。
- **激活命令**：脚本锁定的是 Python **解释器的绝对路径**（而非 `source .../activate`），因此
  Windows / macOS / Linux 一律用 `<py> scripts/xxx.py` 运行，不依赖任何平台的激活语法。
  Windows 下 venv 解释器位于 `skill/.venv/Scripts/python.exe`，macOS/Linux 为 `skill/.venv/bin/python`。
  `skill_config.json` 里的 `activate_cmd` 仅供人工在终端里激活时参考，**Agent 不需要用它**。
- **模型路径**：固定为 `skill/models/<模型名>`（相对 skill 目录，跨平台一致）；
  如需覆盖到已有模型目录，可手动编辑 `skill_config.json` 的 `models.*_model_dir`。

## 工作流程

### Step 1: 识别说明书图片（视觉直读优先，OCR 兜底）

用户提供药品图片路径。**先判断识别方式，再识别**：

1. **你具备视觉能力，且能看清图片** → 直接查看图片识别，**不要**运行 OCR 脚本。通读图片内容后进入 Step 2。
   - 自检标准：能可靠读出药品名、成分、用法用量、禁忌等关键字段，没有「看不清 / 在猜」的感觉。
2. **你有视觉能力，但看不清图片**（图片模糊、文字过小过密、只拍到局部，或你自认无法可靠读出内容）→ **用 OCR 兜底**。
3. **你没有视觉能力**（无法读取图片内容）→ 直接调用 OCR。

OCR 命令（情况 2 / 3）：

```bash
<py> scripts/recognize.py --image <image_path> --output text
```

输出：`ocr_text`（原始识别文字）、`image_path`。

> OCR 直接以**整图单次推理**完成识别（不做图片分割）。原图文字应清晰、光线均匀、尽量拍全页面；若整图文字过小导致漏识，可改用对页面局部放大后分多张拍摄、逐张识别。

> 视觉直读与 OCR 结果明显冲突、或关键字段（药名 / 成分 / 用法）仍不确定时，向用户求证或请其重拍更清晰的照片，**不要臆测**。

### Step 2: Agent 阅读并归纳（由你完成）

拿到上一步的识别结果后（**视觉直读内容或 OCR 文本**均可），你要：
1. 通读说明书内容，理解这份说明书的要点
2. 归纳为一段**通俗易懂、适合老年人听的播报文本**，覆盖：
   - 药品名称
   - 适应症（治什么病）
   - 用法与用量（怎么吃、吃多少）
   - 禁忌（谁不能吃、啥情况不能吃）
   - 不良反应（可能出现的不舒服）
3. 要求：口语化、无专业术语、无 markdown、无 emoji、纯文本
4. 展示这段播报文本给用户

同时，从说明书提取结构化数据用于冲突检测和记录保存（见 Step 4）。

### Step 3: 与用户协作编辑播报文本

将播报文本展示给用户，询问是否需要修改措辞。用户可要求改写、润色、补充或简化。

### Step 4: 生成结构化元数据 + 药物冲突分析（由你完成 + 脚本检测）

#### 4.1 生成结构化元数据

根据识别内容整理一份元数据 JSON（参考 `scripts/metadata_template.json`）：

```json
{
  "medicine_name": "阿莫西林胶囊",
  "generic_name": "阿莫西林",
  "ingredients": ["阿莫西林"],
  "category": "抗生素",
  "function": ["消炎", "抗感染"],
  "manufacturer": "XX制药有限公司",
  "keywords": ["阿莫西林", "阿莫西林胶囊", "消炎", "抗生素", "胶囊"],
  "indications": "用于敏感菌引起的感染",
  "contraindications": "青霉素过敏者禁用",
  "usage_summary": "口服，一次0.5g，一日3次"
}
```

**字段要点**：
- `ingredients`（有效成分）：冲突检测的关键，务必从说明书提取
- `category`（药物分类）：如抗生素/解热镇痛/抗凝等
- `function`（功效标签）：2-4 个，如消炎、退烧、止痛
- `keywords`：含药名全名/简称、通用名、功效词、剂型、厂家，共 5-10 个，无标点

用 `write` 工具写成 `medicine_info.json`。

#### 4.2 药物冲突检测（核心：私人药物助理功能）

对历史记录运行冲突检测（脚本确定性规则）：

```bash
<py> scripts/records.py check-conflict medicine_info.json
```

脚本会检测并输出：
- `duplicate_records`：历史中已有同名药品（重复保存）
- `overlaps`：与新药有效成分重叠的历史药品 → **重复用药风险**
- `conflicts`：命中内置已知冲突对表 → **药物相互作用**
- `same_category`：属于同一分类的历史药品（提示性）

**你还要基于药理知识做语义级补充**：综合新药与历史记录的成分/分类/功效，补充脚本未覆盖的相互作用、重复用药、用药时机注意等。

然后向用户呈现一份**简明的用药分析报告**：
- 列出发现的重叠项/冲突项及其风险
- 标注严重程度（高危/中危/提示）
- **必须附上免责声明**（conflicts.json 中的 `disclaimer`）：
  "以上分析仅供参考，非医疗建议，实际用药请遵医嘱或咨询医生/药师。"

### Step 5: 询问用户意向（先确认再操作）

结合分析报告询问用户，例如：
- "识别到『泰诺』与您历史记录中的『感冒灵颗粒』有效成分重叠（均含对乙酰氨基酚），可能存在重复用药风险。"
- "是否需要保存这条记录？是否生成语音播报音频？是否调整用法？"

**只有用户确认后**才进入下一步生成音频。若用户不想保存/生成，则停止，不要擅自操作。

### Step 6: 生成语音（用户确认后）

先用确认后的播报文本生成语音。生成前可询问用户希望用哪种声音（老人通常对熟悉的声音更亲近）：
1. **内置音色**（默认，开箱即用）：如 vivian；
2. **声音克隆**：用家人/照护者的声音朗读，需要用户提供**参考音频**（依赖从 Hugging Face（经 hf-mirror 镜像）下载的 Base 模型，缺失时 `setup.py install` 自动下载，无需任何转换）。

**若用户选内置音色**：

```bash
<py> scripts/generate_audio.py --text "<确认后的播报文本>" --speaker vivian --language chinese --output audio.wav
```

**若用户选声音克隆**（先向用户索取参考音频并说明下方要求，收到后再执行）：

```bash
<py> scripts/generate_audio.py --text "<确认后的播报文本>" --ref-audio "<参考音频路径>" --ref-text "<参考音频逐字文字>" --language chinese --output audio.wav
```

**参考音频要求（转告用户）**：
- 时长 **3~10 秒**、单人说话、**无背景音乐/噪声**、在安静环境录制；
- 格式 wav/mp3 均可（librosa 自动转码），**采样率 ≥16kHz** 效果更好；
- 内容随意（日常话即可）；但若提供 `--ref-text`，**必须与音频内容逐字一致**（ICL 克隆，音色更接近原声）；
- 不提供 `--ref-text` 会自动退化为「仅克隆音色」（x_vector_only），相似度略低；
- 勿用电话录音、强压缩音轨等劣质音频。

> 声音克隆依赖 Qwen3-TTS **Base** 模型（内置 CustomVoice 模型无此能力）。该模型与 CustomVoice 同布局、是**从 Hugging Face（hf-mirror 镜像）直接下载的社区 INT8 OpenVINO 成品**（`aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8`），由 `scripts/setup.py install` 自动下载到 `<skill>/models/Qwen3-TTS-Base-0.6B-OpenVINO-INT8/`，**不涉及任何本地转换**。若缺失，克隆脚本会报错并提示运行 `setup.py install`，不影响内置音色流程。

> 通用提示：默认**贪婪解码 + 16-bit PCM**。若生成的音频**没有声音/异常**：先加 `--device CPU` 重试（Intel 机器上 fp16 模型走采样易出现 nan/inf）；脚本检测到全零或过小音量时会打印告警。长文本建议改用 `--text-file <文件>`。

### Step 7: 打包数据包

```bash
<py> scripts/create_package.py --info medicine_info.json --audio audio.wav
```

输出 `medicine_package_<药名>.zip`，包含 `metadata.json`（含 `id`、ingredients/category/function）+ `audio.wav`，可直接导入移动应用。

**记录 id（关键）**：包内 metadata 的 `id` 决定手机本地记录与二维码贴纸的关联。优先级为：显式 `--id <id>` > `medicine_info.json` 里已有的 `id` > 自动生成新 UUID。

- **小更新沿用旧 id**：同一药品仅调整文案/音频时，若希望药盒上已贴的二维码不失效，请带 `--id <旧id>` 重新打包（或先写好 `medicine_info.json` 的 `id`）。
- 全新药品默认生成新 id，此时旧贴纸会失效（App 会引导重新导入），需重新生成贴纸。

### Step 7.5: 生成药盒二维码贴纸（打印贴药盒）

```bash
<py> scripts/create_sticker.py --package medicine_package_<药名>.zip
```

从数据包 ZIP 读取 `metadata.id` 与药名生成二维码贴纸，输出：
- `medicine_sticker_<药名>.png` —— 高分辨率二维码图
- `medicine_sticker_<药名>.pdf` —— A4 可裁剪贴纸（默认 6 枚，含药名、二维码与**底部记录 id**）

**默认贴纸 70×50mm**（适合常见 11×6cm 药盒）：药名居中于顶部，二维码按版面自动缩放（该尺寸下约 29–30mm，扫码从容），**底部整行显示二维码 payload 里的完整记录 id**（与 `metadata.id` 一致，方便把贴纸对上药品记录；字号随 id 长度自动适配，纯文本无特殊符号）。盒面较小、希望少遮挡时调小尺寸：
```bash
# 换用更小的贴纸（例 60mm 宽 × 40mm 高），枚数超过单页容量时自动分页：
<py> scripts/create_sticker.py --package medicine_package_<药名>.zip --sticker-size 60x40
# 强制二维码边长（mm），默认自动；太小扫不上时加大：
<py> scripts/create_sticker.py --package medicine_package_<药名>.zip --qr-size-mm 20
```

告诉用户把贴纸打印、裁剪后贴到药盒醒目位置；手机 Lucky Doctor App **主入口扫码**即可直达资料并自动播放语音（无需 OCR）。

> 注意：`create_sticker.py` 只接受数据包 ZIP（不从裸 metadata 生成），确保贴纸 id 与导入记录 id 天然一致。

### Step 8: 保存记录（用户确认后）

生成音频后，将本次药品加入历史记录（作为用户的私人药物库）：

```bash
<py> scripts/records.py add medicine_info.json
```

若历史已有同名药品会自动更新（去重）。记录会保存 ingredients/category/function 等信息，供下次冲突检测使用。

---

## 历史药品记录管理（私人药物助理 - CRUD）

用户可以通过对话管理历史药品记录。依据用户的说法，执行相应操作：

| 操作 | 用户说法示例 | Agent 动作 |
|------|------------|-----------|
| 创建/保存 | "记住这个药"、"添加阿莫西林" | `records.py add <file>` |
| 查询全部 | "我有哪些药？"、"我的药库" | `records.py list` |
| 搜索 | "查一下阿莫西林" | `records.py search <关键词>` |
| 查看单条 | "看看感冒灵的详情" | `records.py get <名/id>` |
| 更新 | "把阿莫西林改成一天两次"、"补充用法" | `records.py update <id> <changes.json>` |
| 停用/启用 | "我停用感冒灵了" | `records.py off <名> | on <名>` |
| 删除 | "删掉阿司匹林" | `records.py remove <名/id>` |

**records.py 全部命令**：
```bash
<py> scripts/records.py list
<py> scripts/records.py search <keyword>
<py> scripts/records.py get <id_or_name>
<py> scripts/records.py add <record_or_metadata.json>
<py> scripts/records.py update <id> <changes.json>
<py> scripts/records.py remove <id_or_name>
<py> scripts/records.py check-conflict <metadata.json>
<py> scripts/records.py on <id_or_name>    # 启用
<py> scripts/records.py off <id_or_name>   # 停用
<py> scripts/records.py history <id_or_name>
```

**记录数据的修改（update/remove/off/on）都要先与用户确认**，得到明确同意后再执行。

**数据位置**：`skill/data/medicine_records.json`（gitingored，属于用户私人数据）。

---

## 免责声明与安全须知

- 所有药物冲突/相互作用分析**仅供老年用户参考，绝不替代专业医疗建议**
- 每次分析报告必须附带免责声明："以上分析仅供参考，非医疗建议，实际用药请遵医嘱或咨询医生/药师"
- 冲突检测结果仅供参考，不替用户做停药/换药决定
- 用户对记录的保存、修改、删除有最终决定权（每次写操作前先确认）
- 严重（high）风险项要明确提示，但语气应温和、不制造恐慌

## 脚本参数

### recognize.py
| 参数 | 默认值 | 说明 |
|------|--------|------|
| --image | (必填) | 药品图片路径 |
| --device | AUTO | OpenVINO 设备 (CPU/GPU/AUTO) |
| --output | json | json 或 text（建议 text，便于阅读） |
| --ocr-max-tokens | 5120 | OCR 最大生成 token 数 |

### generate_audio.py
| 参数 | 默认值 | 说明 |
|------|--------|------|
| --text | (二选一必填) | 要合成的播报文本（与 `--text-file` 互斥） |
| --text-file | — | 从 UTF-8 文件读取文本（与 `--text` 互斥，可单独使用） |
| --speaker | vivian | 说话人 |
| --language | chinese | 语言 |
| --instruct | 用友好亲切的语气说话。 | TTS 风格指令 |
| --output | audio.wav | 输出文件路径 |
| --device | AUTO | OpenVINO 设备（fp16 异常/静音时改 `CPU` 试试） |
| --do-sample | 关闭（贪婪解码） | 开启采样；fp16 模型在 CPU 上可能出现 nan/inf 导致静音，默认关闭 |
| --float32 | 关闭（16-bit PCM） | 输出 32-bit 浮点 WAV |
| --max-tokens | 2048 | 最大生成 token 数 |
| --ref-audio | — | 参考音频路径/URL，提供后启用**声音克隆**（需 Base 模型；缺失时 `setup.py install` 自动从 ModelScope 下载，见下） |
| --ref-text | — | 参考音频的逐字文字（ICL 克隆，更接近原声） |
| --x-vector-only | 关闭 | 仅克隆音色、忽略 `--ref-text`（省略 `--ref-text` 时自动启用） |
| --tts-base-dir | models/Qwen3-TTS-Base-0.6B-OpenVINO-INT8 | 覆盖声音克隆所用 Base 模型目录 |

可用说话人：vivian, ryan, serena, aiden, dylan, eric, ono_anna, sohee, uncle_fu
可用语言：chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish

**声音克隆（可选能力）**：CustomVoice 模型仅支持上表说话人；克隆需要
Qwen3-TTS **Base** 模型。它与 CustomVoice 同布局、是从 Hugging Face
（hf-mirror 镜像）拉取的**社区 INT8 OpenVINO 成品**
（`aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8`），由
`<python> scripts/setup.py install` 自动下载到
`<skill>/models/Qwen3-TTS-Base-0.6B-OpenVINO-INT8/`，**不涉及任何本地转换**。
模型就绪后直接克隆：
`generate_audio.py --ref-audio <参考音频> [--ref-text <文字>]`。
`<python> scripts/setup.py check` 会报告 `tts_base_ready` 状态。

### create_package.py
| 参数 | 默认值 | 说明 |
|------|--------|------|
| --info | (必填) | 元数据 JSON 文件路径（或内联 JSON） |
| --audio | (必填) | 音频 WAV 文件路径 |
| --id | 自动 | 记录 id（复用 `--info` 内 `id` 或自动新 UUID）；小更新沿用旧 id 可保持旧贴纸有效 |
| --output | medicine_package_<name>.zip | 输出 ZIP 路径 |

### create_sticker.py（药盒二维码贴纸）
| 参数 | 默认值 | 说明 |
|------|--------|------|
| --package | (必填) | create_package.py 生成的数据包 ZIP（从中读取 id 与药名） |
| --out-png | medicine_sticker_<name>.png | 二维码 PNG 输出路径 |
| --out-pdf | medicine_sticker_<name>.pdf | A4 打印贴纸 PDF 输出路径 |
| --error | q | 二维码纠错级别 l/m/q/h（贴纸易脏，建议 q） |
| --scale | 20 | 每模块像素数（越大越清晰；建议 ≥20 保打印质量） |
| --copies | 6 | 贴纸总枚数（每页放不下的枚数超过则自动加页） |
| --sticker-size | 70x50 | 单枚贴纸尺寸（宽x高，mm）。默认 70×50（适合常见 11×6cm 药盒）；盒面小需减少遮挡时可调小，枚更大/更多时自动分页 |
| --qr-size-mm | 自动 | 二维码边长（mm）。默认自动：随贴纸与底部文字高度自适应居中（70×50 下约 29–30mm）。扫码失败时加大此值、放大 --sticker-size，或 --error 用 m |

> 该脚本依赖新增的 `segno` / `reportlab`。若 skill venv 未装（报 ModuleNotFoundError），先执行
> `python scripts/setup.py install`（会复用已有 venv/模型，仅补齐依赖）。

### setup.py（环境检查 / 配置）
| 命令 | 说明 |
|------|------|
| `setup.py check` | 只读检查环境状态，输出 JSON（用任意 python 运行） |
| `setup.py install [--no-deps] [--no-models] [--venv dir] [--no-venv]` | 自动配置：创建/复用项目 venv → 装依赖 → 下模型 → 写配置 |
| `setup.py --guided` | 引导模式：分阶段（选环境/建venv/装依赖/下OCR模型/下TTS模型/存配置）逐步让用户确认 |

### records.py（记录管理 + 冲突检测）
| 命令 | 说明 |
|------|------|
| list | 列出全部历史记录 |
| search <关键词> | 按名称/成分/关键词搜索 |
| get <名或id> | 查看单条记录（支持简称前缀，如"感冒灵"匹配"感冒灵颗粒"） |
| add <json> | 新增/更新记录（按药名去重） |
| update <id> <changes.json> | 更新指定字段 |
| remove <名或id> | 删除记录 |
| on/off <名或id> | 启用/停用记录 |
| check-conflict <metadata.json> | 冲突检测，与历史记录比对 |
| history <名或id> | 查看记录 |

## 模型文件

模型存储在 `skill/models/` 目录下（已 gitignore），此路径跨平台固定：

- `PaddleOCR-VL-1.5-OpenVINO/` - OCR 模型
- `Qwen3-TTS-CustomVoice-0.6B-fp16-ov/` - TTS 语音合成模型
- `Qwen3-TTS-Base-0.6B-OpenVINO-INT8/` - TTS **Base** 模型（可选，仅声音克隆需要；Hugging Face 社区 INT8 OpenVINO 成品，与 CustomVoice 同布局，无需转换）

**首次使用**请通过 `setup.py install`（或 `setup.py --guided`）自动下载到上述目录，无需手写命令。
- OCR / TTS 模型从 **ModelScope** 下载（modelscope ≥ 1.30 移除了 `python -m modelscope` 入口，脚本内部使用 `snapshot_download` Python API）；
- TTS Base 模型从 **Hugging Face** 下载，脚本会自动设置 `HF_ENDPOINT=https://hf-mirror.com`。

等效的手动命令（供参考）：
```bash
# OCR 模型
<py> -c "from modelscope import snapshot_download; snapshot_download('megemini/PaddleOCR-VL-1.5-OpenVINO', local_dir='skill/models/PaddleOCR-VL-1.5-OpenVINO')"
# TTS 模型
<py> -c "from modelscope import snapshot_download; snapshot_download('snake7gun/Qwen3-TTS-CustomVoice-0.6B-fp16-ov', local_dir='skill/models/Qwen3-TTS-CustomVoice-0.6B-fp16-ov')"
# TTS Base 模型（声音克隆，可选；缺失时以上 setup 命令也会自动补下）
<py> -c "import os; os.environ['HF_ENDPOINT']='https://hf-mirror.com'; from huggingface_hub import snapshot_download; snapshot_download('aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8', local_dir='skill/models/Qwen3-TTS-Base-0.6B-OpenVINO-INT8')"
```

## 示例

测试用例在 `skill/examples/` 目录下（**运行前需先完成环境配置**）：

```bash
<py> scripts/recognize.py --image examples/1.jpg --output text
```

## 内存管理

OCR 和 TTS 使用 lazy loading，每次只加载一个模型，用完即释放，内存占用低。

## 数据包格式

生成的 ZIP 包含：
- `metadata.json` - 药品元数据（名称、关键词、用法等，含记录 `id`）
- `audio.wav` - TTS 生成的语音文件

此数据包可导入到 Lucky Doctor 移动应用中使用；也可用 `create_sticker.py` 生成药盒二维码贴纸。

## 二维码贴纸规范（与移动端必须一致）

贴纸二维码内容（payload）为一行文本：

```
LD|1|<record_id>|<medicine_name>
示例: LD|1|3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c|阿莫西林胶囊
```

- `LD`：本应用固定前缀（识别其它二维码时给出"不是 Lucky Doctor 二维码"提示）
- `1`：payload 版本
- `record_id`：与数据包 metadata.json 的 `id` **完全一致**，App 据此在本地药库精确查找
- `medicine_name`：药名短码，本机无该记录时仍可显示名称并引导导入

**更新边界**：
- 数据包重新生成且使用新 `id` 后，旧贴纸失效 → App 会提示"请先导入数据包"（导入新包即可）；
- 仅文案/音频小幅更新时，用 `create_package.py --id <旧id>` 复用旧 id 重新打包，旧贴纸继续有效。
