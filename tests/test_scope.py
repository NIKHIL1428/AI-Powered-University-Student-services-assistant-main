from app.precedence.scope import batch_in_scope, programme_in_scope


def test_programme_scope():
    assert programme_in_scope("B.Tech CSE", "ALL")
    assert programme_in_scope("B.Tech CSE", "B.Tech")
    assert programme_in_scope("B.Tech CSE", "BTech")
    assert programme_in_scope("B.Tech IT", "B.Tech CSE;B.Tech IT")
    assert not programme_in_scope("B.Tech IT", "B.Tech CSE")
    assert not programme_in_scope("M.Tech CSE", "B.Tech")


def test_batch_scope():
    assert batch_in_scope(2023, "ALL")
    assert batch_in_scope(2023, "2023")
    assert batch_in_scope(2024, "2023+")
    assert not batch_in_scope(2022, "2023+")
    assert batch_in_scope(2022, "2021-2023")
    assert not batch_in_scope(2024, "2021-2023")
    assert batch_in_scope(2020, "2019;2020")
