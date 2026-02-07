# Архитектура работы ИИ-агента 1С

В данном файле описана логика работы агента, включая механизмы Discovery, обработки ошибок и оптимизации контекста.

```mermaid
graph TD
    Start([Запрос пользователя]) --> PromptGen[ИИА_Промты: Генерация промпта + StateSummary]
    PromptGen --> LLM[ИИ: Генерация DSL-сценария]
    
    subgraph Execution [Ядро выполнения DSL - ИИА_DSL]
        LLM --> ValidateDSL{Валидация DSL}
        ValidateDSL -- Ошибка --> FixDSL[ИИА_Сервер: ИсправитьDSLЧерезИИ]
        ValidateDSL -- Успех --> RunSteps[Выполнение шагов сценария]
        
        RunSteps --> StepType{Тип действия?}
        
        StepType -- RunQuery --> CheckTable{Таблица существует?}
        CheckTable -- Нет --> TableError[Ошибка: table_not_found]
        CheckTable -- Да --> ExecuteSQL[Выполнение запроса 1С]
        
        StepType -- GetMetadata --> MetadataSearch[Поиск + Карта синонимов]
        MetadataSearch --> LimitResults[Лимит 20 объектов]
        
        StepType -- ShowInfo --> ValidateData{Есть данные в контексте?}
        ValidateData -- Нет --> HallucinationError[Ошибка: Нераспознанные поля]
        ValidateData -- Да --> ShowUser[Вывод сообщения]
    end
    
    subgraph ErrorHandling [Умная обработка ошибок - ИИА_Сервер]
        TableError --> Levenshtein[Алгоритм Левенштейна: Поиск похожих]
        Levenshtein --> AutoPilot[Автопилот: GetObjectFields для лучшего]
        
        FixDSL --> Warmup[Повышение Temperature до 0.7]
        Warmup --> LLM
        
        AutoPilot --> PromptGen
    end
    
    subgraph ContextOptimization [Оптимизация памяти]
        RunSteps --> HistoryCleanup[Удаление старых метаданных из истории]
        HistoryCleanup --> PromptGen
    end

    ShowUser --> DoD{Задача выполнена?}
    DoD -- Нет --> PromptGen
    DoD -- Да --> End([Результат пользователю])

    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style End fill:#f9f,stroke:#333,stroke-width:2px
    style LLM fill:#bbf,stroke:#333,stroke-width:2px
    style Execution fill:#dfd,stroke:#333,stroke-width:1px
    style ErrorHandling fill:#fdd,stroke:#333,stroke-width:1px
```

## Ключевые особенности

1.  **Discovery (Исследование):** Агент никогда не гадает имена объектов. Если объект не найден, включается алгоритм Левенштейна и карта синонимов 1С для поиска альтернатив.
2.  **Автопилот:** При нахождении подходящего документа система автоматически получает его реквизиты, сокращая количество итераций.
3.  **Динамическая температура:** При исправлении ошибок температура модели повышается до 0.7 для более гибкого подбора синонимов.
4.  **Context Saver:** Система агрессивно очищает историю от старых списков метаданных, оставляя только последний результат, что позволяет работать в огромных конфигурациях (ERP, УТ).
5.  **Защита от галлюцинаций:** Блокировка вывода сообщений с данными, которые не были реально получены из базы.
