"""
bot_features — ALEV v2 Telegram Özellik Modülleri

Her modül bağımsızdır. bot.py'de ihtiyaç duyduklarınızı import edin.

Hızlı entegrasyon (bot.py main() içine ekle):

    # ── Quiz ──────────────────────────────────
    from bot_features.quiz import QuizManager, register_quiz_handlers
    quiz_mgr = QuizManager(cfg, engine)
    register_quiz_handlers(app, quiz_mgr, ADMIN_IDS)

    # ── Butonlu görev listesi ─────────────────
    from bot_features.task_buttons import TaskButtonManager, register_task_button_handlers
    task_btn_mgr = TaskButtonManager(cfg, engine, ADMIN_IDS)
    register_task_button_handlers(app, task_btn_mgr)
    # NOT: bot.py'deki CommandHandler("tasks", cmd_tasks) satırını kaldırın

    # ── Inline mod ───────────────────────────
    from bot_features.inline_mode import InlineModeManager, register_inline_handlers
    inline_mgr = InlineModeManager(cfg, engine)
    register_inline_handlers(app, inline_mgr)

    # ── Konum görevleri ──────────────────────
    from bot_features.location_tasks import LocationTaskManager, register_location_handlers
    loc_mgr = LocationTaskManager(cfg, engine, ADMIN_IDS)
    register_location_handlers(app, loc_mgr)

    # ── Mini App ─────────────────────────────
    from bot_features.mini_app import MiniAppManager, register_mini_app_handlers
    mini_app_mgr = MiniAppManager(web_app_url=os.getenv("ALEV_WEB_APP_URL",""))
    register_mini_app_handlers(app, mini_app_mgr)
    await mini_app_mgr.setup_menu_button(app.bot)  # Ana menü butonu

    # ── Kanal senkronizasyonu ────────────────
    from bot_features.channel_sync import ChannelSync
    channel_sync = ChannelSync(cfg, engine, app.bot)
    # İlk kurulumda:
    # await channel_sync.init_channel_post()
    # await channel_sync.pin_score_message()
    # Sonra her skor değişiminde:
    # await channel_sync.update_channel_score()

    # ── Zamanlanmış mesajlar ─────────────────
    from bot_features.scheduler import ALEVScheduler
    group_ids = [g.chat_id for g in cfg.groups.active_groups() if g.chat_id]
    scheduler = ALEVScheduler(cfg, engine, app, group_ids, ADMIN_IDS)
    scheduler.start()
    # app.post_shutdown'a scheduler.stop ekle

Ek gereksinimler (pip install):
    apscheduler   — Zamanlanmış mesajlar için
    (Diğerleri python-telegram-bot ile birlikte gelir)
"""
