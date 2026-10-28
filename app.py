"""
AI 英语学习助手 (AI English Tutor)
=================================
一个帮助你学习英语的小工具：改语法、翻译、讲句、查单词、做题、错题本、学习日历、历史记录和学习计划。
由 DeepSeek 大模型驱动，界面风格与 GitHub Copilot 协作完成。

导航方式：左上角 ☰ 菜单切换界面（窗口栈最多保留最近 2 个界面，进入第 3 个时自动关闭最早的）。
学习闭环：语法改错 → 针对错误出题 → 做题批改 → 错题自动进错题本 → 重做巩固 → 全程记录成长。

作者：李天恩
学校：马鞍山学院
用途：第九届传智杯 AI 创新应用挑战赛 参赛作品

运行方式：
    pip install -r requirements.txt
    streamlit run app.py
"""

import calendar
import hashlib
import json
import pathlib
import re
import tempfile
import time
from datetime import date
from typing import Iterator

import streamlit as st
import requests
try:
    from streamlit_mic_recorder import mic_recorder
except ImportError:
    mic_recorder = None

try:
    import azure.cognitiveservices.speech as speechsdk
except (ImportError, OSError):
    speechsdk = None

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)


# ===== 全局配置（演示时只需要改这里）=====
MODEL = "deepseek-chat"          # 使用的模型名
TEMPERATURE = 0.7                # 回答创造性：0 严谨 ~ 1 活泼
REQUEST_TIMEOUT = 60             # 单次请求超时（秒），防止一直转圈
MAX_STREAM_DURATION = 180        # 流式回复总时长上限（秒）
CET4_DATE = date(2026, 12, 12)   # 四级笔试日期
MAX_INPUT_LENGTH = 5000          # 限制单次输入长度
HISTORY_LIMIT = 50               # 历史记录最多保留条数
HISTORY_FILE = pathlib.Path(__file__).parent / "history.json"      # 历史记录本地存档
WRONGBOOK_FILE = pathlib.Path(__file__).parent / "wrongbook.json"  # 错题本本地存档
CHAT_FILE = pathlib.Path(__file__).parent / "chat_history.json"    # 对话记录本地存档

ENCOURAGEMENTS = (
    "今天学一点，也是在向前走。",
    "不用一次学很多，持续就很棒。",
    "每一次练习，都让表达更自然。",
    "慢慢来，你正在积累真正的进步。",
    "愿意开始，就是很棒的一步。",
    "把今天学会的一点点，变成明天的底气。",
    "不必完美，保持好奇就很好。",
)

MILESTONES = (
    (365, "🏆 一整年的坚持"),
    (100, "💎 百日学习者"),
    (30, "🌟 坚持满月"),
    (7, "🌿 连续一周"),
    (1, "🌱 已经启程"),
)

# AI 对话的预设角色人设
PERSONAS = {
    "🐳 鲸鲸英语伙伴（默认）": (
        "你是原创的鲸鲸英语学习伙伴，名字叫小汐。你温柔、沉静、富有想象力，"
        "偶尔用海洋和潮汐作轻柔比喻，但不过度使用口癖。"
        "你是一位耐心的英语老师和聊天伙伴，用中文为主、穿插简单实用的英语帮助用户学习。"
        "尊重用户感受，先肯定努力，再温和解释问题；不要模仿现有作品或角色。"
    ),
    "🐱 猫猫英语伙伴": (
        "你是原创的猫猫英语学习伙伴，名字叫小棉。你温柔、活泼、亲切，"
        "偶尔自然地说一声「喵」，但不要每句话都重复口癖。"
        "你是一位耐心的英语老师，也是一位尊重用户感受的聊天伙伴。"
        "用中文为主、穿插简单实用的英语帮助用户学习；先肯定努力，再温和解释问题。"
        "不要声称自己是真人或真实动物，也不要模仿任何现有作品或角色。"
    ),
    "👩‍🏫 英语老师 Emily": (
        "你是一位耐心温柔的英语老师 Emily。你总是先鼓励学生，再指出问题；"
        "讲解用简单英语，必要时用中文补充。你亲切但专业。"
    ),
    "🐱 猫咪学习伙伴": (
        "你是一只聪明的猫咪学习伙伴，说话俏皮可爱，偶尔「喵～」一声；"
        "但你讲解英语知识非常清楚，会用最简单的比喻让人听懂。"
    ),
    "🔥 热血动漫主角": (
        "你是一位热血动漫主角，说话充满斗志，喜欢说「冲啊！」「燃烧吧！」；"
        "但你教起英语来认真又可靠，鼓励对方绝不放弃。"
    ),
    "🤖 未来 AI 助手": (
        "你是一个来自 2126 年的 AI 助手，语气冷静、简洁，偶尔提到未来世界的小趣闻；"
        "讲解清晰高效。"
    ),
    "🎀 自定义角色": "",
}

ALL_VIEWS = [
    "💬 AI 对话 Chat",
    "✏️ 英语助手 Tutor",
    "📝 做题本 Quiz",
    "❌ 错题本 Wrong Book",
    "📅 学习日历 Calendar",
    "📜 历史记录 History",
    "📋 学习计划 Plan",
]

st.set_page_config(page_title="AI 英语朋友", page_icon="🤝", layout="centered")

# ===== Daylight 风格与流畅动效（高对比度 + 苹果风）=====
st.markdown("""
<style>
    :root {
        --daylight-ease: cubic-bezier(.22, 1, .36, 1);
        --daylight-spring: cubic-bezier(.2, .8, .2, 1);
    }
    @keyframes daylightFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    @keyframes daylightFadeUp {
        from { opacity: 0; transform: translateY(10px) scale(.99); }
        to { opacity: 1; transform: translateY(0); }
    }
    .stApp {
        background:
            radial-gradient(ellipse at 12% 4%, rgb(245 222 229 / 42%), transparent 30rem),
            radial-gradient(ellipse at 92% 18%, rgb(222 233 240 / 48%), transparent 32rem),
            #f8f7f5;
    }
    .block-container { color: #292721; }
    .block-container > div { animation: daylightFadeIn 420ms var(--daylight-ease) both; }
    h1 {
        letter-spacing: -0.04em;
        font-weight: 700;
        animation: daylightFadeUp 650ms var(--daylight-ease) both;
    }
    .stButton > button {
        border: 1px solid #71866a;
        border-radius: 14px;
        background: linear-gradient(145deg, #81977a, #687f63);
        color: #fff;
        font-weight: 600;
        text-shadow: 0 1px 1px rgb(0 0 0 / 14%);
        box-shadow: inset 0 1px 0 rgb(255 255 255 / 28%), 0 2px 8px rgb(77 91 69 / 14%);
        transition:
            opacity 240ms var(--daylight-ease),
            transform 360ms var(--daylight-spring),
            box-shadow 300ms var(--daylight-ease);
        animation: daylightFadeIn 420ms var(--daylight-ease) both;
    }
    .stButton > button:hover {
        background: linear-gradient(145deg, #768d6e, #5e7758);
        box-shadow: inset 0 1px 0 rgb(255 255 255 / 24%), 0 6px 16px rgb(77 91 69 / 18%);
        transform: translateY(-1px);
    }
    .stButton > button:active {
        background: linear-gradient(145deg, #5e7758, #71866a);
        box-shadow: inset 0 2px 5px rgb(0 0 0 / 12%);
        transform: translateY(0) scale(.985);
    }
    [data-testid="stSidebar"] {
        background: rgb(255 255 255 / 74%);
        border-right: 1px solid rgb(226 220 216 / 75%);
        backdrop-filter: blur(22px) saturate(135%);
        -webkit-backdrop-filter: blur(22px) saturate(135%);
    }
    .stTextInput input, .stTextArea textarea, .stDateInput input {
        border-radius: 12px !important;
        border: 1px solid #d9d5cf !important;
        background: rgb(255 255 255 / 84%) !important;
        color: #292721 !important;
        transition:
            border-color 260ms var(--daylight-ease),
            box-shadow 320ms var(--daylight-ease),
            background-color 260ms var(--daylight-ease) !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus, .stDateInput input:focus {
        border-color: #9baa91 !important;
        box-shadow: 0 0 0 4px rgb(129 151 122 / 13%), 0 2px 10px rgb(72 68 60 / 5%) !important;
    }
    [data-testid="stMetric"] {
        background: rgb(255 255 255 / 78%);
        border: 1px solid rgb(227 222 215 / 88%);
        border-radius: 18px;
        padding: 16px;
        box-shadow: 0 4px 16px rgb(65 58 51 / 4%);
        transition: transform 360ms var(--daylight-spring), box-shadow 360ms var(--daylight-ease);
        animation: daylightFadeUp 520ms var(--daylight-ease) both;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 22px rgb(65 58 51 / 8%);
    }
    [data-testid="stAlert"] {
        border-radius: 14px;
        animation: daylightFadeUp 360ms var(--daylight-ease) both;
    }
    .encouragement-pill, .milestone-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 11px;
        border: 1px solid rgb(157 128 135 / 18%);
        border-radius: 999px;
        background: linear-gradient(135deg, rgb(250 237 239 / 90%), rgb(239 244 239 / 90%));
        color: #62545a;
        font-size: 13px;
        line-height: 1.4;
        animation: daylightFadeUp 520ms var(--daylight-ease) both;
    }
    .milestone-pill { margin-top: 6px; font-size: 12px; }
    .mac-titlebar {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 9px 14px;
        margin-bottom: 12px;
        border: 1px solid rgb(226 220 216 / 76%);
        border-radius: 16px;
        background: rgb(255 255 255 / 68%);
        box-shadow: 0 2px 9px rgb(65 58 51 / 5%);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
    }
    .mac-dot {
        width: 13px;
        height: 13px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 9px;
        font-weight: 700;
        color: transparent;
        transition: filter 180ms ease;
    }
    .mac-dot:hover { filter: brightness(.9); }
    .mac-dot.mac-red { background: #ff5f57; }
    .mac-dot.mac-yellow { background: #febc2e; }
    .mac-dot.mac-green { background: #28c840; }
    .mac-titlebar:hover .mac-dot { color: rgb(0 0 0 / 45%); }
    .mac-dot.mac-red::before { content: "×"; }
    .mac-dot.mac-yellow::before { content: "−"; }
    .mac-dot.mac-green::before { content: "+"; }
    .mac-titlebar-text {
        margin-left: 6px;
        color: #655b58;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: .01em;
    }
    .mac-openviews {
        margin-left: auto;
        color: #7d8479;
        font-size: 11px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 55%;
    }
    [data-testid="stPopover"] button, [data-testid="stPopover"] {
        border-radius: 10px !important;
        border: 1px solid rgb(226 220 216 / 76%) !important;
        background: rgb(255 255 255 / 76%) !important;
        color: #292721 !important;
        transition: background-color 240ms var(--daylight-ease), box-shadow 240ms var(--daylight-ease);
    }
    [data-testid="stChatMessage"] {
        border: 1px solid rgb(226 220 216 / 52%);
        border-radius: 18px;
        background: rgb(255 255 255 / 52%);
        box-shadow: 0 3px 12px rgb(65 58 51 / 3%);
        animation: daylightFadeUp 420ms var(--daylight-ease) both;
    }
    [data-testid="stChatInput"] textarea {
        border-radius: 16px !important;
        background: rgb(255 255 255 / 86%) !important;
    }
    .stExpander {
        border-color: rgb(226 220 216 / 80%) !important;
        border-radius: 16px !important;
        background: rgb(255 255 255 / 42%);
    }
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: .01ms !important;
            animation-iteration-count: 1 !important;
            scroll-behavior: auto !important;
            transition-duration: .01ms !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ===== 初始化会话状态 =====
if "api_key" not in st.session_state:
    # 演示时可以先把 Key 写进 .streamlit/secrets.toml：
    # DEEPSEEK_API_KEY = "sk-..."
    # 没有 secrets.toml 时，使用左侧边栏手动输入。
    try:
        st.session_state.api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except FileNotFoundError:
        st.session_state.api_key = ""

    st.session_state.editing_key = st.session_state.api_key == ""

if "learning_history" not in st.session_state:
    # 从本地文件恢复历史记录（刷新页面不丢失）
    saved_history = []
    try:
        if HISTORY_FILE.exists():
            loaded = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                saved_history = loaded[-HISTORY_LIMIT:]
    except (OSError, ValueError):
        saved_history = []
    st.session_state.learning_history = saved_history

if "wrong_book" not in st.session_state:
    # 从本地文件恢复错题本
    saved_book = []
    try:
        if WRONGBOOK_FILE.exists():
            loaded = json.loads(WRONGBOOK_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                saved_book = loaded
    except (OSError, ValueError):
        saved_book = []
    st.session_state.wrong_book = saved_book

if "quiz_questions" not in st.session_state:
    st.session_state.quiz_questions = []

if "quiz_topic" not in st.session_state:
    st.session_state.quiz_topic = ""

if "last_sentence" not in st.session_state:
    st.session_state.last_sentence = ""

if "current_view" not in st.session_state:
    st.session_state.current_view = ALL_VIEWS[0]

if "open_views" not in st.session_state:
    st.session_state.open_views = [ALL_VIEWS[0]]

if "wb_flash" not in st.session_state:
    st.session_state.wb_flash = ""

if "chat_messages" not in st.session_state:
    # 从本地文件恢复对话记录（刷新页面不丢失）
    saved_chat = []
    try:
        if CHAT_FILE.exists():
            loaded = json.loads(CHAT_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                saved_chat = loaded[-40:]
    except (OSError, ValueError):
        saved_chat = []
    st.session_state.chat_messages = saved_chat
if "voice_draft" not in st.session_state:
    st.session_state.voice_draft = ""
if "queued_voice_message" not in st.session_state:
    st.session_state.queued_voice_message = ""
if "azure_speech_key" not in st.session_state or "azure_speech_region" not in st.session_state or "dashscope_image_key" not in st.session_state:
    try:
        if "azure_speech_key" not in st.session_state:
            st.session_state.azure_speech_key = st.secrets.get("AZURE_SPEECH_KEY", "")
        if "azure_speech_region" not in st.session_state:
            st.session_state.azure_speech_region = st.secrets.get("AZURE_SPEECH_REGION", "")
        if "dashscope_image_key" not in st.session_state:
            st.session_state.dashscope_image_key = st.secrets.get("DASHSCOPE_API_KEY", "")
    except FileNotFoundError:
        if "azure_speech_key" not in st.session_state:
            st.session_state.azure_speech_key = ""
        if "azure_speech_region" not in st.session_state:
            st.session_state.azure_speech_region = ""
        if "dashscope_image_key" not in st.session_state:
            st.session_state.dashscope_image_key = ""

if "chat_avatar" not in st.session_state:
    st.session_state.chat_avatar = None
if "chat_avatar_upload_hash" not in st.session_state:
    st.session_state.chat_avatar_upload_hash = ""

if "user_profile" not in st.session_state:
    # AI 对用户语言习惯和心情的猜测画像
    st.session_state.user_profile = {"language": "未知", "mood": "平静", "messages_analyzed": 0}


def switch_view(view: str) -> None:
    """切换界面：新界面入栈；打开的界面数达到 3 个时，移除最早打开的那个。"""
    stack = st.session_state.open_views
    if view in stack:
        stack.remove(view)
    stack.append(view)
    if len(stack) >= 3:
        stack.pop(0)
    st.session_state.current_view = view


# ===== 顶部：☰ 菜单 + 苹果标题栏 =====
menu_col, bar_col = st.columns([1, 18], gap="small")

with menu_col:
    with st.popover("☰", use_container_width=True, help="打开菜单，切换界面"):
        st.markdown("**📍 已打开的界面**")
        for view in st.session_state.open_views:
            marker = "👉" if view == st.session_state.current_view else ""
            if st.button(f"{marker} {view}", key=f"pop_open_{view}", use_container_width=True):
                st.session_state.current_view = view
                st.rerun()

        st.markdown("---")
        st.markdown("**🧭 全部功能**")
        for view in ALL_VIEWS:
            if st.button(view, key=f"pop_all_{view}", use_container_width=True):
                switch_view(view)
                st.rerun()

with bar_col:
    open_text = " · ".join(st.session_state.open_views)
    st.markdown(
        f'<div class="mac-titlebar">'
        f'<span class="mac-dot mac-red" title="关闭"></span>'
        f'<span class="mac-dot mac-yellow" title="最小化"></span>'
        f'<span class="mac-dot mac-green" title="全屏"></span>'
        f'<span class="mac-titlebar-text">AI English Friend</span>'
        f'<span class="mac-openviews">已打开：{open_text}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.title("Hi，今天想聊点什么？")
st.caption("🤝 你的 AI 英语朋友 · 温柔的英语学习伙伴，陪你练习、聊天，也认真倾听。")

daily_encouragement = ENCOURAGEMENTS[date.today().toordinal() % len(ENCOURAGEMENTS)]
st.markdown(
    f'<span class="encouragement-pill">☀️ {daily_encouragement}</span>',
    unsafe_allow_html=True,
)

# ===== 侧边栏：API Key 设置 =====
with st.sidebar:
    st.header("⚙️ 设置")

    if st.session_state.api_key and not st.session_state.editing_key:
        st.success("✅ API Key 已设置")
        masked = st.session_state.api_key[:6] + "****" + st.session_state.api_key[-4:]
        st.code(masked, language=None)

        if st.button("🔄 更改 API Key", use_container_width=True):
            st.session_state.editing_key = True
            st.session_state.api_key = ""
            st.rerun()
    else:
        api_key_input = st.text_input(
            "DeepSeek API Key",
            type="password",
            placeholder="sk-...",
            help="在 https://platform.deepseek.com 申请",
        )

        if st.button("✅ 确定", type="primary", use_container_width=True):
            if api_key_input and api_key_input.strip():
                st.session_state.api_key = api_key_input.strip()
                st.session_state.editing_key = False
                st.rerun()
            else:
                st.warning("请先输入 API Key")

    st.markdown("---")
    st.markdown("**关于本项目**")
    st.markdown("一个零基础大一新生，靠 AI 协作做出来的 AI 英语朋友。")


@st.cache_resource
def get_client(api_key: str) -> OpenAI:
    """按 API Key 缓存客户端，避免每次点击按钮都重新创建连接。"""
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=REQUEST_TIMEOUT,
        max_retries=0,
        # 修复：禁用 brotli 压缩，避免 httpx2 与 brotli 版本不兼容的解压报错
        default_headers={"Accept-Encoding": "gzip, deflate"},
    )


def build_prompt(mode: str, text: str) -> str:
    """根据所选学习模式生成对应的教学提示词。"""
    prompt_templates = {
        "✏️ 语法改错": (
            "你是一名耐心的英语老师。请帮我修改下面这句英文的语法错误。\n"
            "要求：1) 先给出修改后的正确句子；2) 再用中文简要说明改了什么、为什么。\n\n"
        ),
        "🌐 中英翻译": (
            "你是一名英语老师。请把下面这句英文翻译成中文，并列出其中的重点单词和短语。\n\n"
        ),
        "📖 逐句讲解": (
            "你是一名英语老师。请用通俗易懂的方式，逐词讲解下面这句英文的意思、语法结构和用法。\n\n"
        ),
        "🔍 查单词": (
            "你是一名英语老师。请详细讲解下面这个单词：\n"
            "要求：1) 音标；2) 词性和中文释义；3) 三个例句（每个例句附中文翻译）；"
            "4) 常用搭配或记忆小技巧。\n\n"
        ),
    }
    subject = "单词" if mode == "🔍 查单词" else "句子"
    return f"{prompt_templates[mode]}{subject}：{text}"


def stream_answer(client: OpenAI, prompt: str) -> Iterator[str]:
    """生成有限时长的文本流；客户端的 read timeout 也会限制无数据等待。"""
    deadline = time.monotonic() + MAX_STREAM_DURATION

    with client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=TEMPERATURE,
        stream=True,
        max_tokens=777,
    ) as stream:
        for chunk in stream:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AI 回复超过 {MAX_STREAM_DURATION} 秒，请稍后重试。"
                )

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            content = delta.content if delta else None

            if isinstance(content, str) and content:
                yield content


def save_history() -> None:
    """把历史记录写入本地 JSON 文件（失败时静默跳过）。"""
    try:
        HISTORY_FILE.write_text(
            json.dumps(st.session_state.learning_history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def add_history(mode: str, text: str, answer: str) -> None:
    """把一次练习写入历史记录（保留最近若干条，并保存到本地）。"""
    st.session_state.learning_history.append({
        "mode": mode,
        "text": text,
        "answer": answer,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    })
    st.session_state.learning_history = st.session_state.learning_history[-HISTORY_LIMIT:]
    save_history()


def save_wrongbook() -> None:
    """把错题本写入本地 JSON 文件（失败时静默跳过）。"""
    try:
        WRONGBOOK_FILE.write_text(
            json.dumps(st.session_state.wrong_book, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def add_wrongbook(question: str, topic: str, user_answer: str) -> None:
    """把做错的题加入错题本（去重，并保存到本地）。"""
    if any(entry.get("question") == question for entry in st.session_state.wrong_book):
        return
    st.session_state.wrong_book.append({
        "question": question,
        "topic": topic,
        "user_answer": user_answer,
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    })
    save_wrongbook()


def run_with_stream(client: OpenAI, prompt: str) -> str:
    """跑一次流式调用并返回完整文本，同时处理常见错误。"""
    st.markdown("### ✨ AI 回复")
    try:
        with st.spinner("🤖 AI 正在思考..."):
            full = st.write_stream(stream_answer(client, prompt))
        if not full.strip():
            st.warning("AI 没有返回内容，请稍后重试。")
            return ""
        return full
    except TimeoutError as error:
        st.error(str(error))
    except APITimeoutError:
        st.error(f"请求超时（{REQUEST_TIMEOUT} 秒），请检查网络后重试。")
    except AuthenticationError:
        st.error("API Key 无效或已过期，请在左侧重新设置。")
    except RateLimitError:
        st.error("API 请求频率过高或额度不足，请稍后重试并检查账户额度。")
    except APIConnectionError:
        st.error("无法连接 DeepSeek 服务，请检查网络连接后重试。")
    except Exception as error:
        st.error(f"分析失败，请稍后重试。\n\n详情：{error}")
    return ""


def stream_chat(client: OpenAI, messages: list) -> Iterator[str]:
    """对话式流式回复（角色扮演用，温度稍高更有性格）。"""
    deadline = time.monotonic() + MAX_STREAM_DURATION

    with client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.9,
        stream=True,
        max_tokens=555,
    ) as stream:
        for chunk in stream:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AI 回复超过 {MAX_STREAM_DURATION} 秒，请稍后重试。"
                )

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            content = delta.content if delta else None

            if isinstance(content, str) and content:
                yield content


def run_chat(client: OpenAI, messages: list) -> str:
    """跑一次对话流式调用并返回完整文本，同时处理常见错误。"""
    try:
        with st.spinner("🤖 AI 正在思考..."):
            full = st.write_stream(stream_chat(client, messages))
        if not full.strip():
            st.warning("AI 没有返回内容，请稍后重试。")
            return ""
        return full
    except TimeoutError as error:
        st.error(str(error))
    except APITimeoutError:
        st.error(f"请求超时（{REQUEST_TIMEOUT} 秒），请检查网络后重试。")
    except AuthenticationError:
        st.error("API Key 无效或已过期，请在左侧重新设置。")
    except RateLimitError:
        st.error("API 请求频率过高或额度不足，请稍后重试并检查账户额度。")
    except APIConnectionError:
        st.error("无法连接 DeepSeek 服务，请检查网络连接后重试。")
    except Exception as error:
        st.error(f"对话失败，请稍后重试。\n\n详情：{error}")
    return ""


def generate_quiz(client: OpenAI, prompt: str) -> bool:
    """生成练习题并写入会话状态；成功返回 True。"""
    full = run_with_stream(client, prompt)
    if not full:
        return False
    questions = [line.strip() for line in full.splitlines() if line.strip()]
    if not questions:
        st.warning("AI 没有生成出题目，请重试。")
        return False
    st.session_state.quiz_questions = questions[:3]
    return True


def render_calendar(year: int, month: int, today: date, start_date: date) -> None:
    """绘制周一开头的月历，标记今天和学习过的日期。"""
    cal = calendar.Calendar(firstweekday=0)

    html = (
        f'<div style="text-align:center;font-weight:bold;font-size:18px;'
        f'margin-bottom:8px;color:#1c2019;">{year} 年 {month} 月</div>'
    )
    html += (
        '<table style="width:100%;text-align:center;'
        'border-collapse:collapse;font-size:16px;">'
    )
    html += "<tr>" + "".join(
        f'<th style="padding:6px;color:#565d50;">{day}</th>'
        for day in "一二三四五六日"
    ) + "</tr>"

    for week in cal.monthdayscalendar(year, month):
        html += "<tr>"

        for day in week:
            if day == 0:
                html += '<td style="padding:8px;"></td>'
                continue

            current_date = date(year, month, day)

            if current_date == today:
                html += (
                    f'<td style="padding:8px;background-color:#4a6040;color:#fff;'
                    f'border-radius:50%;font-weight:700;">{day}</td>'
                )
            elif start_date <= current_date <= today:
                html += (
                    f'<td style="padding:8px;background-color:#e3e8dd;'
                    f'border-radius:50%;color:#1c2019;">{day}</td>'
                )
            else:
                html += f'<td style="padding:8px;color:#1c2019;">{day}</td>'

        html += "</tr>"

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)


# ===== 界面 1：英语助手 =====
def render_tutor() -> None:
    mode = st.selectbox(
        "选择功能",
        ["✏️ 语法改错", "🌐 中英翻译", "📖 逐句讲解", "🔍 查单词"],
    )

    input_label = "输入英文句子或单词" if mode == "🔍 查单词" else "输入英文句子"
    input_placeholder = (
        "例如：abandon（单词）"
        if mode == "🔍 查单词"
        else "例如：I very like AI, because it can help me a lot."
    )

    text = st.text_area(
        input_label,
        placeholder=input_placeholder,
        height=120,
        max_chars=MAX_INPUT_LENGTH,
    )

    if st.button("🚀 开始分析", type="primary", use_container_width=True):
        if not text.strip():
            st.warning("请先输入内容。")
        elif not st.session_state.api_key:
            st.warning("请先在左侧输入并「确定」API Key。")
        else:
            client = get_client(st.session_state.api_key)
            full = run_with_stream(client, build_prompt(mode, text.strip()))

            if full:
                st.markdown(
                    '<span class="milestone-pill">✨ 完成一次练习，今天的你又进步了一点</span>',
                    unsafe_allow_html=True,
                )
                add_history(mode, text.strip(), full)
                if mode == "✏️ 语法改错":
                    st.session_state.last_sentence = text.strip()

    # —— 学习闭环：改错后可以针对这句话出题 ——
    if st.session_state.last_sentence and mode == "✏️ 语法改错":
        st.markdown("---")
        if st.button("🎯 针对刚才的句子出 3 道题", use_container_width=True):
            if not st.session_state.api_key:
                st.warning("请先在左侧输入并「确定」API Key。")
            else:
                client = get_client(st.session_state.api_key)
                sentence = st.session_state.last_sentence
                quiz_prompt = (
                    f"请围绕下面这句英文中出现的语法错误，出 3 道英语填空题，用 ___ 表示需要填的空。\n"
                    f"句子：{sentence}\n"
                    "要求：每道题单独一行，不要题号，不要输出答案和解析，只输出题目本身。"
                )
                if generate_quiz(client, quiz_prompt):
                    st.session_state.quiz_topic = f"这句话的语法：{sentence[:30]}"
                    add_history("🎯 闭环出题", sentence[:60], "")
                    switch_view("📝 做题本 Quiz")
                    st.rerun()


# ===== 界面 2：做题本 =====
def render_quiz() -> None:
    st.subheader("📝 做题本")
    st.caption("让 AI 出题，你来做，AI 帮你批改")

    topic = st.text_input(
        "练习什么？",
        placeholder="例如：abandon / 现在完成时 / 定语从句",
        key="quiz_topic_input",
    )

    if st.button("📝 生成 3 道填空题", use_container_width=True):
        if not topic.strip():
            st.warning("请先输入要练习的单词或语法点。")
        elif not st.session_state.api_key:
            st.warning("请先在左侧输入并「确定」API Key。")
        else:
            client = get_client(st.session_state.api_key)
            quiz_prompt = (
                f"请围绕「{topic.strip()}」出 3 道英语填空题，用 ___ 表示需要填的空。\n"
                "要求：每道题单独一行，不要题号，不要输出答案和解析，只输出题目本身。"
            )
            if generate_quiz(client, quiz_prompt):
                st.session_state.quiz_topic = topic.strip()
                add_history("📝 做题本·出题", topic.strip(), "")
                st.rerun()

    if st.session_state.quiz_questions:
        st.markdown("---")
        st.markdown(f"### 📋 题目（{st.session_state.quiz_topic}）")

        answers = []
        for index, question in enumerate(st.session_state.quiz_questions, 1):
            st.markdown(f"**第 {index} 题** {question}")
            answer = st.text_input("你的答案", key=f"quiz_answer_{index}")
            answers.append(answer)

        if st.button("✅ 提交批改", type="primary", use_container_width=True):
            if not st.session_state.api_key:
                st.warning("请先在左侧输入并「确定」API Key。")
            else:
                client = get_client(st.session_state.api_key)
                grade_prompt = "你是一名英语老师，请批改下面学生的填空题答案。\n\n"
                for index, question in enumerate(st.session_state.quiz_questions, 1):
                    grade_prompt += (
                        f"第 {index} 题：{question}\n"
                        f"学生答案：{answers[index - 1].strip() or '（未作答）'}\n"
                    )
                grade_prompt += (
                    "\n请逐题批改：给出正确答案、判断对错、用一两句话简要讲解。"
                    "最后给一句总体鼓励。"
                    "\n\n最后必须单独用一行输出判定结果，格式：判定：1对 2错 3错"
                )

                full = run_with_stream(client, grade_prompt)
                if full:
                    wrong_count = 0
                    match = re.search(r"判定[:：]\s*(.+)", full)
                    if match:
                        for num_str, verdict in re.findall(r"(\d+)\s*(对|错)", match.group(1)):
                            number = int(num_str)
                            if verdict == "错" and 1 <= number <= len(st.session_state.quiz_questions):
                                add_wrongbook(
                                    st.session_state.quiz_questions[number - 1],
                                    st.session_state.quiz_topic,
                                    answers[number - 1] if number - 1 < len(answers) else "",
                                )
                                wrong_count += 1

                    add_history("📝 做题本·批改", st.session_state.quiz_topic, full)

                    if wrong_count:
                        st.markdown(
                            f'<span class="milestone-pill">❌ {wrong_count} 题做错，已自动加入错题本</span>',
                            unsafe_allow_html=True,
                        )
                        if st.button("❌ 去错题本看看", use_container_width=True):
                            switch_view("❌ 错题本 Wrong Book")
                            st.rerun()
                    else:
                        st.markdown(
                            '<span class="milestone-pill">🎉 全部做对，太强了！</span>',
                            unsafe_allow_html=True,
                        )


# ===== 界面 3：错题本 =====
def render_wrongbook() -> None:
    st.subheader("❌ 错题本")
    st.caption("做错的题都收在这里，专攻弱点")

    if st.session_state.wb_flash:
        st.success(st.session_state.wb_flash)
        st.session_state.wb_flash = ""

    if not st.session_state.wrong_book:
        st.info("错题本是空的，太棒了！继续加油 🎉")
        return

    if st.button("🗑️ 清空错题本", key="clear_wrongbook"):
        st.session_state.wrong_book = []
        save_wrongbook()
        st.rerun()

    st.markdown(f"共 **{len(st.session_state.wrong_book)}** 道错题待复习")

    entries = list(reversed(st.session_state.wrong_book))
    for index, entry in enumerate(entries, 1):
        st.markdown("---")
        st.markdown(f"**{index}. {entry['question']}**")
        st.caption(f"来源：{entry['topic']} · {entry['created_at']}")
        if entry.get("user_answer"):
            st.caption(f"你当时答：{entry['user_answer']}")

        answer = st.text_input("重新作答", key=f"wb_answer_{index}")

        if st.button("✅ 检查", key=f"wb_check_{index}"):
            if not answer.strip():
                st.warning("先写答案再检查")
            elif not st.session_state.api_key:
                st.warning("请先在左侧输入并「确定」API Key。")
            else:
                client = get_client(st.session_state.api_key)
                check_prompt = (
                    f"请判断学生的答案是否正确。\n题目：{entry['question']}\n"
                    f"学生答案：{answer.strip()}\n"
                    "第一行只回答「对」或「错」，第二行起用一两句话讲解。"
                )
                full = run_with_stream(client, check_prompt)
                if full:
                    first_line = ""
                    for line in full.splitlines():
                        if line.strip():
                            first_line = line.strip()
                            break
                    if first_line.startswith(("对", "✅", "正确")):
                        original_index = len(st.session_state.wrong_book) - 1 - (index - 1)
                        del st.session_state.wrong_book[original_index]
                        save_wrongbook()
                        add_history("❌ 错题本·攻克", entry["question"], full)
                        st.session_state.wb_flash = "✅ 答对了！已从错题本移除，成长 +1"
                        st.rerun()


# ===== 界面 4：学习日历 =====
def render_calendar_view() -> None:
    st.subheader("📅 我的学习日历")

    today = date.today()
    cet4_date = st.date_input("📝 四级笔试日期", value=CET4_DATE)
    days_to_cet4 = (cet4_date - today).days

    start_date = st.date_input(
        "📌 你从哪天开始坚持学习？",
        value=date(2026, 10, 12),
    )

    col1, col2 = st.columns(2)

    if today < start_date:
        st.warning("开始日期还没到哦，请选择今天或更早的日期。")
        col1.metric("🔥 已坚持学习", "0 天")
        streak_days = 0
    else:
        streak_days = (today - start_date).days + 1
        col1.metric("🔥 已坚持学习", f"{streak_days} 天")

    if streak_days:
        milestone = next((label for days, label in MILESTONES if streak_days >= days), None)
        if milestone:
            st.markdown(
                f'<span class="milestone-pill">{milestone}</span>',
                unsafe_allow_html=True,
            )

    col2.metric(
        "📝 距离四级考试",
        f"{days_to_cet4} 天" if days_to_cet4 >= 0 else "已结束 🎉",
    )

    st.markdown("---")
    st.markdown("#### 🗓️ 本月日历")
    render_calendar(today.year, today.month, today, start_date)

    st.markdown("---")
    st.markdown("💡 **图例**：绿色圆 = 今天；浅灰绿圆 = 你坚持学习的日子")


# ===== 界面 5：历史记录（成长经历）=====
def render_history() -> None:
    st.subheader("📜 历史记录")
    st.caption("你的每一次练习，AI 都帮你记着")

    total = len(st.session_state.learning_history)
    today_str = time.strftime("%Y-%m-%d")
    today_count = sum(
        1 for item in st.session_state.learning_history
        if str(item.get("created_at", "")).startswith(today_str)
    )
    wrong_count = len(st.session_state.wrong_book)

    c1, c2, c3 = st.columns(3)
    c1.metric("📚 总练习", f"{total} 次")
    c2.metric("☀️ 今日练习", f"{today_count} 次")
    c3.metric("❌ 待复习错题", f"{wrong_count} 道")

    st.markdown("---")

    if not st.session_state.learning_history:
        st.info("还没有学习记录。去「英语助手」或「做题本」练一次吧！")
    else:
        if st.button("🗑️ 清空历史记录", key="clear_history_tab"):
            st.session_state.learning_history = []
            save_history()
            st.rerun()

        history = list(reversed(st.session_state.learning_history))
        total = len(history)
        for index, item in enumerate(history, 1):
            head_col, del_col = st.columns([9, 1])
            with head_col:
                st.markdown(f"**{index}. {item['mode']} · {item['created_at']}**")
            with del_col:
                if st.button("🗑️", key=f"delete_history_{index}", help="删除这条记录"):
                    original_index = total - index
                    del st.session_state.learning_history[original_index]
                    save_history()
                    st.rerun()

            if item.get("text"):
                st.caption(f"原文：{item['text']}")
            if item.get("answer"):
                st.markdown(item["answer"])

            if index < total:
                st.markdown("---")


# ===== 界面 6：学习计划 =====
def render_plan() -> None:
    st.subheader("📋 我的学习计划")
    st.caption("由 GitHub Copilot 协作生成的任务清单")

    plan_path = pathlib.Path(__file__).parent / "plan.html"

    if plan_path.exists():
        with plan_path.open(encoding="utf-8") as plan_file:
            plan_html = plan_file.read()

        st.components.v1.html(plan_html, height=780, scrolling=True)
    else:
        st.warning("找不到 plan.html 文件")


# ===== 用户画像：猜测语言和心情 =====
def analyze_user(text: str) -> dict:
    """根据一条用户消息，猜测语言习惯和当前心情。"""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[A-Za-z]+", text))

    if chinese_chars and not english_words:
        language = "中文为主"
    elif english_words and not chinese_chars:
        language = "英语为主"
    elif chinese_chars and english_words:
        language = "中英混合"
    else:
        language = "英语为主"

    lowered = text.lower()
    negative_words = [
        "累", "烦", "难过", "伤心", "焦虑", "压力", "崩溃", "emo", "sad", "tired",
        "anxious", "stressed", "upset", "depressed", "不想", "哭", "委屈", "迷茫",
    ]
    positive_words = [
        "开心", "高兴", "哈哈", "太棒", "太好了", "happy", "great", "awesome",
        "nice", "love", "喜欢", "冲", "棒",
    ]
    energetic = lowered.count("!") + lowered.count("！") + lowered.count("~") + lowered.count("～")

    if any(word in lowered for word in negative_words):
        mood = "低落/需要支持"
    elif any(word in lowered for word in positive_words) or energetic >= 2:
        mood = "积极/有活力"
    else:
        mood = "平静"

    return {"language": language, "mood": mood}


def update_profile(text: str) -> None:
    """用最新一条消息更新对用户的画像。"""
    result = analyze_user(text)
    profile = st.session_state.user_profile
    profile["messages_analyzed"] += 1
    profile["language"] = result["language"]
    profile["mood"] = result["mood"]


def save_chat() -> None:
    """把对话记录写入本地 JSON 文件（失败时静默跳过）。"""
    try:
        CHAT_FILE.write_text(
            json.dumps(st.session_state.chat_messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def queue_voice_message() -> None:
    """提交语音识别草稿，留给对话流程发送。"""
    voice_text = st.session_state.get("voice_draft", "").strip()
    if voice_text:
        st.session_state.queued_voice_message = voice_text
        st.session_state.voice_draft = ""


def generate_anime_avatar(prompt: str, api_key: str, size: str) -> bytes:
    """通过阿里云百炼万相生成原创动漫头像并下载图片数据。"""
    if not api_key.strip():
        raise ValueError("请先填写阿里云百炼 API Key。")
    if not prompt.strip():
        raise ValueError("请先描述想生成的角色形象。")

    base_url = "https://dashscope.aliyuncs.com/api/v1"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": "wanx-v1",
        "input": {"prompt": prompt.strip()[:800]},
        "parameters": {
            "style": "<anime>",
            "size": size,
            "n": 1,
        },
    }

    response = requests.post(
        f"{base_url}/services/aigc/text2image/image-synthesis",
        headers=headers,
        json=payload,
        timeout=(10, 30),
    )
    if not response.ok:
        try:
            error_data = response.json()
            detail = error_data.get("message") or error_data.get("code") or response.text[:300]
        except ValueError:
            detail = response.text[:300]
        raise RuntimeError(f"万相创建图片任务失败（HTTP {response.status_code}）：{detail}")

    try:
        task_id = response.json()["output"]["task_id"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("万相未返回有效的图片任务编号，请检查 API Key 和模型服务。") from error

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        time.sleep(2)
        task_response = requests.get(
            f"{base_url}/tasks/{task_id}",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=(10, 20),
        )
        if not task_response.ok:
            raise RuntimeError(f"查询万相图片任务失败（HTTP {task_response.status_code}）。")

        try:
            task_data = task_response.json()
            output = task_data["output"]
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError("万相返回的任务状态格式无法识别。") from error

        status = output.get("task_status")
        if status in {"PENDING", "RUNNING"}:
            continue
        if status != "SUCCEEDED":
            detail = output.get("message") or task_data.get("message") or status or "未知错误"
            raise RuntimeError(f"万相图片生成失败：{detail}")

        results = output.get("results", [])
        image_url = next(
            (result.get("url") for result in results if isinstance(result, dict) and result.get("url")),
            None,
        )
        if not image_url:
            raise RuntimeError("万相任务成功，但没有返回图片链接。")

        image_response = requests.get(image_url, timeout=(10, 30))
        image_response.raise_for_status()
        content_type = image_response.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            raise RuntimeError("万相返回的内容不是有效图片。")
        if len(image_response.content) > 12 * 1024 * 1024:
            raise RuntimeError("生成的图片超过 12 MB，无法载入头像。")
        return image_response.content

    raise TimeoutError("图片生成等待超过 3 分钟，请稍后重试。")


def transcribe_with_azure(
    audio_bytes: bytes,
    language: str,
    subscription_key: str,
    region: str,
) -> str:
    """将 WAV 录音发送到 Azure Speech 并返回识别文本。"""
    if speechsdk is None:
        raise RuntimeError(
            "尚未安装 Azure Speech SDK。请运行："
            "pip install azure-cognitiveservices-speech"
        )
    if not subscription_key or not region:
        raise ValueError("请先填写 Azure Speech Key 和资源区域。")

    speech_config = speechsdk.SpeechConfig(
        subscription=subscription_key,
        region=region.strip(),
    )
    speech_config.speech_recognition_language = language
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
        "10000",
    )
    speech_config.set_property(
        speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
        "1500",
    )

    audio_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_file.write(audio_bytes)
            audio_path = pathlib.Path(audio_file.name)

        audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text.strip()
        if result.reason == speechsdk.ResultReason.NoMatch:
            raise ValueError("Azure 没有识别出清晰语音，请检查录音后重试。")
        if result.reason == speechsdk.ResultReason.Canceled:
            details = speechsdk.CancellationDetails(result)
            message = details.error_details or details.reason
            raise RuntimeError(f"Azure 语音识别失败：{message}")
        raise RuntimeError(f"Azure 返回了未处理的识别结果：{result.reason}")
    finally:
        if audio_path is not None:
            try:
                audio_path.unlink()
            except OSError:
                pass


def build_friend_system_prompt(persona_text: str) -> str:
    """根据用户画像，动态生成 AI 朋友的身份与语气指令。"""
    profile = st.session_state.user_profile

    language_guide = {
        "中文为主": "用户主要用中文。请用「中文为主、夹带简单英语短句」的方式回复，温柔地带动用户多说英语。",
        "英语为主": "用户主要用英语。请用英语回复，注意用简单词汇和短句，让用户能听懂。",
        "中英混合": "用户中英混用。请自然地在两种语言之间切换。",
        "未知": "先观察用户语言，跟随用户。",
    }.get(profile["language"], "跟随用户语言。")

    mood_guide = {
        "低落/需要支持": "用户情绪似乎有些低落。请先像心理委员一样温柔倾听和安慰，先照顾情绪、再谈学习，最后轻轻带一点英语。",
        "积极/有活力": "用户状态不错！可以活泼一点，多互动，适当给一点英语小挑战。",
        "平静": "保持自然、轻松、有耐心的语气。",
    }.get(profile["mood"], "保持自然轻松的语气。")

    base = (
        "你是用户的 AI 英语朋友，可以随时切换三种身份：\n"
        "1) 英语老师：教语法、纠正错误、讲解知识；\n"
        "2) 英国朋友：像英国朋友一样自然聊天；\n"
        "3) 心理委员：当用户情绪不好时，温柔倾听、陪伴和支持。\n"
        "你要根据用户当前的状态，自动选择最合适的身份和语气。\n"
    )
    if persona_text:
        base += f"此外，你还有一个扮演设定：{persona_text}\n"

    return base + language_guide + "\n" + mood_guide


@st.cache_resource
def create_default_catgirl_avatar():
    """绘制一个原创的柔和猫猫头像，用作默认 AI 头像。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return "🐱"

    size = 256
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        blend = y / (size - 1)
        color = (
            int(250 - 13 * blend),
            int(235 - 4 * blend),
            int(238 + 7 * blend),
        )
        for x in range(size):
            pixels[x, y] = color

    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 12, 238, 232), fill=(255, 246, 239))
    draw.ellipse((205, 20, 248, 63), fill=(229, 237, 230))

    # Ears sit behind the hair and face.
    draw.polygon([(57, 91), (62, 18), (126, 76)], fill=(108, 78, 82))
    draw.polygon([(133, 74), (195, 18), (204, 96)], fill=(108, 78, 82))
    draw.polygon([(70, 72), (68, 37), (105, 76)], fill=(232, 161, 174))
    draw.polygon([(151, 75), (190, 38), (193, 77)], fill=(232, 161, 174))

    # Neck, shoulders, hair silhouette and face.
    draw.rounded_rectangle((104, 170, 153, 216), radius=18, fill=(246, 194, 177))
    draw.ellipse((35, 177, 221, 316), fill=(152, 177, 159))
    draw.polygon([(86, 196), (128, 226), (170, 196), (194, 256), (62, 256)], fill=(247, 241, 228))
    draw.ellipse((53, 46, 204, 218), fill=(107, 76, 80))
    draw.ellipse((74, 69, 183, 197), fill=(255, 220, 199))

    # Soft bangs frame the face.
    draw.pieslice((67, 45, 193, 152), start=180, end=360, fill=(118, 83, 87))
    draw.polygon([(71, 96), (84, 66), (111, 101), (128, 68), (147, 101), (177, 73), (187, 111), (162, 97), (145, 117), (124, 95), (101, 116)], fill=(118, 83, 87))
    draw.ellipse((65, 103, 83, 165), fill=(118, 83, 87))
    draw.ellipse((174, 101, 193, 164), fill=(118, 83, 87))

    # Eyes, blush and a tiny friendly smile.
    draw.ellipse((91, 123, 108, 146), fill=(91, 135, 120))
    draw.ellipse((148, 123, 165, 146), fill=(91, 135, 120))
    draw.ellipse((96, 126, 101, 132), fill=(255, 255, 255))
    draw.ellipse((153, 126, 158, 132), fill=(255, 255, 255))
    draw.ellipse((76, 148, 101, 160), fill=(244, 157, 157))
    draw.ellipse((155, 148, 180, 160), fill=(244, 157, 157))
    draw.ellipse((125, 146, 131, 151), fill=(194, 123, 119))
    draw.arc((116, 145, 141, 168), start=12, end=168, fill=(159, 91, 101), width=3)

    # Ribbon accents add a soft, original character detail.
    draw.ellipse((51, 91, 76, 116), fill=(227, 173, 185))
    draw.ellipse((179, 91, 204, 116), fill=(227, 173, 185))
    draw.ellipse((59, 99, 68, 108), fill=(250, 231, 220))
    draw.ellipse((187, 99, 196, 108), fill=(250, 231, 220))
    return image


# ===== 界面：AI 对话（主界面）=====
def render_chat() -> None:
    st.subheader("💬 和你的 AI 朋友聊聊")
    st.caption("它会慢慢了解你的语言和心情，越聊越懂你")

    # —— 用户画像展示（个性化可见）——
    profile = st.session_state.user_profile
    if profile["messages_analyzed"] > 0:
        mood_icon = {
            "低落/需要支持": "🌧️",
            "积极/有活力": "☀️",
            "平静": "🌤️",
        }.get(profile["mood"], "🌤️")
        st.markdown(
            f'<span class="encouragement-pill">🧠 我感觉到：{mood_icon} 你主要用{profile["language"]} · 心情{profile["mood"]}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("和我说几句话吧，我会慢慢了解你的语言习惯和心情 😊")

    # —— 角色设置 ——
    with st.expander("🎭 角色设置", expanded=False):
        persona_choice = st.selectbox("选择角色", list(PERSONAS.keys()))

        custom_persona = ""
        if persona_choice == "🎀 自定义角色":
            custom_persona = st.text_area(
                "描述你的角色",
                placeholder="例如：这张图是《海贼王》的路飞，请扮演他和我用英语聊天……",
                height=100,
            )

        uploaded = st.file_uploader(
            "上传角色图片（可选，PNG/JPG，会显示为角色头像）",
            type=["png", "jpg", "jpeg", "webp"],
        )
        if uploaded is not None:
            uploaded_bytes = uploaded.getvalue()
            upload_hash = hashlib.sha256(uploaded_bytes).hexdigest()
            if upload_hash != st.session_state.chat_avatar_upload_hash:
                st.session_state.chat_avatar = uploaded_bytes
                st.session_state.chat_avatar_upload_hash = upload_hash

        st.markdown("#### 🎨 创作原创二次元形象")
        st.caption(
            "使用阿里云百炼通义万相生成动漫头像。每次生成可能产生费用；"
            "提示词和生成请求会发送给阿里云处理。"
        )
        st.text_input(
            "阿里云百炼 API Key",
            type="password",
            key="dashscope_image_key",
            help="使用华北 2（北京）地域的百炼 API Key；也可配置 DASHSCOPE_API_KEY 环境密钥。",
        )
        anime_prompt = st.text_area(
            "描述你的原创角色",
            key="anime_avatar_prompt",
            max_chars=800,
            height=90,
            placeholder="例如：原创二次元英语老师，短发，温暖的绿色眼睛，穿着简洁的学院风针织衫，微笑，柔和自然光，肩部以上头像，干净背景。",
        )
        avatar_size_label = st.selectbox(
            "头像比例",
            options=["正方形", "竖版"],
            key="anime_avatar_size",
        )
        avatar_size = {
            "正方形": "1024*1024",
            "竖版": "720*1280",
        }[avatar_size_label]

        if st.button("✨ 生成二次元形象", key="generate_anime_avatar", use_container_width=True):
            try:
                with st.spinner("万相正在创作你的形象，通常需要几十秒…"):
                    st.session_state.chat_avatar = generate_anime_avatar(
                        prompt=anime_prompt,
                        api_key=st.session_state.dashscope_image_key,
                        size=avatar_size,
                    )
                st.success("形象生成完成，已设置为 AI 聊天头像。")
            except ValueError as error:
                st.warning(str(error))
            except requests.Timeout:
                st.error("连接万相超时，请稍后重试。")
            except requests.RequestException as error:
                st.error(f"连接阿里云万相失败，请检查网络后重试。详情：{error}")
            except Exception as error:
                st.error(f"生成形象失败：{error}")

        if st.session_state.chat_avatar:
            col_a, col_b = st.columns([1, 4])
            with col_a:
                st.image(st.session_state.chat_avatar, width=72)
            with col_b:
                if st.button("移除头像", key="remove_chat_avatar"):
                    st.session_state.chat_avatar = None
                    st.rerun()

        persona_text = PERSONAS[persona_choice] or custom_persona.strip()

    def chat_avatar(role: str):
        """返回聊天头像：AI 用上传的图片，用户用固定 emoji。"""
        if role == "assistant" and st.session_state.chat_avatar:
            try:
                from PIL import Image
                import io

                return Image.open(io.BytesIO(st.session_state.chat_avatar))
            except Exception:
                return create_default_catgirl_avatar()
        return create_default_catgirl_avatar() if role == "assistant" else "🧑‍🎓"

    # —— 聊天记录 ——
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"], avatar=chat_avatar(message["role"])):
            st.markdown(message["content"])

    if st.session_state.chat_messages:
        if st.button("🗑️ 清空对话", key="clear_chat"):
            st.session_state.chat_messages = []
            st.session_state.user_profile = {"language": "未知", "mood": "平静", "messages_analyzed": 0}
            save_chat()
            st.rerun()

    # —— 语音输入与文字输入 ——
    with st.expander("🎙️ 语音输入", expanded=False):
        st.text_input(
            "Azure Speech Key",
            type="password",
            key="azure_speech_key",
            help="可在 Azure Portal 的 Speech 资源中查看。也可在 secrets.toml 配置 AZURE_SPEECH_KEY。",
        )
        st.text_input(
            "Azure 资源区域（Region）",
            key="azure_speech_region",
            placeholder="例如 eastasia",
            help="填写 Azure Speech 资源概览中的区域标识，例如 eastasia。",
        )
        voice_language_label = st.selectbox(
            "识别语言",
            options=["英语（美国）", "中文（普通话）"],
            key="chat_voice_language",
        )
        voice_language = {
            "英语（美国）": "en-US",
            "中文（普通话）": "zh-CN",
        }[voice_language_label]
        st.caption(
            "录音会通过网络发送给 Microsoft Azure Speech 进行识别；"
            "请先配置 Azure Speech Key 和区域，并允许浏览器使用麦克风。"
        )
        if speechsdk is None:
            st.info("需要安装 Azure Speech SDK：pip install azure-cognitiveservices-speech")
        if mic_recorder is None:
            st.info("需要安装录音组件：pip install streamlit-mic-recorder")
        audio = None
        if speechsdk is not None and mic_recorder is not None:
            audio = mic_recorder(
                start_prompt="🎙️ 开始录音",
                stop_prompt="⏹️ 停止录音",
                just_once=True,
                use_container_width=True,
                format="wav",
                key="chat_voice_recorder",
            )
        if audio:
            try:
                with st.spinner("正在识别语音…"):
                    st.session_state.voice_draft = transcribe_with_azure(
                        audio_bytes=audio["bytes"],
                        language=voice_language,
                        subscription_key=st.session_state.azure_speech_key,
                        region=st.session_state.azure_speech_region,
                    )
                if st.session_state.voice_draft:
                    st.success("语音识别完成，可以编辑后发送。")
            except ValueError as error:
                st.warning(str(error))
            except Exception as error:
                st.error(f"Azure 语音识别暂时不可用：{error}")

        with st.form("voice_message_form", clear_on_submit=False):
            st.text_area(
                "识别结果（可编辑）",
                key="voice_draft",
                height=80,
                placeholder="录音识别出的内容会显示在这里，也可以手动修改。",
                max_chars=MAX_INPUT_LENGTH,
            )
            st.form_submit_button(
                "发送语音消息",
                on_click=queue_voice_message,
                use_container_width=True,
            )

    user_input = st.chat_input("和你的 AI 朋友说点什么吧…")
    if not user_input:
        user_input = st.session_state.queued_voice_message

    if user_input:
        if not st.session_state.api_key:
            st.warning("请先在左侧输入并「确定」API Key。")
        elif not persona_text:
            st.warning("请先在「🎭 角色设置」里填写自定义角色描述。")
        else:
            if user_input == st.session_state.queued_voice_message:
                st.session_state.queued_voice_message = ""
            update_profile(user_input)
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user", avatar=chat_avatar("user")):
                st.markdown(user_input)

            client = get_client(st.session_state.api_key)
            system_prompt = build_friend_system_prompt(persona_text)
            messages = [{"role": "system", "content": system_prompt}] + st.session_state.chat_messages[-7:]

            with st.chat_message("assistant", avatar=chat_avatar("assistant")):
                full = run_chat(client, messages)

            if full:
                st.session_state.chat_messages.append({"role": "assistant", "content": full})
                save_chat()
                add_history("💬 AI 对话", user_input[:60], full[:200] + ("…" if len(full) > 200 else ""))


# ===== 渲染当前界面 =====
current_view = st.session_state.current_view
if current_view == "✏️ 英语助手 Tutor":
    render_tutor()
elif current_view == "💬 AI 对话 Chat":
    render_chat()
elif current_view == "📝 做题本 Quiz":
    render_quiz()
elif current_view == "❌ 错题本 Wrong Book":
    render_wrongbook()
elif current_view == "📅 学习日历 Calendar":
    render_calendar_view()
elif current_view == "📜 历史记录 History":
    render_history()
else:
    render_plan()
