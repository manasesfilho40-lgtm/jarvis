import sys, os, json, tempfile, pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from actions.leads_manager import (
    init_db, save_db, import_scraped_leads, get_new_leads, get_used_leads,
    mark_as_used, get_crm_stats, search_leads, delete_lead, clear_leads,
    normalize_phone, manage_crm, get_db_lock
)


@pytest.fixture(autouse=True)
def isolate_db():
    orig_db_path = Path("actions/leads_manager.py").resolve().parent.parent / "config" / "leads_db.json"
    with tempfile.TemporaryDirectory() as tmp:
        test_db = Path(tmp) / "leads_db.json"
        test_db.write_text(json.dumps({"new": [], "used": []}), encoding="utf-8")

        with patch("actions.leads_manager._db_path", return_value=test_db):
            yield


class TestInitDB:
    def test_init_creates_empty_db(self, isolate_db):
        db = init_db()
        assert db == {"new": [], "used": []}

    def test_init_loads_existing(self, isolate_db):
        init_db()
        db = init_db()
        assert "new" in db
        assert "used" in db

    def test_init_fixes_missing_keys(self, isolate_db):
        from actions.leads_manager import _db_path
        p = _db_path()
        p.write_text(json.dumps({"new": []}), encoding="utf-8")
        db = init_db()
        assert "used" in db
        assert db["used"] == []


class TestImportScraped:
    def test_import_adds_leads(self, isolate_db):
        scraped = [
            {"title": "Loja A", "phoneUnformatted": "+5511999999999", "categoryName": "Clothing"},
            {"title": "Loja B", "phoneUnformatted": "+5511888888888"},
        ]
        added, dupes = import_scraped_leads(scraped)
        assert added == 2
        assert dupes == 0
        assert len(get_new_leads()) == 2

    def test_import_skips_duplicates(self, isolate_db):
        scraped = [
            {"title": "Loja A", "phoneUnformatted": "+5511999999999"},
        ]
        import_scraped_leads(scraped)
        added, dupes = import_scraped_leads(scraped)
        assert added == 0
        assert dupes == 1

    def test_import_skips_no_phone(self, isolate_db):
        scraped = [{"title": "Sem Telefone"}]
        added, dupes = import_scraped_leads(scraped)
        assert added == 0
        assert dupes == 0

    def test_import_handles_old_format(self, isolate_db):
        scraped = [{"name": "Loja Antiga", "phone": "+5511777777777"}]
        added, dupes = import_scraped_leads(scraped)
        assert added == 1
        leads = get_new_leads()
        assert leads[0]["title"] == "Loja Antiga"

    def test_import_multiple_fields(self, isolate_db):
        scraped = [{"title": "Loja", "address": "Rua X", "website": "loja.com", "categoryName": "Store"}]
        added, dupes = import_scraped_leads(scraped)
        assert added == 0  # no phone

    def test_import_normalizes_phone(self, isolate_db):
        scraped = [{"title": "Loja", "phoneUnformatted": "55 11 99999-9999"}]
        added, dupes = import_scraped_leads(scraped)
        db = init_db()
        assert db["new"][0]["phoneUnformatted"] == "55 11 99999-9999"


class TestMarkAsUsed:
    def test_mark_moves_lead(self, isolate_db):
        scraped = [{"title": "Loja A", "phoneUnformatted": "+5511999999999"}]
        import_scraped_leads(scraped)
        assert len(get_new_leads()) == 1
        assert len(get_used_leads()) == 0

        result = mark_as_used("+5511999999999")
        assert result is True
        assert len(get_new_leads()) == 0
        assert len(get_used_leads()) == 1

    def test_mark_nonexistent_phone(self, isolate_db):
        result = mark_as_used("+5511000000000")
        assert result is False

    def test_mark_empty_phone(self, isolate_db):
        assert mark_as_used("") is False
        assert mark_as_used(None) is False


class TestSearchAndStats:
    def test_crm_stats_empty(self, isolate_db):
        stats = get_crm_stats()
        assert stats["new_count"] == 0
        assert stats["used_count"] == 0
        assert stats["total_count"] == 0

    def test_crm_stats_with_data(self, isolate_db):
        scraped = [
            {"title": "A", "phoneUnformatted": "111"},
            {"title": "B", "phoneUnformatted": "222"},
        ]
        import_scraped_leads(scraped)
        mark_as_used("111")
        stats = get_crm_stats()
        assert stats["new_count"] == 1
        assert stats["used_count"] == 1
        assert stats["total_count"] == 2

    def test_search_by_name(self, isolate_db):
        scraped = [
            {"title": "Streetwear Brasil", "phoneUnformatted": "111"},
            {"title": "Moda Casual", "phoneUnformatted": "222"},
        ]
        import_scraped_leads(scraped)
        results = search_leads(query="Streetwear", status="all")
        assert len(results) == 1
        assert results[0]["title"] == "Streetwear Brasil"

    def test_search_by_phone(self, isolate_db):
        scraped = [{"title": "Loja", "phoneUnformatted": "+5511999999999"}]
        import_scraped_leads(scraped)
        results = search_leads(query="99999", status="all")
        assert len(results) >= 1

    def test_search_by_category(self, isolate_db):
        scraped = [{"title": "Loja", "phoneUnformatted": "111", "categoryName": "Streetwear"}]
        import_scraped_leads(scraped)
        results = search_leads(query="Streetwear", status="all")
        assert len(results) >= 1

    def test_search_new_only(self, isolate_db):
        scraped = [{"title": "Novo Lead", "phoneUnformatted": "111"}]
        import_scraped_leads(scraped)
        mark_as_used("111")
        results = search_leads(query="Novo", status="new")
        assert len(results) == 0

    def test_search_limit(self, isolate_db):
        scraped = [{"title": f"Loja {i}", "phoneUnformatted": f"{i}"} for i in range(10)]
        import_scraped_leads(scraped)
        results = search_leads(query="", status="all", limit=3)
        assert len(results) == 3


class TestDeleteAndClear:
    def test_delete_lead(self, isolate_db):
        scraped = [{"title": "Loja", "phoneUnformatted": "+5511999999999"}]
        import_scraped_leads(scraped)
        assert delete_lead("+5511999999999") is True
        assert len(get_new_leads()) == 0

    def test_delete_nonexistent(self, isolate_db):
        assert delete_lead("+5511000000000") is False

    def test_clear_new(self, isolate_db):
        scraped = [{"title": "A", "phoneUnformatted": "111"}, {"title": "B", "phoneUnformatted": "222"}]
        import_scraped_leads(scraped)
        assert clear_leads("new") == 2
        assert len(get_new_leads()) == 0

    def test_clear_all(self, isolate_db):
        scraped = [{"title": "A", "phoneUnformatted": "111"}]
        import_scraped_leads(scraped)
        mark_as_used("111")
        assert clear_leads("all") == 1


class TestNormalizePhone:
    def test_normalize_removes_non_digits(self):
        assert normalize_phone("+55 (11) 99999-9999") == "5511999999999"

    def test_normalize_empty(self):
        assert normalize_phone("") == ""
        assert normalize_phone(None) == ""

    def test_normalize_clean(self):
        assert normalize_phone("5511999998888") == "5511999998888"


class TestManageCRM:
    def test_stats_action(self, isolate_db):
        result = manage_crm({"action": "stats"})
        assert "Leads novos" in result
        assert "0" in result

    def test_list_action_empty(self, isolate_db):
        result = manage_crm({"action": "list"})
        assert "Nenhum" in result

    def test_list_with_leads(self, isolate_db):
        import_scraped_leads([{"title": "Teste", "phoneUnformatted": "111"}])
        result = manage_crm({"action": "list"})
        assert "Teste" in result
        assert "111" in result

    def test_get_action(self, isolate_db):
        import_scraped_leads([{"title": "Minha Loja", "phoneUnformatted": "111"}])
        result = manage_crm({"action": "get", "query": "Minha"})
        assert "Minha Loja" in result
        assert "111" in result

    def test_get_not_found(self, isolate_db):
        result = manage_crm({"action": "get", "query": "naoexiste"})
        assert "Nenhum" in result

    def test_mark_used_action(self, isolate_db):
        import_scraped_leads([{"title": "Loja", "phoneUnformatted": "111"}])
        result = manage_crm({"action": "mark_used", "phone": "111"})
        assert "marcado" in result.lower()

    def test_mark_used_not_found(self, isolate_db):
        result = manage_crm({"action": "mark_used", "phone": "000"})
        assert "não encontrado" in result.lower()

    def test_delete_action(self, isolate_db):
        import_scraped_leads([{"title": "Loja", "phoneUnformatted": "111"}])
        result = manage_crm({"action": "delete", "phone": "111"})
        assert "removido" in result.lower()

    def test_clear_action(self, isolate_db):
        import_scraped_leads([{"title": "Loja", "phoneUnformatted": "111"}])
        result = manage_crm({"action": "clear", "status": "new"})
        assert "1 leads" in result

    def test_unknown_action(self, isolate_db):
        result = manage_crm({"action": "invalid"})
        assert "ERROR" in result

    def test_get_missing_query(self, isolate_db):
        result = manage_crm({"action": "get"})
        assert "ERROR" in result

    def test_mark_used_missing_phone(self, isolate_db):
        result = manage_crm({"action": "mark_used"})
        assert "ERROR" in result

    def test_delete_missing_phone(self, isolate_db):
        result = manage_crm({"action": "delete"})
        assert "ERROR" in result
