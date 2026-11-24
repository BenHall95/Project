# Веб-приложение «Прокат оборудования» (FastAPI + SQLite)

Веб-система для автоматизации проката спортивного, туристического и строительного инвентаря: каталог с фильтрацией, бронирование с проверкой пересечения дат, контроль выдачи/возврата, расчёт штрафов и складской учёт.

## Установка и запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Запустите сервер разработки:
```bash
uvicorn app.main:app --reload
```

3. Откройте приложение в браузере: `http://127.0.0.1:8000` (документация API доступна по адресу `http://127.0.0`).

## Демо-аккаунты

- **Администратор:** `admin` / `admin`
- **Менеджер:** `manager` / `manager`
- **Клиент:** `client` / `client`

## Запуск автотестов

```bash
pytest -v
```

## ER-диаграмма базы данных

```mermaid
erDiagram
    USERS ||--o{ BOOKINGS : creates
    EQUIPMENT ||--o{ BOOKINGS : includes
    BOOKINGS ||--o{ FINES : has

    USERS {
        int id PK
        string username UK
        string hashed_password
        string role
    }

    EQUIPMENT {
        int id PK
        string name
        string category
        float price_per_day
        int total_qty
        int broken_qty
        string image_url
    }

    BOOKINGS {
        int id PK
        int user_id FK
        int equipment_id FK
        int quantity
        date start_date
        date end_date
        float total_price
        string status
        string condition_note
    }

    FINES {
        int id PK
        int booking_id FK
        float amount
        string reason
        boolean is_paid
    }
```
