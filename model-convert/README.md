# model-convert/ — Qwen3-TTS Base 模型转 OpenVINO（发布者一次性工具）

> **本目录只给「模型发布/维护者」使用，与 skill 运行流程无关。**
> Lucky Doctor skill **不会**调用本目录任何东西，也不会做任何模型转换。
> skill 的声音克隆模型默认从 **Hugging Face**（hf-mirror 镜像）直接下载社区现成的
> INT8 OpenVINO 成品 `aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8`
> （与 CustomVoice 同布局，见 `skill/scripts/setup.py` 的 `MODEL_SPECS`）。
> 本目录只是备选路径：当你**想自己转换并发布**一份 Base 的 OpenVINO 版本
> （例如发到 ModelScope 供无外网环境使用）时才需要。

## 这个工具是干什么的

Qwen3-TTS 的 **Base** 变体（带 speaker encoder，可做声音克隆）没有官方现成的
OpenVINO 权重。本目录提供一个**完全自包含、不依赖 skill 代码**的一次性转换脚本，
把 Base 原模型转成 OpenVINO IR，产物随后**手动上传到 ModelScope** 供所有人直接下载。

上传目标仓库（当前约定）：`megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO`

## 转换频率

- **只需转换一次**（每台需要产出模型的机器一次），转换是幂等的：产物已存在会自动跳过。
- 转换后每次**修改代码/重新发布**才需要重转（此时加 `--force`）。
- skill 使用者**永远不需要**运行本目录脚本——他们下载你上传好的模型即可。

## 目录文件

| 文件 | 说明 |
|------|------|
| `convert_tts_base.py` | 命令行入口：下载原模型 → 转换 → 校验产物 |
| `qwen3_tts_ov_converter.py` | 转换核心（从官方 Qwen3-TTS examples 移植，零项目依赖） |
| `requirements.txt` | 转换专用依赖清单 |

## 一次性准备（独立 Python 环境）

```bash
cd model-convert
python -m venv .venv
# 大陆网络建议追加：-i https://pypi.tuna.tsinghua.edu.cn/simple
.venv/bin/python -m pip install -r requirements.txt
```

> 转换环境与 skill 的 `.venv` 完全隔离，互不引用。

## 执行转换

在 `model-convert/` 下（用刚建好的 venv python）执行：

```bash
# 方式一：ModelScope 下载原模型再转换（大陆推荐）
.venv/bin/python convert_tts_base.py --source modelscope

# 方式二：HuggingFace 下载再转换（境外网络）
.venv/bin/python convert_tts_base.py

# 方式三：已有本地 checkpoint 目录（跳过下载）
.venv/bin/python convert_tts_base.py --model-id /path/to/Qwen3-TTS-12Hz-0.6B-Base

# 可选参数
#   --output-dir <dir>   输出目录（默认 ./Qwen3-TTS-12Hz-0.6B-Base-OpenVINO）
#   --ckpt-dir <dir>     原始权重缓存位置（默认与输出同级 *_src 目录）
#   --force              已有产物也强制重转
```

转换耗时较长（视 CPU 数分钟到数十分钟），磁盘建议预留 ≥ 10 GB。
脚本会自动把 **speech_tokenizer**（参考音频编码必需）一并转进
`<output>/speech_tokenizer/`，产物自包含。

## 校验产物

`<output-dir>` 下应包含：

```
config.json / preprocessor_config.json / 其它 processor 文件
openvino_talker_language_model.{xml,bin}
openvino_talker_embedding_model.{xml,bin}
openvino_talker_text_embedding_model.{xml,bin}
openvino_talker_text_projection_model.{xml,bin}
openvino_talker_code_predictor_model.{xml,bin}
openvino_talker_code_predictor_embedding_model.{xml,bin}
openvino_speaker_encoder_model.{xml,bin}          ← Base 专属（克隆用）
speech_tokenizer/openvino_speech_tokenizer_{encoder,decoder}_model.{xml,bin}
```

## 上传到 ModelScope

1. 在 ModelScope 创建模型库，例如 `megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO`
   （License 建议与官方 Qwen3-TTS 一致；需支持免登录下载，skill 才能拉取）。
2. 把 `<output-dir>` **目录内的全部文件**（注意是文件，不是外层目录）上传到仓库根目录：
   - 网页：ModelScope 网页拖拽上传最省事；或
   - 命令行（先 `modelscope login` 一次）：
     ```bash
     .venv/bin/python -c "from modelscope import HubApi; HubApi().push_model(model_id='megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO', local_dir='Qwen3-TTS-12Hz-0.6B-Base-OpenVINO')"
     ```
3. 上传完成后，若想让 skill 用你自己的仓库，改 `skill/scripts/setup.py` → `MODEL_SPECS["tts_base"]`
   （注意：skill 当前默认值是 Hugging Face 的 `aurora2035/...-INT8`，source 为
   `"huggingface"`；要改用本目录产物时，把该行 source 改成 `"modelscope"` 并换成你的仓库 id）。

## 常见问题

- **`qwen_tts` 装不上 / torch 太大**：qwen-tts 会自动带 torch；CPU 环境用
  `--extra-index-url https://download.pytorch.org/whl/cpu`，或直接装默认版（更大）。
- **HuggingFace 慢/超时**：改用 `--source modelscope`（原模型在 ModelScope 有镜像）。
- **转换中断**：重跑同一命令即可续做（按文件粒度跳过已完成部分）。
- **提示缺依赖**：确认用的是 `model-convert/.venv` 的解释器，且
  `pip install -r requirements.txt` 成功。
- **改过发布仓库**：更新 `skill/scripts/setup.py` 的 `MODEL_SPECS["tts_base"]`，
  并把文档里指向旧 id / 旧目录名的地方一起改掉。
