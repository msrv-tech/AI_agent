#Область ПрограммныйИнтерфейс

Функция ПолучитьРеестрПолитикВосстановления() Экспорт
	Реестр = Новый Соответствие;
	Реестр.Вставить("table_not_found", Новый Структура("id,actions,max_attempts", "table_not_found_policy", "GetMetadata->GetObjectFields->RunQuery", 2));
	Реестр.Вставить("object_not_found", Новый Структура("id,actions,max_attempts", "object_not_found_policy", "GetMetadata->GetObjectFields->RunQuery", 2));
	Реестр.Вставить("field_not_found", Новый Структура("id,actions,max_attempts", "field_not_found_policy", "RepairDSL|SwitchObject", 2));
	Реестр.Вставить("query_syntax_error", Новый Структура("id,actions,max_attempts", "query_syntax_policy", "RepairDSL", 2));
	Реестр.Вставить("query_execution_error", Новый Структура("id,actions,max_attempts", "query_execution_policy", "RepairDSL|GetObjectFields", 2));
	Реестр.Вставить("parameter_missing", Новый Структура("id,actions,max_attempts", "parameter_missing_policy", "RepairDSL", 2));
	Реестр.Вставить("query_safety_violation", Новый Структура("id,actions,max_attempts", "query_safety_policy", "GetObjectFields|RepairDSL", 2));
	Реестр.Вставить("write_failed", Новый Структура("id,actions,max_attempts", "write_retry_same_operation_policy", "ResumeSameOperation|AbortUnsafeRetry", 2));
	Реестр.Вставить("storage_write_error", Новый Структура("id,actions,max_attempts", "storage_write_same_operation_policy", "ResumeSameOperation|AbortUnsafeRetry", 2));
	Реестр.Вставить("capability_violation", Новый Структура("id,actions,max_attempts", "capability_violation_policy", "AbortWithExplanation", 1));
	Возврат Реестр;
КонецФункции

Функция ИзвлечьКодОшибки(РезультатExecutor) Экспорт
	КодОшибки = "";
	Если РезультатExecutor = Неопределено Тогда
		Возврат КодОшибки;
	КонецЕсли;
	Если РезультатExecutor.Свойство("error_code") Тогда
		КодОшибки = Строка(РезультатExecutor.error_code);
	КонецЕсли;
	Если ПустаяСтрока(КодОшибки) И РезультатExecutor.Свойство("КодОшибки") Тогда
		КодОшибки = Строка(РезультатExecutor.КодОшибки);
	КонецЕсли;
	Если ПустаяСтрока(КодОшибки)
		Или ВРег(СокрЛП(КодОшибки)) = "STEP_FAILED"
		Или ВРег(СокрЛП(КодОшибки)) = "INVALID_STEP" Тогда
		ТекстОшибки = ?(РезультатExecutor.Свойство("Сообщение"), Строка(РезультатExecutor.Сообщение), "");
		КодПоТексту = ОпределитьКодОшибкиПоТексту(ТекстОшибки);
		Если НЕ ПустаяСтрока(КодПоТексту) Тогда
			КодОшибки = КодПоТексту;
		КонецЕсли;
	КонецЕсли;
	Возврат НормализоватьКодОшибки(КодОшибки);
КонецФункции

Функция ОпределитьКодОшибкиПоТексту(ТекстОшибки) Экспорт
	Текст = ВРег(СокрЛП(ТекстОшибки));
	Если ПустаяСтрока(Текст) Тогда
		Возврат "";
	КонецЕсли;
	Если СтрНайти(Текст, "ПОЛЕ НЕ НАЙДЕНО") > 0 Тогда
		Возврат "field_not_found";
	КонецЕсли;
	Если (СтрНайти(Текст, "ДОКУМЕНТ '") > 0
			ИЛИ СтрНайти(Текст, "СПРАВОЧНИК '") > 0
			ИЛИ СтрНайти(Текст, "РЕГИСТРНАКОПЛЕНИЯ '") > 0
			ИЛИ СтрНайти(Текст, "РЕГИСТРСВЕДЕНИЙ '") > 0)
		И СтрНайти(Текст, "НЕ НАЙДЕН") > 0 Тогда
		Возврат "object_not_found";
	КонецЕсли;
	Если СтрНайти(Текст, "ТАБЛИЦА") > 0 И (СтрНайти(Текст, "НЕ НАЙДЕНА") > 0 ИЛИ СтрНайти(Текст, "НЕ НАЙДЕН") > 0) Тогда
		Возврат "table_not_found";
	КонецЕсли;
	Если СтрНайти(Текст, "СИНТАКСИЧЕСКАЯ ОШИБКА") > 0
		ИЛИ СтрНайти(Текст, "ОЖИДАЕТСЯ ВЫРАЖЕНИЕ") > 0
		ИЛИ СтрНайти(Текст, "НЕОПОЗНАННЫЙ ОПЕРАТОР") > 0 Тогда
		Возврат "query_syntax_error";
	КонецЕсли;
	Если СтрНайти(Текст, "ПАРАМЕТР") > 0 И СтрНайти(Текст, "НЕ УСТАНОВЛЕН") > 0 Тогда
		Возврат "parameter_missing";
	КонецЕсли;
	Если СтрНайти(Текст, "QUERY SAFETY GATE") > 0
		ИЛИ СтрНайти(Текст, "FORBIDDEN_") > 0
		ИЛИ СтрНайти(Текст, "WHITELIST") > 0 Тогда
		Возврат "query_safety_violation";
	КонецЕсли;
	Если СтрНайти(Текст, "ОШИБКА ВЫПОЛНЕНИЯ ЗАПРОСА") > 0
		ИЛИ СтрНайти(Текст, "ОШИБКА ВЫПОЛНЕНИЯ ШАГА 'RUNQUERY'") > 0 Тогда
		Возврат "query_execution_error";
	КонецЕсли;
	Если СтрНайти(Текст, "ОШИБКА ЗАПИСИ ОБЪЕКТА") > 0
		ИЛИ СтрНайти(Текст, "ОШИБКА АВТОМАТИЧЕСКОЙ ЗАПИСИ ОБЪЕКТА") > 0 Тогда
		Возврат "write_failed";
	КонецЕсли;
	Возврат "";
КонецФункции

Функция ЭтоВосстановимаяОшибка(КодОшибки) Экспорт
	Код = НормализоватьКодОшибки(КодОшибки);
	Возврат Код = "field_not_found"
		Или Код = "table_not_found"
		Или Код = "object_not_found"
		Или Код = "query_syntax_error"
		Или Код = "query_execution_error"
		Или Код = "parameter_missing"
		Или Код = "query_safety_violation"
		Или Код = "write_failed"
		Или Код = "storage_write_error";
КонецФункции

Функция ПолучитьМаксПопытокДляОшибки(КодОшибки) Экспорт
	Код = НормализоватьКодОшибки(КодОшибки);
	Реестр = ПолучитьРеестрПолитикВосстановления();
	Политика = Реестр.Получить(Код);
	Если Политика <> Неопределено И Политика.Свойство("max_attempts") Тогда
		Возврат Политика.max_attempts;
	КонецЕсли;
	Возврат 1;
КонецФункции

Функция НормализоватьКодОшибки(КодОшибки) Экспорт
	КодВРег = ВРег(СокрЛП(КодОшибки));
	Если КодВРег = "FIELD_NOT_FOUND" Тогда
		Возврат "field_not_found";
	ИначеЕсли КодВРег = "TABLE_NOT_FOUND" Тогда
		Возврат "table_not_found";
	ИначеЕсли КодВРег = "OBJECT_NOT_FOUND" Тогда
		Возврат "object_not_found";
	ИначеЕсли КодВРег = "QUERY_SYNTAX_ERROR" Тогда
		Возврат "query_syntax_error";
	ИначеЕсли КодВРег = "QUERY_EXECUTION_ERROR" Тогда
		Возврат "query_execution_error";
	ИначеЕсли КодВРег = "PARAMETER_MISSING" Тогда
		Возврат "parameter_missing";
	ИначеЕсли КодВРег = "QUERY_SAFETY_VIOLATION" Тогда
		Возврат "query_safety_violation";
	ИначеЕсли КодВРег = "WRITE_FAILED" Тогда
		Возврат "write_failed";
	ИначеЕсли КодВРег = "STORAGE_WRITE_ERROR" Тогда
		Возврат "storage_write_error";
	ИначеЕсли КодВРег = "CAPABILITY_VIOLATION" Тогда
		Возврат "capability_violation";
	КонецЕсли;
	Возврат СокрЛП(КодОшибки);
КонецФункции

Функция ПопробоватьПрименитьWriteRecoveryPolicy(СсылкаДиалога, РезультатExecutor, КодОшибки, Результат) Экспорт
	ЛокКод = НормализоватьКодОшибки(КодОшибки);
	Если ЛокКод <> "write_failed" И ЛокКод <> "storage_write_error" Тогда
		Возврат Ложь;
	КонецЕсли;
	
	АртефактПлана = ИИА_Сервер.ПолучитьАртефактПланировщика(СсылкаДиалога);
	DSLИсходный = ?(АртефактПлана <> Неопределено И АртефактПлана.Свойство("PlannedDSL"), АртефактПлана.PlannedDSL, "");
	OperationId = ИИА_ReplayPolicy.ИзвлечьOperationIdИзРезультатаExecutor(РезультатExecutor);
	ПоследнийЭффект = ИИА_ReplayPolicy.НайтиПоследнийSideEffectПоOperationId(СсылкаДиалога, OperationId);
	
	Если ИИА_ReplayPolicy.ЭтоКоммитящийSideEffect(ПоследнийЭффект) Тогда
		СинтетическийРезультат = Новый Структура("Успех,Сообщение,error_code,operation_id,recovered_by_policy", Истина, "Повтор Write пропущен: side effect уже зафиксирован для operation_id " + OperationId + ".", "", OperationId, "write_retry_committed_policy");
		ИИА_Сервер.СохранитьРезультатExecutor(СсылкаДиалога, СинтетическийРезультат);
		Результат.Обработано = Истина;
		Результат.Идентификатор = "write_retry_committed_policy";
		Результат.Действие = "resume_after_committed_write";
		Результат.Решение = "resume";
		Результат.СледующаяСтадия = "Validate";
		Результат.Причина = "resume_after_committed_write";
		ИИА_Сервер.ДобавитьРешениеВDecisionLog(СсылкаДиалога, "recovery_policy", "resume_after_committed_write", "RecoverySubgraph", Новый Структура("source,policy_id,reason,operation_id,error_code", "recovery", Результат.Идентификатор, ЛокКод, OperationId, ЛокКод));
		ИИА_Сервер.СохранитьЧекпоинтОркестратора(СсылкаДиалога, "recovery_decision_resume", "Recover", Новый Структура("decision,policy_id,operation_id,last_effect", "resume", Результат.Идентификатор, OperationId, ?(ПоследнийЭффект.Свойство("effect_type"), Строка(ПоследнийЭффект.effect_type), "")), "resume_after_committed_write");
		Результат.Вставить("SemanticsLogged", Истина);
		Возврат Истина;
	КонецЕсли;
	
	Если ПустаяСтрока(OperationId) Тогда
		ИИА_Сервер.ДобавитьСообщениеВДиалог(СсылкаДиалога, Перечисления.ИИА_АвторСообщения.Система, Перечисления.ИИА_ТипСообщения.Текст, "Recovery остановлен: write-path завершился ошибкой без operation_id, безопасный retry невозможен.");
		Результат.Обработано = Истина;
		Результат.Идентификатор = "write_retry_missing_operation_id_policy";
		Результат.Действие = "abort_unsafe_write_retry";
		Результат.Решение = "abort";
		Результат.СледующаяСтадия = "Summarize";
		Результат.Причина = "abort_unsafe_write_retry";
		ИИА_Сервер.ДобавитьРешениеВDecisionLog(СсылкаДиалога, "recovery_policy", "abort_unsafe_write_retry", "RecoverySubgraph", Новый Структура("source,policy_id,reason,error_code", "recovery", Результат.Идентификатор, ЛокКод, ЛокКод));
		ИИА_Сервер.СохранитьЧекпоинтОркестратора(СсылкаДиалога, "recovery_decision_abort", "Recover", Новый Структура("decision,policy_id,error_code", "abort", Результат.Идентификатор, ЛокКод), "abort_unsafe_write_retry");
		Результат.Вставить("SemanticsLogged", Истина);
		Возврат Истина;
	КонецЕсли;
	
	Если ПустаяСтрока(DSLИсходный) Или СтрНайти(DSLИсходный, OperationId) = 0 Тогда
		ИИА_Сервер.ДобавитьСообщениеВДиалог(СсылкаДиалога, Перечисления.ИИА_АвторСообщения.Система, Перечисления.ИИА_ТипСообщения.Текст, "Recovery остановлен: не найден сохраненный DSL с тем же operation_id для безопасного повтора write-path.");
		Результат.Обработано = Истина;
		Результат.Идентификатор = "write_retry_missing_planned_dsl_policy";
		Результат.Действие = "abort_missing_same_operation";
		Результат.Решение = "abort";
		Результат.СледующаяСтадия = "Summarize";
		Результат.Причина = "abort_missing_same_operation";
		ИИА_Сервер.ДобавитьРешениеВDecisionLog(СсылкаДиалога, "recovery_policy", "abort_missing_same_operation", "RecoverySubgraph", Новый Структура("source,policy_id,reason,operation_id,error_code", "recovery", Результат.Идентификатор, ЛокКод, OperationId, ЛокКод));
		ИИА_Сервер.СохранитьЧекпоинтОркестратора(СсылкаДиалога, "recovery_decision_abort", "Recover", Новый Структура("decision,policy_id,operation_id", "abort", Результат.Идентификатор, OperationId), "abort_missing_same_operation");
		Результат.Вставить("SemanticsLogged", Истина);
		Возврат Истина;
	КонецЕсли;
	
	ИИА_Сервер.СохранитьАртефактПланировщика(СсылкаДиалога, DSLИсходный, "recovery_resume_same_operation_id", ?(АртефактПлана <> Неопределено И АртефактПлана.Свойство("PlanStepId"), АртефактПлана.PlanStepId, ""));
	Результат.Обработано = Истина;
	Результат.Идентификатор = ?(ЛокКод = "storage_write_error", "storage_write_same_operation_policy", "write_retry_same_operation_policy");
	Результат.Действие = "resume_same_operation_id";
	Результат.Решение = "resume";
	Результат.СледующаяСтадия = "Execute";
	Результат.Причина = "resume_same_operation_id";
	ИИА_Сервер.ДобавитьРешениеВDecisionLog(СсылкаДиалога, "recovery_policy", "resume_same_operation_id", "RecoverySubgraph", Новый Структура("source,policy_id,reason,operation_id,error_code", "recovery", Результат.Идентификатор, ЛокКод, OperationId, ЛокКод));
	ИИА_Сервер.СохранитьЧекпоинтОркестратора(СсылкаДиалога, "recovery_decision_resume", "Recover", Новый Структура("decision,policy_id,operation_id", "resume", Результат.Идентификатор, OperationId), "resume_same_operation_id");
	Результат.Вставить("SemanticsLogged", Истина);
	Возврат Истина;
КонецФункции

Функция СформироватьRecoveryDSLGetObjectFields(ИмяТаблицы) Экспорт
	ЛокИмя = СокрЛП(ИмяТаблицы);
	Если ПустаяСтрока(ЛокИмя) Тогда
		Возврат "";
	КонецЕсли;
	ПозицияТочки = СтрНайти(ЛокИмя, ".");
	Если ПозицияТочки = 0 Тогда
		Возврат "";
	КонецЕсли;
	Префикс = ВРег(Лев(ЛокИмя, ПозицияТочки - 1));
	ИмяОбъекта = СокрЛП(Сред(ЛокИмя, ПозицияТочки + 1));
	Если ПустаяСтрока(ИмяОбъекта) Тогда
		Возврат "";
	КонецЕсли;
	ТипОбъекта = "";
	Если Префикс = "ДОКУМЕНТ" Тогда
		ТипОбъекта = "Документ";
	ИначеЕсли Префикс = "СПРАВОЧНИК" Тогда
		ТипОбъекта = "Справочник";
	ИначеЕсли Префикс = "РЕГИСТРНАКОПЛЕНИЯ" Тогда
		ТипОбъекта = "РегистрНакопления";
	ИначеЕсли Префикс = "РЕГИСТРСВЕДЕНИЙ" Тогда
		ТипОбъекта = "РегистрСведений";
	КонецЕсли;
	Если ПустаяСтрока(ТипОбъекта) Тогда
		Возврат "";
	КонецЕсли;
	Возврат "{""dsl_version"":2,""steps"":[{""action"":""GetObjectFields"",""object_type"":""" + ТипОбъекта + """,""object_name"":""" + ИмяОбъекта + """}]}";
КонецФункции

Функция СохранитьRecoveryАртефактЕслиВалиден(СсылкаДиалога, DSLКандидат, Причина, Действие, Результат) Экспорт
	Если ПустаяСтрока(DSLКандидат) Тогда
		Возврат Ложь;
	КонецЕсли;
	Если ИИА_Оркестратор.ЭтоРанняяСдачаShowInfo(СсылкаДиалога, DSLКандидат) Тогда
		ИИА_Сервер.ДобавитьЗаписьВЛогДиалога(СсылкаДиалога, "[ANTI_GIVEUP] Recovery-ответ отклонен: ранний negative ShowInfo.");
		Возврат Ложь;
	КонецЕсли;
	ИИА_Сервер.СохранитьАртефактПланировщика(СсылкаДиалога, DSLКандидат, Причина, Формат(ТекущаяДата(), "ДФ=yyyyMMddHHmmss"));
	Результат.Обработано = Истина;
	Результат.Действие = Действие;
	Возврат Истина;
КонецФункции

#КонецОбласти
