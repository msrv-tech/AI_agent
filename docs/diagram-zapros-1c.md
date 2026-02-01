# Диаграмма процесса «Запрос 1С»

Ниже — сквозной процесс в режиме диалога **`Запрос1С`**: какие части формируют промпты (включая `system`), что возвращает модель, как извлекается DSL, как выполняется `RunQuery`, и как устроен цикл исправления ошибок.

```mermaid
sequenceDiagram
  participant User as "User"
  participant Form as "Form_UI(ИИА_Агент)"
  participant Client as "Client(ИИА_Клиент/ИИА_ВызовСервера)"
  participant Server as "Server(ИИА_Сервер)"
  participant Prov as "Provider(ИИА_Провайдеры)"
  participant Prompts as "Prompts(ИИА_Промты)"
  participant Proxy as "OpenAI_API(Gitsell_AI_Proxy)"
  participant DSL as "DSL_Engine(ИИА_DSL)"
  participant DB as "OneC_DB(Запрос.Выполнить)"
  participant UI as "TableDoc_UI"

  User->>Form: Ввод задачи Запрос1С
  Form->>Client: ОтправитьСообщение

  Client->>Server: ВызватьИИ
  note over Server: В диалог пишется сообщение Система, но в LLM оно уйдёт как user-роль

  Server->>Prov: ВызватьИИ
  Prov->>Prompts: СформироватьПромпт

  note over Prompts: messages включают system для Запрос1С, историю и текущее сообщение

  Prompts-->>Prov: messages
  Prov->>Proxy: chat completions
  Proxy-->>Prov: content и usage
  Prov->>Prov: РаспознатьОтветИИ, извлечь DSL или текст запроса

  alt В ответе найден DSL JSON
    Prov-->>Server: Ответ DSL
    Server->>DSL: ВыполнитьDSL
    note over DSL: ТолькоЧтение запрещает модифицирующие действия. Разрешены только действия чтения.

    loop steps
      alt GetObjectFields или ShowInfo
        DSL-->>Server: Результат шага
      else RunQuery
        DSL->>DSL: Нормализация и проверка текста запроса
        DSL->>DB: Выполнить запрос
        DB-->>DSL: Результат запроса
        DSL->>DSL: Выгрузить результат и сохранить в контекст
        DSL-->>Server: Результат для таблицы
      end
    end

    DSL-->>Server: Итог выполнения DSL
    Server-->>Client: Возврат результата
    Client->>UI: Показать таблицу
  else DSL не найден
    Prov-->>Server: Ответ текст
    Server-->>Client: Текст (без выполнения)
    note over Client: На форме есть попытка извлечь DSL из текста и выполнить его, если нашёлся JSON.
  end

  opt Ошибка выполнения DSL или запроса
    DSL-->>Server: Ошибка выполнения
    Server->>Server: Исправить DSL через ИИ
    note over Server: Если ошибка про запрос или синтаксис, добавляется подсказка GetObjectFields или справка по языку запросов 1С.
    Server->>Prov: ВызватьИИ
    Prov-->>Server: Исправленный DSL
    Server->>DSL: Повторить ВыполнитьDSL
  end

  opt Оркестрация «задача завершена?»
    Server->>Prompts: Промпт проверки
    Server->>Prov: ВызватьИИ
    Prov-->>Server: Ответ проверки
    note over Server: Для Запрос1С дополнительно проверяется, что был RunQuery и показ таблицы. Иначе задача считается не выполненной.
    alt НЕТ (не завершено)
      Server->>Prov: ВызватьИИ продолжение
    end
  end
```

