# Bu test dosyasi, db session davranisini dogrular.

from app.db.session import engine


def test_engine_uses_pool_pre_ping_for_stale_connection_recovery() -> None:
    assert engine.pool._pre_ping is True
