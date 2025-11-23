# app.py
from flask import Flask, request, jsonify
from be1 import SmartRecipeBot
import logging
import ssl

app = Flask(__name__)
logging.basicConfig(level=logging.ERROR)

# Инициализация бота
try:
    bot = SmartRecipeBot("recipes.json", "llama3.2:3b")
except Exception as e:
    print(f"Ошибка инициализации бота: {e}")
    bot = None

@app.route('/webhook', methods=['POST'])
def main():
    if bot is None:
        return jsonify({
            'response': {
                'text': 'Извините, сервис временно недоступен. Попробуйте позже.',
                'end_session': False
            },
            'version': '1.0'
        })
    
    data = request.json
    user_input = data['request'].get('original_utterance', '').strip()
    
    if not user_input:
        # Приветственное сообщение для первого запуска
        return jsonify({
            'response': {
                'text': 'Привет! Я ваш кулинарный помощник. Что вы хотите приготовить?',
                'end_session': False
            },
            'version': '1.0'
        })
    
    # Обрабатываем сообщение через бота
    response_text = bot.process_message(user_input)
    
    # Извлекаем только ответ бота (после "🤖 Бот:")
    if '🤖 Бот:' in response_text:
        bot_response = response_text.split('🤖 Бot:', 1)[1].strip()
    else:
        bot_response = response_text
    
    # Проверяем, является ли сообщение прощанием
    end_session = any(word in user_input.lower() for word in ['пока', 'выход', 'до свидания', 'закончить'])
    
    return jsonify({
        'response': {
            'text': bot_response,
            'end_session': end_session
        },
        'version': '1.0'
    })

if __name__ == '__main__':
    # Запуск с SSL
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain('cert.pem', 'key.pem')  # Укажите пути к вашим SSL сертификатам
    
    app.run(host='0.0.0.0', port=5000, ssl_context=context)