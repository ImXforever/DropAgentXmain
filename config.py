import os

from dotenv import load_dotenv
from dataclasses import dataclass, field

load_dotenv()

# Semantic version of the project. Bumped on each release so the bot, web UI and
# health checks can report which build is running.
VERSION = "0.6.0"  # «سخت‌شده» — ۹ فیکس امنیتی + فیلتر ضدکلاهبرداری
APP_NAME = "DropAgentX / Hermes Marketplace Bot"


def _int_list(env_key: str) -> list[int]:
    return [int(x) for x in os.getenv(env_key, "").split(",") if x.strip()]


@dataclass
class Config:
    # v3.3.3 fix: نسخه/نام به‌صورت اتریبیوت کلاس هم در دسترس باشد —
    # admin_v2 (/system) و mcp_bridge روی آبجکت می‌خواندند → AttributeError
    VERSION: str = VERSION
    APP_NAME: str = APP_NAME
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # --- Hermes engine (see hermes_engine.py) ---
    # auto: prefer local `hermes` CLI, then HERMES_GATEWAY_URL, then plain API
    HERMES_MODE: str = os.getenv("HERMES_MODE", "auto")
    HERMES_CMD: str = os.getenv("HERMES_CMD", "hermes")
    HERMES_PROFILE: str = os.getenv("HERMES_PROFILE", "")
    HERMES_GATEWAY_URL: str = os.getenv("HERMES_GATEWAY_URL", "")
    HERMES_GATEWAY_TOKEN: str = os.getenv("HERMES_GATEWAY_TOKEN", "")
    HERMES_TIMEOUT: int = int(os.getenv("HERMES_TIMEOUT", "180"))
    HERMES_MAX_CONCURRENT: int = int(os.getenv("HERMES_MAX_CONCURRENT", "2"))

    # --- Fallback API backend (accepts OPENAI_* aliases too) ---
    AI_API_KEY: str = os.getenv("AI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    AI_BASE_URL: str = (
        os.getenv("AI_BASE_URL", "")
        or os.getenv("OPENAI_BASE_URL", "")
        or "https://openrouter.ai/api/v1"
    )
    AI_MODEL: str = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

    ADMIN_IDS: list[int] = field(default_factory=lambda: _int_list("ADMIN_IDS"))

    DB_PATH: str = os.getenv("DB_PATH", "data/marketplace.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

    # --- capacity (v2.0 · هدف: 8000+ کاربر روی سقف 500MB) ---
    # کانال/گروپ ذخیره فایل‌ها: اگر ست شود، فایل محصولات با file_id تلگرام نگه‌داری
    # می‌شود و صفر بایت روی Volume می‌رود (۰ = خاموش، رفتار قدیمی دیسک).
    FILE_STORAGE_CHANNEL_ID: int = int(os.getenv("FILE_STORAGE_CHANNEL_ID", "0") or 0)
    CHAT_KEEP_ROWS: int = int(os.getenv("CHAT_KEEP_ROWS", "25"))       # سقف پیام چت per user (قبلاً 60)
    CHAT_USER_CAP: int = int(os.getenv("CHAT_USER_CAP", "2000"))       # سقف کاراکتر پیام کاربر (قبلاً 6000)
    CHAT_ASSISTANT_CAP: int = int(os.getenv("CHAT_ASSISTANT_CAP", "1500"))  # سقف پاسخ assistant
    CHAT_FTS_USERS_ONLY: bool = os.getenv("CHAT_FTS_USERS_ONLY", "1") == "1"  # FTS فقط پیام کاربر
    DB_WARN_MB: int = int(os.getenv("DB_WARN_MB", "400"))              # هشدار ادمین در 80٪ سقف
    TX_ARCHIVE_DAYS: int = int(os.getenv("TX_ARCHIVE_DAYS", "0"))      # آرشیو txهای قدیمی‌تر (۰=خاموش)
    VACUUM_DAY: int = int(os.getenv("VACUUM_DAY", "1"))                # روز ماه برای VACUUM خودکار
    SWEEP_DORMANT_DAYS: int = int(os.getenv("SWEEP_DORMANT_DAYS", "45"))  # پاک‌سازی چت کاربران راکد

    # --- لانچ v3.4.0 — رشد و پشتیبانی ---
    SUPPORT_CONTACT: str = os.getenv("SUPPORT_CONTACT", "@ImXforevr")   # آیدی پشتیبان/مالک
    LAUNCH_TARGET: int = int(os.getenv("LAUNCH_TARGET", "1000"))        # ظرفیت اعضای زودهنگام
    LAUNCH_BONUS_CREDITS: int = int(os.getenv("LAUNCH_BONUS_CREDITS", "100"))  # بونوس عضویت زودهنگام
    DAILY_BONUS_BASE: int = int(os.getenv("DAILY_BONUS_BASE", "15"))   # بونوس روزانه روز اول
    DAILY_BONUS_STEP: int = int(os.getenv("DAILY_BONUS_STEP", "5"))    # رشد هر روز استریک
    DAILY_BONUS_CAP: int = int(os.getenv("DAILY_BONUS_CAP", "50"))     # سقف بونوس روزانه

    # --- v3.3.3: نگهداری لاگ ساختاریافته (ضد رشد بی‌سقف app_logs) ---
    APP_LOG_RETENTION_DAYS: int = int(os.getenv("APP_LOG_RETENTION_DAYS", "14"))
    APP_LOG_MAX_ROWS: int = int(os.getenv("APP_LOG_MAX_ROWS", "50000"))

    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.10"))
    CREDITS_PER_FOLLOW: int = int(os.getenv("CREDITS_PER_FOLLOW", "5"))
    WELCOME_CREDITS: int = int(os.getenv("WELCOME_CREDITS", "50"))

    # --- USDT treasury (internal wallet) ---
    # 1000 credits == 1 USDT
    CREDITS_PER_USDT: int = int(os.getenv("CREDITS_PER_USDT", "1000"))
    DEPOSIT_MIN_USDT: float = float(os.getenv("DEPOSIT_MIN_USDT", "1"))
    WITHDRAW_MIN_USDT: float = float(os.getenv("WITHDRAW_MIN_USDT", "5"))
    # network fee (USDT) deducted from the withdrawal amount, per network key
    WITHDRAW_FEES: dict = field(default_factory=lambda: {
        "ton": float(os.getenv("FEE_TON", "0.5")),
        "bsc": float(os.getenv("FEE_BSC", "1")),
        "sol": float(os.getenv("FEE_SOL", "0.5")),
        "trx": float(os.getenv("FEE_TRX", "1")),
    })
    DEPOSIT_WALLETS: dict = field(default_factory=lambda: {
        "ton": os.getenv("WALLET_TON", ""),
        "bsc": os.getenv("WALLET_BSC", ""),   # BSC / BASE (EVM)
        "sol": os.getenv("WALLET_SOL", ""),
        "trx": os.getenv("WALLET_TRX", ""),
    })

    # --- Referral program ---
    # Two-sided bonus (Dropbox) paid ONLY after referee's first real action (Coinbase gate)
    REF_INVITE_BONUS_REFERRER: int = int(os.getenv("REF_INVITE_BONUS_REFERRER", "75"))
    REF_BONUS_REFEREE: int = int(os.getenv("REF_BONUS_REFEREE", "50"))
    # Instant mystery-box for referrer on each signup (Robinhood) — kept small vs farming
    REF_MYSTERY_MIN: int = int(os.getenv("REF_MYSTERY_MIN", "5"))
    REF_MYSTERY_MAX: int = int(os.getenv("REF_MYSTERY_MAX", "20"))
    # Lifetime share of platform commission on referred users' sales (Binance)
    REF_COMMISSION_SHARE: float = float(os.getenv("REF_COMMISSION_SHARE", "0.20"))
    # Milestone ladder (Tesla): qualified-referrals -> bonus credits
    REF_MILESTONES: dict = field(default_factory=lambda: {
        5: int(os.getenv("REF_MS_5", "250")),
        25: int(os.getenv("REF_MS_25", "1500")),
        100: int(os.getenv("REF_MS_100", "8000")),
    })

    # --- Fractal autonomy org ranks ---
    # associate -> soldier: automatic on first sale (king of own shop)
    # soldier -> capo: automatic at CAPO_MIN_REFS qualified referrals
    # underboss: appointed by godfather (ADMIN_IDS), domain = category
    CAPO_MIN_REFS: int = int(os.getenv("CAPO_MIN_REFS", "10"))
    CAPO_OVERRIDE_PCT: float = float(os.getenv("CAPO_OVERRIDE_PCT", "0.05"))

    # ======================================================================
    # v2.0.0 — Multi-faceted memory
    # ======================================================================
    MEMORY2_ENABLED: bool = os.getenv("MEMORY2_ENABLED", "1") == "1"
    # Relative weight of each memory facet when building the augmented context.
    MEMORY_FACET_W: dict = field(default_factory=lambda: {
        "identity": float(os.getenv("MEM_FACET_IDENTITY", "1.5")),
        "factual": float(os.getenv("MEM_FACET_FACTUAL", "1.0")),
        "preference": float(os.getenv("MEM_FACET_PREFERENCE", "1.3")),
        "behavioral": float(os.getenv("MEM_FACET_BEHAVIORAL", "1.2")),
        "emotional": float(os.getenv("MEM_FACET_EMOTIONAL", "1.1")),
        "engagement": float(os.getenv("MEM_FACET_ENGAGEMENT", "0.9")),
        "risk": float(os.getenv("MEM_FACET_RISK", "1.0")),
    })
    # How long (days) a low-importance memory survives before being pruned.
    MEMORY_EVICTION_DAYS: int = int(os.getenv("MEMORY_EVICTION_DAYS", "90"))

    # ======================================================================
    # v2.0.0 — Image generation (Gemini "Google brand" + OpenAI-compatible)
    # ======================================================================
    # gemini  -> Google Gemini via REST (free-tier GEMINI_API_KEY)
    # openai  -> any OpenAI-compatible /images/generations endpoint
    # auto    -> try gemini, fall back to openai
    IMAGE_GEN_BACKEND: str = os.getenv("IMAGE_GEN_BACKEND", "auto")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    GEMINI_IMAGE_MODEL: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")

    # ======================================================================
    # v2.0.0 — Identity reinforcement-learning agent
    # ======================================================================
    IDENTITY_RL_ENABLED: bool = os.getenv("IDENTITY_RL_ENABLED", "1") == "1"
    RL_EXPLORE: float = float(os.getenv("RL_EXPLORE", "0.20"))
    RL_LEARN_RATE: float = float(os.getenv("RL_LEARN_RATE", "0.15"))
    RL_GAMMA: float = float(os.getenv("RL_GAMMA", "0.90"))
    RL_SESSION_TTL: int = int(os.getenv("RL_SESSION_TTL", "7200"))

    # ======================================================================
    # v2.0.0 — Observability (structured logs + persisted audit trail)
    # ======================================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_TO_DB: bool = os.getenv("LOG_TO_DB", "1") == "1"
    LOG_DB_KEEP_DAYS: int = int(os.getenv("LOG_DB_KEEP_DAYS", "7"))
    LOG_JSON_ENABLED: bool = os.getenv("LOG_JSON_ENABLED", "1") == "1"

    # ======================================================================
    # v3.0.0 — LLM Router (9router integration)
    # ======================================================================
    # When set, all AI calls are routed through {ROUTER_BASE_URL}/v1/chat/completions
    # (an OpenAI-compatible router such as 9router) BEFORE falling back to the
    # direct provider. This buys 3-tier fallback, quota tracking and token saving.
    ROUTER_BASE_URL: str = os.getenv("ROUTER_BASE_URL", "").strip()
    ROUTER_API_KEY: str = os.getenv("ROUTER_API_KEY", "").strip()
    ROUTER_TIMEOUT: int = int(os.getenv("ROUTER_TIMEOUT", "120"))
    # If we route through 9router, we must NOT double-spend by also hitting the
    # direct provider as the primary. The direct provider is only the fallback.
    ROUTER_FALLBACK_TO_DIRECT: bool = os.getenv("ROUTER_FALLBACK_TO_DIRECT", "1") == "1"

    # ======================================================================
    # v3.0.0 — Agent discovery / A2A (from radius)
    # ======================================================================
    AGENT_NAME: str = os.getenv("AGENT_NAME", "DropAgentX")
    AGENT_BASE_URL: str = os.getenv("AGENT_BASE_URL", "").strip()
    # ERC-8004 / registry publishing toggle (opt-in, off by default)
    A2A_ENABLED: bool = os.getenv("A2A_ENABLED", "1") == "1"
    A2A_PORT: int = int(os.getenv("A2A_PORT", "9000") or 9000)
    A2A_TOKEN: str = os.getenv("A2A_TOKEN", "").strip()


config = Config()
