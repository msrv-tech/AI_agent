#Область ПрограммныйИнтерфейс

Функция ПолучитьВерсииDSLКонтракта() Экспорт
	Возврат Новый Структура("Текущая,Предыдущая", 2, 1);
КонецФункции

Функция ПолучитьРеестрКонтрактовDSL() Экспорт
	Реестр = Новый Соответствие;
	
	Реестр.Вставить("FindReferenceByName", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "FindReferenceByName", "object_name,name|value", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("FindReferenceByGUID", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "FindReferenceByGUID", "guid", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("FindReferenceByURL", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "FindReferenceByURL", "url", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("RunQuery", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "RunQuery", "query", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("ShowInfo", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "ShowInfo", "message", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("GetChangedObjects", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "GetChangedObjects", "-", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("GetMetadata", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "GetMetadata", "filter?", Истина, Ложь, "metadata.read", Истина, "retry_same_call"));
	Реестр.Вставить("GetObjectFields", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "GetObjectFields", "object_type,object_name", Истина, Ложь, "metadata.read", Истина, "retry_same_call"));
	Реестр.Вставить("CheckObjectExists", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "CheckObjectExists", "object_type,object_name", Истина, Ложь, "metadata.read", Истина, "retry_same_call"));
	Реестр.Вставить("SaveToStorage", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "SaveToStorage", "key,data,operation_id?", Ложь, Ложь, "data.read", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("LoadFromStorage", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "LoadFromStorage", "key", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("ForEach", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "ForEach", "collection,steps,operation_id?", Ложь, Ложь, "data.read", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("SelectObject", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "SelectObject", "reference|object|object_type+object_name+name", Истина, Ложь, "data.read", Истина, "retry_same_call"));
	Реестр.Вставить("CreateDocument", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "CreateDocument", "object_name,operation_id?", Ложь, Истина, "data.write.document", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("CreateReference", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "CreateReference", "object_name,operation_id?", Ложь, Истина, "data.write.reference", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("SetField", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "SetField", "field|field_name,value,operation_id?", Ложь, Истина, "data.write.reference", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("AddTableRow", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "AddTableRow", "table|table_name,data,operation_id?", Ложь, Истина, "data.write.document", Ложь, "repeat_only_with_same_operation_id"));
	Реестр.Вставить("Write", Новый Структура("name,input_schema,idempotent,requires_write,capability,supports_safe_retries,retry_strategy", "Write", "operation_id?", Ложь, Истина, "data.write.reference", Ложь, "repeat_only_with_same_operation_id"));
	
	Возврат Реестр;
КонецФункции

Функция ПолучитьКонтрактДействия(Действие) Экспорт
	Реестр = ПолучитьРеестрКонтрактовDSL();
	Возврат Реестр.Получить(Действие);
КонецФункции

Функция ПолучитьCapabilityДляДействия(Знач Действие) Экспорт
	Контракт = ПолучитьКонтрактДействия(Действие);
	Если Контракт = Неопределено Тогда
		Возврат "";
	КонецЕсли;
	Возврат ?(Контракт.Свойство("capability"), Строка(Контракт.capability), "");
КонецФункции

Функция ПроверитьCapabilityШага(Знач Шаг, Знач КонтекстВыполнения) Экспорт
	Результат = Новый Структура("Успех,Сообщение,Требуемое", Истина, "", "");
	
	Если ТипЗнч(Шаг) <> Тип("Структура") Или НЕ Шаг.Свойство("action") Тогда
		Возврат Результат;
	КонецЕсли;
	
	Требуемое = ПолучитьCapabilityДляДействия(Строка(Шаг.action));
	Результат.Требуемое = Требуемое;
	Если ПустаяСтрока(Требуемое) Тогда
		Возврат Результат;
	КонецЕсли;
	
	Если КонтекстВыполнения = Неопределено Или ТипЗнч(КонтекстВыполнения) <> Тип("Структура")
		Или НЕ КонтекстВыполнения.Свойство("DSL_Capabilities")
		Или ТипЗнч(КонтекстВыполнения.DSL_Capabilities) <> Тип("Массив") Тогда
		Возврат Результат;
	КонецЕсли;
	
	Если КонтекстВыполнения.DSL_Capabilities.Найти(Требуемое) = Неопределено Тогда
		Результат.Успех = Ложь;
		Результат.Сообщение = "Недостаточно прав для действия '" + Строка(Шаг.action) + "'. Требуется capability '" + Требуемое + "'.";
	КонецЕсли;
	
	Возврат Результат;
КонецФункции

Функция ПолучитьДействияЧтения() Экспорт
	Действия = Новый Массив;
	Реестр = ПолучитьРеестрКонтрактовDSL();
	Для Каждого ПараКонтракта Из Реестр Цикл
		Контракт = ПараКонтракта.Значение;
		Если Контракт <> Неопределено И Контракт.Свойство("requires_write") И НЕ Контракт.requires_write Тогда
			Действия.Добавить(ПараКонтракта.Ключ);
		КонецЕсли;
	КонецЦикла;
	Возврат Действия;
КонецФункции

Функция ПолучитьДействияИзменения() Экспорт
	Действия = Новый Массив;
	Реестр = ПолучитьРеестрКонтрактовDSL();
	Для Каждого ПараКонтракта Из Реестр Цикл
		Контракт = ПараКонтракта.Значение;
		Если Контракт <> Неопределено И Контракт.Свойство("requires_write") И Контракт.requires_write Тогда
			Действия.Добавить(ПараКонтракта.Ключ);
		КонецЕсли;
	КонецЦикла;
	Возврат Действия;
КонецФункции

Функция РазрешенныеДействия() Экспорт
	Действия = ПолучитьДействияЧтения();
	ДействияИзменения = ПолучитьДействияИзменения();
	Для Каждого Действие Из ДействияИзменения Цикл
		Действия.Добавить(Действие);
	КонецЦикла;
	Возврат Действия;
КонецФункции

#КонецОбласти
