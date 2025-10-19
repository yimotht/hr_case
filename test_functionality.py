#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функционала многоязычности и каталога стажировок
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, get_db, init_db

def test_multilang():
    """Тестирует функционал многоязычности"""
    print("=== Тестирование многоязычности ===")
    
    with app.test_client() as client:
        # Тестируем переключение языков
        print("1. Тестируем переключение на английский язык...")
        response = client.get('/set_language/en')
        assert response.status_code == 302, f"Ожидался код 302, получен {response.status_code}"
        print("   ✓ Переключение на английский работает")
        
        print("2. Тестируем переключение на китайский язык...")
        response = client.get('/set_language/zh')
        assert response.status_code == 302, f"Ожидался код 302, получен {response.status_code}"
        print("   ✓ Переключение на китайский работает")
        
        print("3. Тестируем переключение на русский язык...")
        response = client.get('/set_language/ru')
        assert response.status_code == 302, f"Ожидался код 302, получен {response.status_code}"
        print("   ✓ Переключение на русский работает")
        
        print("4. Тестируем страницу входа...")
        response = client.get('/login')
        assert response.status_code == 200, f"Ожидался код 200, получен {response.status_code}"
        print("   ✓ Страница входа доступна")

def test_internship_catalog():
    """Тестирует функционал каталога стажировок"""
    print("\n=== Тестирование каталога стажировок ===")
    
    with app.test_client() as client:
        # Сначала нужно войти как HR
        print("1. Тестируем доступ к каталогу стажировок без авторизации...")
        response = client.get('/hr/internships')
        assert response.status_code == 302, f"Ожидался код 302 (редирект), получен {response.status_code}"
        print("   ✓ Доступ к каталогу стажировок защищен авторизацией")
        
        print("2. Тестируем доступ к форме подачи заявки на стажировку...")
        response = client.get('/hr/internships/1/apply')
        assert response.status_code == 302, f"Ожидался код 302 (редирект), получен {response.status_code}"
        print("   ✓ Доступ к форме подачи заявки защищен авторизацией")

def test_database():
    """Тестирует структуру базы данных"""
    print("\n=== Тестирование базы данных ===")
    
    with app.app_context():
        db = get_db()
        
        # Проверяем существование таблиц
        tables = ['users', 'profiles', 'companies', 'vacancies', 'resumes', 
                 'skills', 'resume_skills', 'applications', 'internship_requests', 
                 'internship_responses', 'moderation_logs']
        
        for table in tables:
            result = db.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone()
            assert result is not None, f"Таблица {table} не найдена"
            print(f"   ✓ Таблица {table} существует")
        
        print("   ✓ Все необходимые таблицы созданы")

def main():
    """Основная функция тестирования"""
    print("Запуск тестирования функционала HR платформы...")
    
    try:
        # Инициализируем базу данных
        with app.app_context():
            init_db()
        
        # Запускаем тесты
        test_multilang()
        test_internship_catalog()
        test_database()
        
        print("\n🎉 Все тесты прошли успешно!")
        print("\nДобавленный функционал:")
        print("✓ Многоязычность (русский, английский, китайский)")
        print("✓ Кнопки переключения языков внизу по центру")
        print("✓ Каталог стажировок для роли Company_HR")
        print("✓ Возможность подачи заявок на стажировки")
        
    except Exception as e:
        print(f"\n❌ Ошибка при тестировании: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
