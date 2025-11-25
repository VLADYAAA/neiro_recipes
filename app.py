from flask import Flask, request, jsonify
import logging
from be1 import SmartRecipeBot
import ssl

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = SmartRecipeBot("recipes.json")

# Стартовое сообщение с инструкцией
START_MESSAGE = """Привет! Я ваш кулинарный помощник. 

Для поиска рецептов используйте команды:
• "Найди рецепт пиццы"
• "Найди блюда с курицей и картошкой" 

При выборе из списка можно сказать:
• "Первое", "Второе", "Третье"
• "Покажи еще" - следующая страница
• "Другой рецепт" - новый поиск

Что хотите приготовить?"""

def split_long_response(text):
    """Разбивает длинный текст на части, если превышает лимит 1024 символа"""
    if len(text) <= 1024:
        return [text]
    
    # Пытаемся разбить по секциям рецепта
    parts = []
    
    # Ищем разделители для ингредиентов и шагов
    ingredients_marker = "Ингредиенты:"
    steps_marker = "Приготовление:"
    
    if ingredients_marker in text and steps_marker in text:
        # Разделяем на ингредиенты и шаги
        ingredients_part = text.split(steps_marker)[0]
        steps_part = steps_marker + text.split(steps_marker)[1]
        
        # Если каждая часть все еще слишком длинная, разбиваем дальше
        if len(ingredients_part) > 1024:
            # Разбиваем ингредиенты на части по 1000 символов
            for i in range(0, len(ingredients_part), 1000):
                part = ingredients_part[i:i+1000]
                if i == 0:
                    parts.append(part)
                else:
                    parts.append("(продолжение)\n" + part)
        else:
            parts.append(ingredients_part)
            
        if len(steps_part) > 1024:
            # Разбиваем шаги на части по 1000 символов
            for i in range(0, len(steps_part), 1000):
                part = steps_part[i:i+1000]
                if i == 0:
                    parts.append(part)
                else:
                    parts.append("(продолжение шагов)\n" + part)
        else:
            parts.append(steps_part)
    else:
        # Простое разбиение на части по 1000 символов
        for i in range(0, len(text), 1000):
            parts.append(text[i:i+1000])
    
    return parts

def create_alice_response(text, tts=None, buttons=None, end_session=False, session_state=None):
    """Создает ответ для Яндекс Алисы"""
    response = {
        "response": {
            "text": text,
            "end_session": end_session
        },
        "version": "1.0"
    }
    
    if tts:
        response["response"]["tts"] = tts
    
    if buttons:
        response["response"]["buttons"] = buttons
    
    if session_state:
        response["session_state"] = session_state
    
    return response

@app.route('/')
def index():
    return "Кулинарный помощник для Яндекс Алисы работает!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"Received data: {data}")
        
        # Проверяем, что это запрос от Алисы
        if not data or 'request' not in data:
            return jsonify(create_alice_response("Произошла ошибка", end_session=True))
        
        request_data = data['request']
        session = data.get('session', {})
        
        # Правильно получаем состояние сессии
        state = data.get('state', {})
        session_state = state.get('session', {}) if state else {}
        
        # Обрабатываем начало сессии
        if request_data.get('type') == 'SimpleUtterance' and 'марку' in request_data.get('command', '').lower():
            return jsonify(create_alice_response(
                "Это кулинарный помощник! " + START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди десерты", "hide": True}
                ]
            ))
        
        # Новый сеанс или команда "Помощь"
        if (session.get('new') or 
            request_data.get('command', '').lower() in ['помощь', 'что ты умеешь', 'help']):
            return jsonify(create_alice_response(
                START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди десерты", "hide": True}
                ]
            ))
        
        # Выход
        if request_data.get('command', '').lower() in ['пока', 'выход', 'закончить']:
            return jsonify(create_alice_response("До свидания! Приятного аппетита!", end_session=True))
        
        # Обрабатываем команду пользователя
        user_message = request_data.get('command', '').strip()
        
        if not user_message:
            return jsonify(create_alice_response(
                "Что вы хотите приготовить?",
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди помощь", "hide": True}
                ]
            ))
        
        user_message_lower = user_message.lower()
        
        # Обрабатываем команду "далее" для продолжения чтения рецепта
        if user_message_lower in ['далее', 'продолжи', 'следующая часть']:
            if session_state.get('response_parts'):
                # Получаем следующую часть рецепта
                remaining_parts = session_state['response_parts']
                if remaining_parts:
                    next_part = remaining_parts[0]
                    new_remaining_parts = remaining_parts[1:]
                    
                    # Обновляем состояние сессии
                    new_session_state = {
                        "response_parts": new_remaining_parts,
                        "current_part": session_state.get('current_part', 0) + 1
                    }
                    
                    # Добавляем подсказку для продолжения, если есть еще части
                    if new_remaining_parts:
                        next_part += "\n\n(Продолжение следует... Скажите 'далее' для чтения следующей части)"
                        buttons = [
                            {"title": "Далее", "hide": True},
                            {"title": "Другой рецепт", "hide": True},
                            {"title": "Помощь", "hide": True}
                        ]
                    else:
                        buttons = [
                            {"title": "Другой рецепт", "hide": True},
                            {"title": "Помощь", "hide": True}
                        ]
                    
                    return jsonify(create_alice_response(
                        next_part,
                        buttons=buttons,
                        session_state=new_session_state
                    ))
            else:
                return jsonify(create_alice_response(
                    "Больше нет частей для продолжения. Начните новый поиск.",
                    buttons=[
                        {"title": "Найди рецепт пиццы", "hide": True},
                        {"title": "Найди блюда с курицей", "hide": True},
                        {"title": "Помощь", "hide": True}
                    ]
                ))
        
        # Обрабатываем команду "покажи еще" для пагинации
        if user_message_lower in ['покажи еще', 'еще', 'дальше', 'следующие']:
            # Используем специальную команду для пагинации
            bot_response = bot.process_message("покажи еще")
            
            buttons = []
            if "Нашла" in bot_response and "рецептов" in bot_response:
                buttons.extend([
                    {"title": "Покажи еще", "hide": True},
                    {"title": "Другой рецепт", "hide": True}
                ])
            elif "Укажите номер рецепта" in bot_response:
                buttons.extend([
                    {"title": "Первое", "hide": True},
                    {"title": "Второе", "hide": True},
                    {"title": "Другой рецепт", "hide": True}
                ])
            else:
                buttons.extend([
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Помощь", "hide": True}
                ])
            
            return jsonify(create_alice_response(
                bot_response,
                buttons=buttons
            ))
        
        # Обрабатываем сообщение через бота
        bot_response = bot.process_message(user_message)
        
        # Проверяем длину ответа и разбиваем при необходимости
        if len(bot_response) > 1024:
            parts = split_long_response(bot_response)
            
            # Если ответ разбит на части, отправляем первую часть
            # и сохраняем остальные в состоянии сессии
            if len(parts) > 1:
                first_part = parts[0]
                remaining_parts = parts[1:]
                
                # Сохраняем оставшиеся части в состоянии сессии
                new_session_state = {
                    "response_parts": remaining_parts,
                    "current_part": 0
                }
                
                # Добавляем подсказку для продолжения
                first_part += "\n\n(Продолжение следует... Скажите 'далее' для чтения следующей части)"
                
                buttons = [
                    {"title": "Далее", "hide": True},
                    {"title": "Другой рецепт", "hide": True},
                    {"title": "Помощь", "hide": True}
                ]
                
                return jsonify(create_alice_response(
                    first_part,
                    buttons=buttons,
                    session_state=new_session_state
                ))
        
        # Обычная обработка для коротких ответов
        buttons = []
        if "Нашла" in bot_response and "рецептов" in bot_response:
            # Если показан список рецептов
            buttons.extend([
                {"title": "Покажи еще", "hide": True},
                {"title": "Другой рецепт", "hide": True}
            ])
        elif "Укажите номер рецепта" in bot_response:
            # Если нужно выбрать из списка
            buttons.extend([
                {"title": "Первое", "hide": True},
                {"title": "Второе", "hide": True},
                {"title": "Другой рецепт", "hide": True}
            ])
        else:
            # Обычное состояние
            buttons.extend([
                {"title": "Найди рецепт пиццы", "hide": True},
                {"title": "Найди блюда с курицей", "hide": True},
                {"title": "Помощь", "hide": True}
            ])
        
        return jsonify(create_alice_response(
            bot_response,
            buttons=buttons
        ))
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify(create_alice_response(
            "Извините, произошла ошибка. Попробуйте еще раз.",
            end_session=True
        ))

if __name__ == '__main__':
    # Запуск с SSL для HTTPS
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    
    # Укажите пути к вашим сертификатам
    try:
        context.load_cert_chain('cert.pem', 'key.pem')
        logger.info("SSL certificates loaded successfully")
        
        app.run(
            host='0.0.0.0',
            port=5000,
            ssl_context=context,
            debug=False
        )
    except FileNotFoundError:
        logger.warning("SSL certificates not found, running without HTTPS")
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False
        )