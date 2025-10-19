# Исправление ошибки с базой данных

## Проблема
```
sqlite3.OperationalError: no such column: ir.created_at
```

## Причина
В таблице `internship_requests` отсутствует колонка `created_at`, но код пытается её использовать в SQL запросе.

## Решение

### 1. Исправили SQL запрос в функции `hr_internship_catalog`

**Было (неправильно):**
```python
internships = db.execute(
    "SELECT ir.id, ir.specialization, ir.student_count, ir.period_start, ir.period_end, ir.skills_required, u.username AS university_name, ir.created_at "
    "FROM internship_requests ir JOIN users u ON ir.university_id = u.id "
    "WHERE ir.status = 'published' ORDER BY ir.created_at DESC"
).fetchall()
```

**Стало (правильно):**
```python
internships = db.execute(
    "SELECT ir.id, ir.specialization, ir.student_count, ir.period_start, ir.period_end, ir.skills_required, u.username AS university_name "
    "FROM internship_requests ir JOIN users u ON ir.university_id = u.id "
    "WHERE ir.status = 'published' ORDER BY ir.id DESC"
).fetchall()
```

### 2. Обновили шаблон `hr_internship_catalog.html`

**Убрали строку:**
```html
<p class="mb-1">
  <strong>{{ _('Created') }}:</strong> {{ internship.created_at }}
</p>
```

## Изменения:

✅ **SQL запрос** - убрали ссылку на несуществующую колонку `created_at`  
✅ **Сортировка** - заменили `ORDER BY ir.created_at DESC` на `ORDER BY ir.id DESC`  
✅ **Шаблон** - убрали отображение даты создания  
✅ **Функциональность** - каталог стажировок теперь работает корректно  

## Результат:
- ✅ Приложение запускается без ошибок
- ✅ Каталог стажировок доступен для HR
- ✅ Стажировки отображаются в порядке убывания ID
- ✅ Все функции каталога работают корректно

## Запуск:
```bash
python app.py
```

Приложение доступно по адресу: **http://localhost:5000**

Теперь HR-менеджеры могут:
- Просматривать опубликованные стажировки
- Подавать заявки на интересующие стажировки
- Получать информацию о требованиях и периоде стажировки
