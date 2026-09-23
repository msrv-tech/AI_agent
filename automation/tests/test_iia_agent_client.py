from pathlib import Path

from automation.ops.iia_agent_client import api_dialog_type, evaluate_recognition, infer_task_success
from automation.quality_gate_matrix import DEFAULT_SUPPLIER_INVOICE, agent_api_url_from_web, recognition_files, run_agent_api_recognition


def test_dialog_type_mapping():
    assert api_dialog_type("Запрос1С") == "query1c"
    assert api_dialog_type("Agent") == "agent"
    assert api_dialog_type("Агент") == "agent"


def test_infer_success_uses_last_postcondition():
    log = "[POSTCONDITION] success=false, reason=old\n[POSTCONDITION] success=true, reason=ok"
    assert infer_task_success(log) == (True, "postcondition")


def test_infer_success_query_output():
    assert infer_task_success("Проверка наличия вывода данных: ДА (Найден шаг RunQuery)") == (True, "query_output")
    assert infer_task_success("Проверка наличия вывода данных: НЕТ") == (False, "query_output_missing")


def test_infer_success_summary_without_status_is_not_hidden():
    assert infer_task_success("обычный лог без маркеров") == (False, "task_status_unavailable")
    assert infer_task_success("=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ===\nГотово") == (True, "summary")


def test_recognition_checks_unf_supplier_invoice():
    log = "\n".join([
        "РЕЖИМ: РАСПОЗНАВАНИЕ ДОКУМЕНТОВ",
        "recognize-supplier-invoice",
        "invoice.pdf",
        "target_object_name=СчетНаОплатуПоставщика",
        "DSL_TEMPLATE_JSON",
    ])
    result = evaluate_recognition(log, "invoice.pdf", "recognize-supplier-invoice", "СчетНаОплатуПоставщика", [], False)
    assert result["passed"] is True
    created = evaluate_recognition(log, "invoice.pdf", "recognize-supplier-invoice", "СчетНаОплатуПоставщика", [], True)
    assert created["passed"] is False
    assert created["checks"]["created_document"] is False
    failed = evaluate_recognition(log + "\nОшибка API (500): OpenAI API error (HTTP 402)", "invoice.pdf", "recognize-supplier-invoice", "СчетНаОплатуПоставщика", [], False)
    assert failed["passed"] is False
    assert failed["checks"]["provider_ok"] is False
    executed = "\n".join([
        "Счет на оплату № 6 от 26 августа 2025 г.pdf",
        "names=recognize-supplier-invoice",
        '{ "document_type": "СчетНаОплатуПоставщика", "number": "6" }',
        "Использован DSL template выбранного skill распознавания: recognize-supplier-invoice",
        "Создан документ 'СчетНаОплатуПоставщика'",
    ])
    executed_result = evaluate_recognition(
        executed,
        "Счет на оплату № 6 от 26 августа 2025 г.pdf",
        "recognize-supplier-invoice",
        "СчетНаОплатуПоставщика",
        [{"type": "Счет на оплату (полученный)"}],
        True,
    )
    assert executed_result["passed"] is True


def test_api_recognition_uses_local_supplier_invoice():
    files = recognition_files("")
    assert DEFAULT_SUPPLIER_INVOICE.is_file()
    assert files == {"supplier_invoice": str(DEFAULT_SUPPLIER_INVOICE)}
    artifact = Path("/tmp/iia-api-recognition-missing")
    missing = run_agent_api_recognition(
        "http://127.0.0.1/hs/iia-agent",
        "user",
        "secret",
        "supplier_invoice=/tmp/no-such-invoice-iia.pdf",
        artifact,
        1,
        False,
        False,
    )
    assert missing[0]["success"] is False
    assert "не найден" in missing[0]["error"]


def test_cloud_web_url_becomes_agent_api():
    assert agent_api_url_from_web("https://1cfresh.com/a/sbm/2226502/ru_RU/") == (
        "https://1cfresh.com/a/sbm/2226502/hs/iia-agent"
    )
