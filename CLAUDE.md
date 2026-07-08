# CLAUDE.md — Учёт ПУ (репозиторий Uchet_PU)

Этот файл — контекст проекта для Claude Code. Прочитай его перед работой над репозиторием.

## Что это

Веб-система учёта приборов учёта электроэнергии (ПУ = приборы учёта) для структуры «Россети». Ведёт инвентаризацию счётчиков, их перемещения между подразделениями, техприсоединения, замены, ИЖЦ и согласование работ. Организационная структура — Сочинский регион:

- **СУЭ** — Служба учёта электроэнергии (центр, видит всё)
- **7 РЭС** — районные электросети (Адлерский, Дагомысский, Краснополянский, Лазаревский, Сочинский, Туапсинский, Хостинский)
- **ЭСК** — подрядчик по монтажу (центральный админ + 7 подразделений ЭСК)
- **ОКС** — отдельная ветка (центральный + 7 участков)
- **Лаборатория** — загрузка реестров ПУ из Excel

## Стек

**Backend:** FastAPI + SQLAlchemy, БД **PostgreSQL**. Авторизация — JWT (`python-jose`), пароли — bcrypt. Импорт/экспорт Excel — pandas + openpyxl. CORS открыт для всех origin.

**Frontend:** React 18 + Vite 5, HTTP — axios, стили — Tailwind CSS. Токен хранится в `localStorage` (`token`), axios-интерцептор добавляет `Authorization: Bearer` ко всем запросам и разлогинивает по 401.

## Структура

```
backend/
  main.py            — МОНОЛИТ (~5300 строк): конфиг, все модели, auth, ВСЕ эндпоинты, init БД
  requirements.txt
frontend/
  src/
    App.jsx          — МОНОЛИТ (~6100 строк): AuthContext, дизайн-система, все страницы и роутинг
    api.js           — axios-клиент (baseURL '/api', Bearer-интерцептор, 401-редирект)
    main.jsx         — точка входа React
    index.css        — Tailwind + анимация загрузчика «Россети»
  vite.config.js     — dev-прокси /api → http://localhost:8000
  package.json, tailwind.config.js, postcss.config.js
README.md            — описание системы, роли, деплой, тестовые аккаунты
```

**Важно: и backend, и frontend — монолитные однофайловые приложения.** Вся логика в `backend/main.py` и `frontend/src/App.jsx`. Модульной архитектуры нет — правки идут в эти большие файлы. Всегда сверяй строки/имена по самим файлам через поиск, дерево выше — для ориентира.

## Модель данных (16 таблиц, `backend/main.py`)

Справочники и порядок восстановления при бэкапе: `units`, `roles`, `users`, `pu_registers`, `esk_masters`, `va_nominals`, `tt_nominals`, `materials`, `pu_type_reference`, `ttr_res`, `ttr_esk`, `ttr_materials`, `ttr_pu_types`, `pu_items`, `pu_materials`, `pu_movements`.

- **PUItem** — центральная запись прибора (~50 полей: `serial_number`, `pu_type`, `status`, юниты, договор/потребитель/адрес, электрика, монтаж, ссылки на ТТР, поля ЭСК, согласование).
- **Unit** — подразделения с иерархией (`parent_id`), тип из `UnitType`.
- **PUMovement** — история перемещений (from→to, кем, когда).
- **TTR_RES / TTR_ESK** — типовые решения (у ЭСК с ценами: ЛСР, цена без/с НДС).
- **PUTypeReference** — паттерны автоопределения типа (фаза/напряжение/форм-фактор).

### Enum-ы (важно, БД PostgreSQL — при изменении нужна миграция enum)

- `UnitType`: SUE, LAB, ESK, RES, ESK_UNIT, OKS, OKS_UNIT
- `RoleCode`: SUE_ADMIN, LAB_USER, ESK_ADMIN, RES_USER, ESK_USER, OKS_ADMIN, OKS_USER
- `PUStatus`: SKLAD, TECHPRIS, ZAMENA, IZHC, INSTALLED
- `ApprovalStatus`: NONE, PENDING, APPROVED, REJECTED

## Роли и доступ

| Роль | Видит | Ключевые права |
|------|-------|----------------|
| `SUE_ADMIN` | всё | перемещение РЭС↔РЭС, удаление (по коду), управление пользователями/справочниками, ТЗ |
| `LAB_USER` | свои загрузки | загрузка реестров Excel |
| `ESK_ADMIN` | все ЭСК | перемещение ЭСК↔ЭСК, мастера |
| `RES_USER` | свой РЭС | просмотр, согласование (approve/reject) |
| `ESK_USER` | своё подразделение ЭСК | просмотр, заявки |
| `OKS_ADMIN` | все участки ОКС | перемещение ОКС↔ОКС, ТЗ |
| `OKS_USER` | свой участок ОКС | просмотр |

Проверки на фронте (в `App.jsx`): `canUpload`, `canMove`, `canDelete`, `canManageUsers`, `canApprove`, `canCreateTZ`, `canManageReferences`, `canManageMasters`. **Это только фильтр интерфейса — настоящую проверку прав делает бэкенд.**

Тестовые аккаунты (создаются в `init_db()`): `admin/admin123` (SUE_ADMIN), `lab/lab123` (LAB), `esk/esk123` (ESK_ADMIN), `oks/oks123` (OKS_ADMIN).

## Конфиг и запуск

`Settings` (`backend/main.py`) читает из `.env`:
- `DATABASE_URL` — строка подключения PostgreSQL
- `SECRET_KEY` — секрет для JWT
- `ADMIN_CODE` — код для деструктивных операций (удаление ПУ), по умолчанию `2233`

Схема БД поднимается автоматически: `ensure_db_schema()` создаёт таблицы, добавляет недостающие колонки и мигрирует enum-ы; `init_db()` создаёт роли, все юниты (SUE, LAB, ESK, OKS + по 7 РЭС/ЭСК_UNIT/OKS_UNIT) и тестовых пользователей.

```
# backend
cd backend
pip install -r requirements.txt
python main.py          # инициализация схемы БД
uvicorn main:app --reload   # http://localhost:8000

# frontend
cd frontend
npm install
npm run dev             # Vite, проксирует /api на :8000
npm run build           # прод-сборка в dist/
```

## Ключевые группы эндпоинтов (префикс `/api`)

- `auth/login`, `auth/me`
- `pu/items` (список/деталь/PUT), `pu/upload` (Excel, только Лаб), `pu/upload-template`, `pu/export`
- `pu/move`, `pu/move-bulk`, `pu/delete` (требует ADMIN_CODE)
- `pu/dashboard`, `pu/analysis`, `pu/detect-type`
- `pu/pending-approval`, `pu/items/{id}/approve`, `pu/items/{id}/reject`
- `ttr/res`, `ttr/esk`, `masters`, `users`, `tz/*`, `requests/*`
- `admin/backup` (gzip-JSON), `admin/restore`, `admin/health-check`, `admin/export-issues`

**Бэкап:** `admin/backup` отдаёт весь дамп 16 таблиц как gzip-сжатый JSON (`backup_full_<дата>.json.gz`), `admin/restore` — восстанавливает в порядке, заданном в `tables_map`.

## Деплой

Прод развёрнут на **Amvera**, домен `uchet-pu-amvera-ashinoff.amvera.io` (этот же URL используется как приложение «Светлячок» в реестре Платформы SUE_system). README описывает вариант Render.com — при работе с деплоем сверяйся с реальным окружением Amvera, а не только с README. Frontend раздаётся как SPA, `/api/*` проксируется на backend. Секреты (`DATABASE_URL`, `SECRET_KEY`) задаются в окружении, не в коде.

## Правила (соблюдать)

- **Все правки backend — в `backend/main.py`, frontend — в `frontend/src/App.jsx`** (монолиты). Перед редактированием ищи точное место через Grep, файлы большие.
- **Меняешь модель/enum — помни про PostgreSQL-миграцию** (логика в `ensure_db_schema()`); новый enum-статус требует ALTER TYPE.
- **Порядок таблиц в бэкапе/восстановлении важен** (справочники → зависимые). Меняешь схему — синхронизируй `tables_map` в backup и restore.
- **Права проверяет бэкенд.** Фронтовые `can*`-флаги — только UI.
- **Секреты не коммить.**

## Совместная работа

Этот проект — часть набора: **Платформа** (SUE_system, web-desktop), **Контроль СИЗ** (siz-control) и Учёт ПУ. Учёт ПУ подключён в Платформу как приложение «Светлячок». Commit и push после правок делаются по умолчанию.
