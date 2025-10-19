#!/usr/bin/env python3
"""
Скрипт для компиляции переводов Flask-Babel
"""
import os
import subprocess
import sys

def compile_translations():
    """Компилирует .po файлы в .mo файлы"""
    try:
        # Компилируем переводы для каждого языка
        languages = ['ru', 'en', 'zh']
        
        for lang in languages:
            po_file = f'translations/{lang}/LC_MESSAGES/messages.po'
            mo_file = f'translations/{lang}/LC_MESSAGES/messages.mo'
            
            if os.path.exists(po_file):
                print(f"Компилируем переводы для языка: {lang}")
                result = subprocess.run([
                    sys.executable, '-m', 'pybabel', 'compile',
                    '-d', 'translations',
                    '-l', lang
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"✓ Переводы для {lang} успешно скомпилированы")
                else:
                    print(f"✗ Ошибка компиляции для {lang}: {result.stderr}")
            else:
                print(f"⚠ Файл переводов не найден: {po_file}")
                
    except Exception as e:
        print(f"Ошибка при компиляции переводов: {e}")

if __name__ == "__main__":
    compile_translations()
