
Сервис работает на базе flask (файл app11.py) + witress(порт: 5001, файл: run_witress.py). Основная логика понимания и ответов пользователю в be1.py 
для поддержки https используются самоподписанные сертификаты и сервер nginx слушает порт 5000 и переадресует на 5001

## 🔍 **Быстрая диагностика**

### Проверка статуса всех сервисов:
```bash
systemctl status waitress-recipe.service google-sheets-parser.service nginx
```

### Проверка портов:
```bash
ss -tlnp | grep -E "5000|5001"
```
*Должны увидеть:* nginx на `0.0.0.0:5000` и waitress на `127.0.0.1:5001`

## 🚀 **Пошаговое восстановление**

### **1. Если всё упало - полный перезапуск:**
```bash
# Перезапустить все сервисы
systemctl restart waitress-recipe.service google-sheets-parser.service nginx

# Проверить статус
systemctl status waitress-recipe.service google-sheets-parser.service nginx --no-pager -l
```

### **2. Если сервисы не запускаются:**
```bash
# Перезагрузить конфигурацию systemd
systemctl daemon-reload

# Запустить по очереди
systemctl start nginx
systemctl start waitress-recipe.service
systemctl start google-sheets-parser.service
```

### **3. Если нужно запустить вручную (для отладки):**
```bash
# Активировать окружение
cd /root/neiro_recipes
source myenv/bin/activate

# Запустить waitress (остановите сначала сервис)
systemctl stop waitress-recipe.service
python run_waitress.py

# Запустить парсер
python google_sheets_parser.py
```

## 📊 **Просмотр логов**

### Логи конкретного сервиса:
```bash
# Waitress
journalctl -u waitress-recipe.service -f

# Google Sheets Parser
journalctl -u google-sheets-parser.service -f

# Nginx
journalctl -u nginx -f

# Все вместе
journalctl -u waitress-recipe.service -u google-sheets-parser.service -u nginx -f
```

### Логи за последний час:
```bash
journalctl -u waitress-recipe.service --since "1 hour ago"
```

