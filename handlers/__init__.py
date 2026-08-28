from .start import router as start_router
from .tasks import router as tasks_router
from .products import router as products_router
from .marketplace import router as marketplace_router
from .ai_chat import router as ai_chat_router
from .wallet import router as wallet_router
from .admin import router as admin_router
from .admin_v2 import router as admin_v2_router
from .profile import router as profile_router
from .referral import router as referral_router
from .org import router as org_router
from .help import router as help_router

all_routers = [
    start_router,
    tasks_router,
    products_router,
    marketplace_router,
    ai_chat_router,
    wallet_router,
    admin_router,
    admin_v2_router,
    profile_router,
    referral_router,
    org_router,
    help_router,
]
