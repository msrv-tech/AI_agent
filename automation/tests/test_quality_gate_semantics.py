from automation.bridge.test_examples import evaluate_scenario_rules


def analysis(log: str, *, zero_rows: bool = False, nonempty: bool = False, errors: int = 0) -> dict:
    return {
        "dsl_actions_found": ["RunQuery", "ShowInfo"],
        "dsl_actions_executed": ["RunQuery", "ShowInfo"],
        "error_lines": ["error"] * errors,
        "runquery_zero_rows": zero_rows,
        "runquery_nonempty": nonempty,
        "recovery_attempts": errors,
        "non_system_text": log,
        "full_log_text": log,
        "approval_pending": False,
    }


def test_stock_query_rejects_order_document_even_with_expected_columns():
    log = "ИЗ Документ.ЗаказПокупателя КАК Заказ; Номенклатура КАК Номенклатура, Количество КАК Остаток"
    result = evaluate_scenario_rules({"id": "stock_low"}, True, analysis(log, nonempty=True), 1000)
    assert not result["passed"]
    assert any("документу заказа" in item for item in result["violations"])


def test_stock_query_rejects_empty_result():
    log = "ИЗ РегистрНакопления.ЗапасыНаСкладах.Остатки; Номенклатура, КоличествоОстаток КАК Остаток"
    result = evaluate_scenario_rules({"id": "stock_low"}, True, analysis(log, zero_rows=True), 1000)
    assert not result["passed"]
    assert any("0 строк" in item for item in result["violations"])


def test_orders_client_accepts_metadata_search_when_order_document_missing():
    log = "Выполнить GetMetadata filter=заказ покупателя заказ клиента\nПолучены метаданные с фильтром 'заказ покупателя заказ клиента':\nОБЪЕКТЫ НЕ НАЙДЕНЫ."
    result = evaluate_scenario_rules({"id": "orders_client"}, True, analysis(log, zero_rows=True), 1000)
    assert result["passed"]


def test_orders_client_rejects_realization_source():
    log = "ИЗ Документ.РеализацияТоваровУслуг КАК Док"
    result = evaluate_scenario_rules({"id": "orders_client"}, True, analysis(log, nonempty=True), 1000)
    assert not result["passed"]
    assert any("реализации" in item for item in result["violations"])


def test_orders_client_accepts_missing_order_document_message():
    log = "ShowInfo: В этой конфигурации нет документа заказа покупателя или заказа клиента."
    result = evaluate_scenario_rules({"id": "orders_client"}, True, analysis(log, zero_rows=True), 1000)
    assert result["passed"]


def test_order_vs_realization_accepts_missing_order_document_message():
    log = "ShowInfo: В этой конфигурации нет документа заказа покупателя или заказа клиента."
    result = evaluate_scenario_rules(
        {"id": "order_vs_realization_resolution"}, True, analysis(log, zero_rows=True), 1000
    )
    assert result["passed"]


def test_empty_data_rejects_invented_period_join():
    log = "ЛЕВОЕ СОЕДИНЕНИЕ Продажи КАК Период ПО Период.Дата = Продажи.Период\nРезультат запроса: строк=0"
    result = evaluate_scenario_rules({"id": "empty_data_not_failure"}, True, analysis(log, zero_rows=True), 2000)
    assert not result["passed"]
    assert any("псевдонимом Период" in item for item in result["violations"])


def test_empty_data_requires_future_period_filter():
    log = "ВЫБРАТЬ ПЕРВЫЕ 100 Период КАК Дата ИЗ РегистрНакопления.X.Обороты КАК X\nРезультат запроса: строк=0"
    result = evaluate_scenario_rules({"id": "empty_data_not_failure"}, True, analysis(log, zero_rows=True), 2000)
    assert not result["passed"]
    assert any("фильтр 2035" in item for item in result["violations"])


def test_sales_analysis_rejects_recovery_after_too_many_query_errors():
    result = evaluate_scenario_rules(
        {"id": "sales_analysis"}, True, analysis("RunQuery result", nonempty=True, errors=4), 2000
    )
    assert not result["passed"]
    assert any("лимит ошибок" in item for item in result["violations"])
