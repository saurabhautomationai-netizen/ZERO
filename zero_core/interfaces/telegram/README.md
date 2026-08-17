# Telegram interface — not implemented yet

Planned: a thin `python-telegram-bot` handler that takes an incoming
message, calls `zero_core.bootstrap.build_orchestrator().run(text)`, and
replies. This interface should contain NO business logic — if you find
yourself writing routing or agent logic here, it belongs in zero_core
instead, so Voice/Web interfaces (see ../web) can reuse it.
