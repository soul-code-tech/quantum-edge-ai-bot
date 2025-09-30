#!/bin/bash

echo "🚀 Quantum Edge AI Bot - Запуск"
echo "================================"

# Проверяем наличие Python
echo "🔍 Проверка Python..."
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python не найден!"
    exit 1
fi

echo "✅ Python найден: $PYTHON_CMD"

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Создайте файл .env на основе .env.example"
    echo "cp .env.example .env"
    echo "📝 Затем отредактируйте .env и добавьте реальные API ключи"
    exit 1
fi

echo "✅ Файл .env найден"

# Запускаем тесты
echo "🧪 Запуск тестов..."
$PYTHON_CMD test_bot.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Тесты пройдены успешно!"
    echo "🚀 Запуск бота..."
    
    # Запускаем основной бот
    $PYTHON_CMD main.py
else
    echo "❌ Тесты провалены! Исправьте ошибки перед запуском."
    exit 1
fi
