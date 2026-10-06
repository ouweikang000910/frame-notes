# 拆片 · 视频拆解工作台

本地运行的中文视频分析工具：抖音链接或本地视频 → 带时间戳的文案 → 画面分镜与内容结构 → 编辑保存 → Markdown / CSV 导出。

## 下载与安装

这是下载后在自己电脑运行的软件。仓库页面提供代码和说明；使用时会启动本机网页与 Python 后端。

1. 安装 [Python 3.12](https://www.python.org/downloads/) 和 [Node.js 24 LTS](https://nodejs.org/)。Windows 安装 Python 时勾选 **Add python.exe to PATH**，保留 Python Launcher；安装后重新打开终端。
2. 在本仓库点击 **Code → Download ZIP**，解压到普通文件夹（不能直接在压缩包里启动）。也可以使用 Git 克隆：

   ```bash
   git clone https://github.com/ouweikang000910/frame-notes.git
   cd frame-notes
   ```

3. 根据系统安装依赖。首次安装需要联网下载 Python / npm 依赖，FFmpeg 随依赖安装，无需另行安装。

   | 系统 | 首次安装 | 日常启动 |
   | --- | --- | --- |
   | macOS | 双击 `安装依赖.command`，或 `bash scripts/setup.sh` | 双击 `启动拆片.command`，或 `bash scripts/start.sh` |
   | Windows | 双击 `安装依赖.cmd` | 双击 `启动拆片.cmd` |
   | Linux | `python3 scripts/bootstrap.py install` | `python3 scripts/bootstrap.py start` |

4. 用文本编辑器打开项目根目录的 `.env`（安装脚本自动由 `.env.example` 创建），填写自己的百炼配置，见下方。
5. 启动后浏览器会打开 <http://127.0.0.1:8765>。终端保持运行，按 **Ctrl+C** 停止。修改 `.env` 后需重启。

如果 macOS 的下载 ZIP 没有保留双击脚本的执行权限，请用上表中的终端命令。Windows 也可在项目目录运行 `py -3 scripts/bootstrap.py install` 和 `py -3 scripts/bootstrap.py start`。

推荐 Python 3.12；最低 Python 3.10。Node.js 需要 22.12+ 或 24+。不需要安装 Codex、GitHub 插件或登录 GitHub 即可下载公开代码并使用。每个人的配置、视频及历史记录相互独立。

## 百炼配置

在[百炼控制台](https://bailian.console.aliyun.com/)开通服务，获取北京地域 API Key 与业务空间 Workspace ID，并确认账户余额及模型权限。Workspace ID 是业务空间 ID，不是工作空间名称。

```dotenv
DASHSCOPE_API_KEY=你的密钥
BAILIAN_WORKSPACE_ID=你的业务空间ID
ASR_MODEL=fun-asr-realtime
VISION_MODEL=qwen3.6-flash
```

默认按官方文档生成北京地域接口地址。如控制台给出的地址不同，可在 `.env` 中覆盖 `BAILIAN_HTTP_BASE_URL`（兼容接口，结尾 `/compatible-mode/v1`）和 `BAILIAN_WS_URL`（语音 WebSocket 接口）。两个模型名也可以修改。

- [Fun-ASR 本地文件识别](https://help.aliyun.com/zh/model-studio/fun-asr-realtime-python-sdk)
- [图像与视频理解](https://help.aliyun.com/zh/model-studio/vision/)

原视频与记录保存在本机 `data/`。AI 分析会向百炼发送提取的音频、抽帧及文案，按百炼实际用量计费。本地服务只监听 `127.0.0.1`，不提供账号、团队共享或外网部署。

每位使用者需配置自己的百炼账号。仓库不含作者的密钥或视频；`.env`、`data/`、虚拟环境及依赖目录均排除在 Git 之外。未配置百炼时可以打开界面，完成 AI 拆解前需要补齐配置。

## 使用

- 粘贴抖音完整分享文本、`v.douyin.com` 短链接或 `/video/` 标准链接；也支持包含 `modal_id` 的视频详情地址。
- 受平台访问限制影响，部分抖音链接无法直接获取。失败时点击“上传视频继续分析”，使用已保存的 MP4 / MOV 替换来源并继续。
- 一次处理一条，最长5分钟、最大200MB。视频会转换为可在浏览器播放的 H.264 MP4。
- 语音时间来自 ASR；画面按1 FPS抽取，并加入检测到的切镜帧。按30秒片段分析，汇总整条视频。极快动作和小字幕仍需要对照原视频核对。
- 在“整体分析”“文案”“分镜”中修改文字；分镜可调整起止秒数及“待核对”状态。时间必须在视频范围内、按顺序排列且不重叠。
- 点击时间戳或分镜缩略图播放对应位置。保存修改后导出 Markdown 完整报告或带 UTF-8 BOM 的 CSV 分镜表；CSV 可用 Excel 打开。
- 阶段失败后重试会复用视频、转写及已分析的片段。服务中断后，下次启动会将未完成任务标记为可重试。
- 删除记录会同时删除其视频和缩略图，删除前页面会确认。

## 开发与检查

```bash
# 后端（默认8765端口）
.venv/bin/python -m backend.main
# 前端开发服务（另开终端，代理到8765）
cd frontend
npm run dev
```

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm run typecheck
npm run build
```

Python 依赖在 `backend/requirements.lock.txt` 固定版本，前端由 `frontend/package-lock.json` 固定。`PORT` 可更换生产启动端口；前端开发代理默认8765。

Windows 后端 Python 路径为 `.venv\Scripts\python.exe`。推送和 Pull Request 会运行 GitHub Actions，分别在 macOS、Windows、Linux 安装依赖、构建前端并运行后端测试；检查不需要 AI 密钥，不会调用付费模型。

## 常见问题

| 提示或现象 | 处理方式 |
| --- | --- |
| 找不到 Python / Node.js | 安装上述运行环境，关闭并重新打开终端；通过 `python --version` / `node --version` 检查 |
| 安装依赖时下载失败 | 检查到 PyPI / npm 的网络，重新运行安装脚本；不要删除已有的 `.env` 和 `data/` |
| 百炼“待配置” | 检查 `.env` 是否在项目根目录，填写 Key 与 Workspace ID 后重启 |
| 鉴权失败、模型不可用或额度不足 | 按任务显示的具体原因检查地域、模型权限、账户额度；修复后点击重试 |
| 抖音要求 Cookie 或获取超时 | 上传自己有权使用的 MP4 / MOV 继续分析；工具不自动读取浏览器 Cookie |
| 8765 端口被占用 | 若已有拆片服务，直接打开本机地址；否则在 `.env` 中设置其他 `PORT` 并重启 |
| 更新代码 | 停止服务，用 `git pull` 更新，或将新版代码解压到新文件夹并复制原来的 `.env` 与 `data/`；重新安装依赖后启动 |

## 本地接口

| 接口 | 用途 |
| --- | --- |
| `GET /api/health` | 配置状态、依赖状态、当前任务，不返回密钥 |
| `GET /api/analyses` | 历史记录列表 |
| `POST /api/analyses` | JSON `{ "text": "分享文本或链接" }` 创建任务 |
| `POST /api/analyses/upload` | multipart `file` 上传视频 |
| `GET /api/analyses/{id}` | 任务状态与结果 |
| `PATCH /api/analyses/{id}` | 保存标题、overview、transcript、shots |
| `POST /api/analyses/{id}/retry` | 重试失败阶段 |
| `POST /api/analyses/{id}/upload` | 为失败任务替换视频来源 |
| `DELETE /api/analyses/{id}` | 删除记录与素材 |
| `GET /api/analyses/{id}/export?format=markdown或csv` | 导出已保存的结果 |
| `GET /api/analyses/{id}/media/{filename}` | 视频及缩略图，支持视频 Range 请求 |

任务状态为 `queued / running / completed / failed`。结果包含视频信息、逐句 `start/end/text`、分镜 `start/end/description/text/role/rhythm/uncertain` 及整体分析；开始和结束时间均为整条视频的绝对秒数。

## 验证边界

首版在 macOS 上通过27项后端测试、前端 TypeScript 检查与生产构建；Chrome 中验证了首页、桌面/手机布局、播放跳转、修改保存、重新打开后的持久化，以及 Markdown / CSV 下载，未发现前端运行错误。跨系统检查结果见仓库 Actions。实际公开抖音链接探测遇到 Cookie 要求，已验证同一任务可通过上传备用视频继续完成。

自动化测试使用实际生成的视频验证媒体处理，使用可控的 AI 测试适配器验证任务恢复与导出；测试数据不会进入你的历史记录。没有配置百炼时，真实 AI 效果与账户可用性无法验证，界面会明确显示“待配置”，不会生成模拟分析结果。
