# 🤝 AI 英语朋友（AI English Friend）

> 英语老师 + 英国朋友 + 心理委员，三位一体的 AI 英语学习伙伴。
> 由 DeepSeek 大模型驱动，界面与 GitHub Copilot 协作完成。

**第九届传智杯 · AI 创新应用挑战赛（个人赛）参赛作品**

- 作者：李添恩（马鞍山学院，软件工程大一）
- 定位：一个会「懂你」的英语学习伙伴——既能教语法、改错、出题，也能像朋友一样聊天，还能在你情绪低落时温柔倾听。

---

## ✨ 它能做什么

一个 App，七种身份，一个完整的学习闭环：

| 界面 | 功能 |
| --- | --- |
| 💬 AI 对话 | 主界面。个性化画像（自动猜你的语言习惯和心情）、角色扮演（猫娘小棉/鲸鱼娘小汐/英语老师 Emily 等）、语音输入、AI 生成二次元头像 |
| ✏️ 英语助手 | 语法改错 / 中英翻译 / 逐句讲解 / 查单词 |
| 📝 做题本 | AI 围绕知识点出题 → 你作答 → AI 批改 |
| ❌ 错题本 | 做错的题自动收集，可重做、攻克后自动移除 |
| 📅 学习日历 | 坚持天数 + 四级倒计时 + 月历打卡 |
| 📜 历史记录 | 成长统计（总练习 / 今日练习 / 待复习错题） |
| 📋 学习计划 | 内置的待办清单（Daylight 风格） |

**学习闭环**：语法改错 → 针对错误自动出题 → 做题批改 → 错题自动进错题本 → 重做巩固 → 全程记录成长。

**三位一体**：AI 会根据你当前的状态自动切换身份——学知识时是耐心老师，闲聊时是英国朋友，情绪低落时是温柔的心理委员。

---

## 🚀 10 分钟复现指南

### 环境要求

- Python 3.10+（开发环境为 3.12.7）
- 一个 DeepSeek API Key（在 [platform.deepseek.com](https://platform.deepseek.com) 免费申请）

### 第一步：克隆并安装依赖

```bash
git clone <你的仓库地址>
cd ai-english-tutor

# 建议使用虚拟环境
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 第二步：启动应用

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

### 第三步：填入 API Key

在左侧边栏「⚙️ 设置」中粘贴你的 DeepSeek API Key，点击「✅ 确定」。

> 🔐 Key 只在当前会话内存中保存，不写入文件、不随页面刷新持久化，关闭浏览器即失效。

### 第四步：开始使用

1. 在「💬 AI 对话」里和它聊聊（试试发「今天好累」，看它变成心理委员）
2. 去「✏️ 英语助手」输入 `I very like AI`，看它帮你改错
3. 点「针对这句话出题」，体验从改错到做题的闭环
4. 故意答错一题，去「❌ 错题本」重做巩固
5. 到「📜 历史记录」看你的成长数字

---

## 📁 项目结构

```
ai-english-tutor/
├── app.py            # 主程序（全部功能，约 1600 行）
├── plan.html         # 学习计划界面（Daylight 风格待办清单）
├── requirements.txt  # 依赖清单
├── .gitignore        # 挡掉隐私数据与密钥
├── README.md         # 本文档
└── docs/             # 技术文档等
```

---

## 🧠 技术亮点

- **流式回复**：基于 OpenAI SDK 的 `chat.completions.create(stream=True)`，打字机式逐字输出，体验更自然。
- **个性化画像**：无需额外模型，用轻量规则实时分析用户的「语言习惯」和「情绪状态」，动态注入 system prompt，让 AI 越聊越懂你。
- **动态人设**：根据画像 + 选择的角色，实时拼装 system prompt，实现「英语老师 / 英国朋友 / 心理委员」三位一体。
- **健壮性处理**：统一封装超时、限流、鉴权、断连等异常，任何错误都有友好的中文提示。
- **本地持久化**：历史记录、错题本、对话记录保存在本地 JSON，刷新不丢失，且已通过 `.gitignore` 排除在版本库之外。

### 一个关键的坑（brotli 修复）

在 `get_client()` 中，必须保留：

```python
default_headers={"Accept-Encoding": "gzip, deflate"},
```

否则 `httpx 2.x` 与 `brotli` 版本不兼容，流式回复会报解压错误。删掉这行会导致「AI 一直转圈/报错」。

---

## 🎁 可选功能（不装也能用）

以下功能依赖额外服务，不配置时应用会自动降级，核心功能不受影响：

- **语音输入**：需要 Azure Speech 服务（`pip install azure-cognitiveservices-speech` + Azure Key）
- **AI 生成头像**：需要阿里云百炼「通义万相」（在角色设置里填百炼 API Key）

---

## 🔐 隐私与安全

- 代码中**不硬编码任何 API Key**，全部从侧边栏输入。
- `history.json`、`wrongbook.json`、`chat_history.json` 等隐私数据已被 `.gitignore` 挡掉，不会上传到公开仓库。
- 若需更优雅的密钥管理，可在 `.streamlit/secrets.toml` 中配置（该文件同样已被忽略）。

---

## 📄 许可

本项目为传智杯参赛作品，代码仅供参考学习。
