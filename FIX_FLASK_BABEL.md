# Исправление ошибки Flask-Babel

## Проблема
```
AttributeError: 'Babel' object has no attribute 'localeselector'
```

## Причина
В Flask-Babel 4.0 изменился синтаксис для регистрации селектора локали. Старый декоратор `@babel.localeselector` больше не поддерживается.

## Решение

### Было (неправильно):
```python
@babel.localeselector
def get_locale():
    # код функции
```

### Стало (правильно):
```python
def get_locale():
    # код функции

@app.context_processor
def inject_locale():
    return {'locale': get_locale()}
```

## Дополнительные исправления

1. **Обработка ошибок создания папок**:
```python
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(AVATAR_FOLDER, exist_ok=True)
except PermissionError:
    print(f"Предупреждение: Не удалось создать папки {UPLOAD_FOLDER} или {AVATAR_FOLDER}")
```

2. **Восстановление файла переводов**:
Создан заново файл `translations/zh/LC_MESSAGES/messages.mo` для китайского языка.

## Результат
✅ Приложение успешно запускается  
✅ Многоязычность работает  
✅ Каталог стажировок доступен  
✅ Кнопки переключения языков функционируют  

## Запуск
```bash
python app.py
```

Приложение будет доступно по адресу: http://localhost:5000
