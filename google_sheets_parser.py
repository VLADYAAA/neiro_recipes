"""
СИНХРОНИЗАТОР GOOGLE ТАБЛИЦЫ И ФАЙЛА РЕЦЕПТОВ
При запуске: объединяет все рецепты из обоих источников
В работе: синхронизирует изменения
"""

import json
import time
import os
import hashlib
from datetime import datetime
import schedule
import gspread
from google.oauth2.service_account import Credentials
import sys
import logging
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync.log'),
        logging.StreamHandler()
    ]
)

class RecipeSynchronizer:
    def __init__(self):
        # КОНФИГУРАЦИЯ
        self.credentials_file = 'credentials.json'
        self.spreadsheet_url = "you_url"
        self.recipes_file = 'recipes.json'
        self.check_interval = 300 # секунд
        
        # Настройка Google Sheets
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        logging.info("🔧 Инициализация синхронизатора...")
        
    def load_recipes_from_file(self):
        """Загружает рецепты из JSON файла"""
        try:
            if os.path.exists(self.recipes_file):
                with open(self.recipes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return [data]
                    return []
        except Exception as e:
            logging.error(f"Ошибка загрузки файла: {e}")
        return []
    
    def load_recipes_from_sheet(self):
        """Загружает рецепты из Google таблицы"""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.get_worksheet(0)
            
            all_data = worksheet.get_all_values()
            
            if not all_data:
                return []
            
            headers = all_data[0]
            rows = all_data[1:]
            
            recipes = []
            for i, row_data in enumerate(rows, start=2):
                # Пропускаем пустые строки
                if not any(row_data):
                    continue
                    
                recipe = self.row_to_your_format(headers, row_data, i)
                if recipe:
                    # Добавляем номер строки для обратной связи
                    recipe['_sheet_row'] = i
                    recipes.append(recipe)
                    
            return recipes
            
        except Exception as e:
            logging.error(f"Ошибка загрузки из таблицы: {e}")
            return []
    
    def row_to_your_format(self, headers, row_data, row_num):
        """Конвертирует строку из Google Sheets в ваш формат"""
        try:
            row_dict = dict(zip(headers, row_data))
            
            title_raw = row_dict.get('Название', '').strip()
            if not title_raw:
                return None
            
            # Формируем title как в вашем формате (с #)
            title = f"#{title_raw.replace(' ', '_').lower()}" if not title_raw.startswith('#') else title_raw
            
            # Парсим ингредиенты
            ingredients_text = row_dict.get('Ингредиенты', '')
            ingredients = self.parse_ingredients(ingredients_text)
            
            # Парсим шаги
            steps_text = row_dict.get('Шаги приготовления', '')
            steps = self.parse_steps(steps_text)
            
            # Парсим теги
            tags_text = row_dict.get('Теги', '')
            tags = self.parse_tags(tags_text)
            if not tags:
                tags = ["Другое"]
            
            # Режим и время
            mode = row_dict.get('Режим', 'ROAST').strip().upper()
            time_val = row_dict.get('Время', '').strip()
            temperature = row_dict.get('Температура', '').strip()
            if temperature and temperature.lower() != 'null':
                temperature = int(temperature) if temperature.isdigit() else temperature
            else:
                temperature = None
            
            # Создаем raw_text
            raw_text = self.create_raw_text_like_yours(
                title, ingredients, steps, mode, time_val, tags
            )
            
            recipe = {
                "title": title,
                "ingredients": ingredients,
                "mode": mode,
                "temperature": temperature,
                "time": time_val,
                "steps": steps,
                "tags": tags,
                "raw_text": raw_text,
                "for_airfryer": True
            }
            
            return recipe
            
        except Exception as e:
            logging.error(f"Ошибка парсинга строки {row_num}: {e}")
            return None
    
    def parse_ingredients(self, text):
        """Парсит ингредиенты"""
        if not text:
            return []
        
        text = str(text).strip()
        ingredients = []
        
        if '\n' in text:
            items = text.split('\n')
        else:
            items = text.split(',')
        
        for item in items:
            item = item.strip()
            item = re.sub(r'^[•\-*\d\.\s]+', '', item)
            if item:
                ingredients.append(item)
        
        return ingredients
    
    def parse_steps(self, text):
        """Парсит шаги"""
        if not text:
            return []
        
        text = str(text).strip()
        steps = []
        
        if '\n' in text:
            items = text.split('\n')
        else:
            items = text.split('. ')
        
        for item in items:
            item = item.strip()
            item = re.sub(r'^\d+\.\s*', '', item)
            item = re.sub(r'^[•\-*\s]+', '', item)
            if item:
                steps.append(item)
        
        return steps
    
    def parse_tags(self, tags_text):
        """Парсит теги"""
        if not tags_text:
            return ["Другое"]
        
        tags = []
        parts = re.split(r'[,#;\s]+', str(tags_text))
        
        for tag in parts:
            tag = tag.strip().lstrip('#')
            if tag and len(tag) > 1 and tag not in tags:
                tags.append(tag)
        
        return tags if tags else ["Другое"]
    
    def create_raw_text_like_yours(self, title, ingredients, steps, mode, time_val, tags):
        """Создает raw_text"""
        lines = []
        
        lines.append("[3:35]")
        lines.append(title)
        lines.append("")
        
        lines.append("Ингредиенты:")
        for ing in ingredients:
            lines.append(f"• {ing}")
        lines.append("")
        
        lines.append(f"Режим: {mode}")
        lines.append(f"Время: {time_val}")
        lines.append("")
        
        lines.append("Процесс приготовления:")
        lines.append("")
        for step in steps:
            lines.append(f"• {step}")
        lines.append("")
        
        lines.append("Приятного аппетита ❤️")
        lines.append("")
        
        for tag in tags:
            if not tag.startswith('#'):
                lines.append(f"#{tag}")
            else:
                lines.append(tag)
        
        return '\n'.join(lines)
    
    def your_format_to_row(self, recipe):
        """Конвертирует ваш формат в строку для Google Sheets"""
        title = recipe.get('title', '').lstrip('#').replace('_', ' ').title()
        ingredients = '\n'.join(recipe.get('ingredients', []))
        steps = '\n'.join(recipe.get('steps', []))
        tags = ', '.join([t.lstrip('#') for t in recipe.get('tags', [])])
        mode = recipe.get('mode', 'ROAST')
        temperature = str(recipe.get('temperature', '')) if recipe.get('temperature') else ''
        time_val = recipe.get('time', '')
        
        return [title, ingredients, steps, tags, mode, temperature, time_val]
    
    
    
    def recipes_are_different(self, recipe1, recipe2):
        """Сравнивает два рецепта"""
        fields = ['ingredients', 'steps', 'tags', 'mode', 'time']
        for field in fields:
            if recipe1.get(field) != recipe2.get(field):
                return True
        return False
    
    def get_state_hash(self, recipes):
        """Создает хеш состояния для сравнения"""
        if not recipes:
            return None
        
        sorted_recipes = sorted(recipes, key=lambda x: x.get('title', ''))
        simplified = []
        for r in sorted_recipes:
            simplified.append({
                'title': r.get('title', ''),
                'ingredients': r.get('ingredients', []),
                'steps': r.get('steps', []),
                'tags': r.get('tags', []),
                'mode': r.get('mode', ''),
                'time': r.get('time', '')
            })
        
        return hashlib.md5(json.dumps(simplified, sort_keys=True).encode()).hexdigest()
    
    def add_recipes_to_sheet_batch(self, recipes):
        """
        Пакетное добавление рецептов в таблицу
        """
        if not recipes:
            return 0
            
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.get_worksheet(0)
            
            # Преобразуем все рецепты в строки таблицы
            rows_to_add = []
            for recipe in recipes:
                rows_to_add.append(self.your_format_to_row(recipe))
            
            # Добавляем ВСЕ строки одним запросом
            worksheet.append_rows(rows_to_add)
            
            logging.info(f"✅ Добавлено {len(recipes)} рецептов в таблицу")
            return len(recipes)
            
        except Exception as e:
            logging.error(f"Ошибка добавления: {e}")
            return 0
    
    def update_recipe_in_sheet(self, recipe):
        """Обновляет рецепт в таблице"""
        try:
            if '_sheet_row' not in recipe:
                return False
                
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.get_worksheet(0)
            
            row_num = recipe['_sheet_row']
            new_row = self.your_format_to_row(recipe)
            
            for col_num, value in enumerate(new_row, start=1):
                worksheet.update_cell(row_num, col_num, value)
            
            return True
            
        except Exception as e:
            logging.error(f"Ошибка обновления в таблице: {e}")
            return False
    
    def delete_recipe_from_sheet(self, recipe):
        """Удаляет рецепт из таблицы (очищает строку)"""
        try:
            if '_sheet_row' not in recipe:
                return False
                
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.get_worksheet(0)
            
            row_num = recipe['_sheet_row']
            
            # Очищаем строку
            for col_num in range(1, 8):
                worksheet.update_cell(row_num, col_num, '')
            
            return True
            
        except Exception as e:
            logging.error(f"Ошибка удаления из таблицы: {e}")
            return False
    
    def save_recipes_to_file(self, recipes):
        """Сохраняет рецепты в JSON файл"""
        try:
            # Убираем служебные поля
            clean_recipes = []
            for r in recipes:
                clean_r = r.copy()
                clean_r.pop('_sheet_row', None)
                clean_recipes.append(clean_r)
            
            with open(self.recipes_file, 'w', encoding='utf-8') as f:
                json.dump(clean_recipes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Ошибка сохранения файла: {e}")
    
    def normalize_title(self, title):
        """Приводит название к единому стандарту для точного сравнения"""
        if not title:
            return ""
        return str(title).lower().replace('_', ' ').replace('#', '').strip()

    def rewrite_entire_sheet(self, recipes):
        """Полностью очищает таблицу и записывает чистый список без дубликатов"""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            worksheet = client.open_by_url(self.spreadsheet_url).get_worksheet(0)
            
            # Заголовки таблицы
            headers = ["Название", "Ингредиенты", "Шаги приготовления", "Теги", "Режим", "Температура", "Время"]
            rows_to_add = [headers]
            
            for recipe in recipes:
                rows_to_add.append(self.your_format_to_row(recipe))
            
            logging.info("🧹 Очистка таблицы от хаоса и пустых строк...")
            worksheet.clear()
            worksheet.append_rows(rows_to_add)
            logging.info(f"✅ Таблица перезаписана: {len(recipes)} уникальных рецептов")
            
        except Exception as e:
            logging.error(f"Ошибка при перезаписи таблицы: {e}")

    def merge_all_recipes(self):
        """
        ПЕРВИЧНОЕ СЛИЯНИЕ - жестко удаляет дубликаты и наводит порядок
        """
        logging.info("🔄 ЗАПУСК ПЕРВИЧНОГО СЛИЯНИЯ И ОЧИСТКИ ОТ ДУБЛИКАТОВ")
        
        file_recipes = self.load_recipes_from_file()
        sheet_recipes = self.load_recipes_from_sheet()
        
        unique_recipes = {}
        
        # 1. Загружаем из файла
        for r in file_recipes:
            title_key = self.normalize_title(r.get('title', ''))
            if title_key:
                unique_recipes[title_key] = r
                
        # 2. Загружаем из таблицы. 
        # Если есть дубликат, версия из таблицы ПЕРЕЗАПИШЕТ файл 
        # (исходим из того, что в таблице данные редактировались руками и они свежее)
        for r in sheet_recipes:
            title_key = self.normalize_title(r.get('title', ''))
            if title_key:
                unique_recipes[title_key] = r

        # Формируем итоговый чистый список
        final_recipes = list(unique_recipes.values())
        
        # Убираем служебный ключ _sheet_row перед сохранением
        for r in final_recipes:
            r.pop('_sheet_row', None)

        logging.info(f"📊 ИТОГ: найдено {len(final_recipes)} уникальных рецептов")

        # Перезаписываем оба источника начисто
        self.save_recipes_to_file(final_recipes)
        self.rewrite_entire_sheet(final_recipes)
        
        # Обновляем состояние для мониторинга
        self.last_file_state = self.get_state_hash(final_recipes)
        # Загружаем заново, чтобы получить актуальные _sheet_row
        self.last_sheet_state = self.get_state_hash(self.load_recipes_from_sheet())
        
        return final_recipes

    def sync_changes(self):
        """
        СИНХРОНИЗАЦИЯ ИЗМЕНЕНИЙ (Приоритет у Google Таблицы)
        """
        try:
            current_file_recipes = self.load_recipes_from_file()
            current_sheet_recipes = self.load_recipes_from_sheet()
            
            current_file_state = self.get_state_hash(current_file_recipes)
            current_sheet_state = self.get_state_hash(current_sheet_recipes)
            
            if current_file_state == self.last_file_state and current_sheet_state == self.last_sheet_state:
                return # Изменений нет
            
            logging.info("📊 Обнаружены изменения, синхронизация...")
            
            # Собираем словари
            file_dict = {self.normalize_title(r.get('title', '')): r for r in current_file_recipes}
            sheet_dict = {self.normalize_title(r.get('title', '')): r for r in current_sheet_recipes}
            
            # 1. Если изменилась таблица (кто-то отредактировал руками)
            if current_sheet_state != self.last_sheet_state:
                logging.info("📝 Замечено изменение в Google Таблице. Переносим в файл...")
                for title_key, sheet_r in sheet_dict.items():
                    if not title_key: continue
                    
                    if title_key in file_dict:
                        # Если рецепт есть и там и там, но отличается -> берем из таблицы
                        if self.recipes_are_different(file_dict[title_key], sheet_r):
                            logging.info(f"  🔄 Обновлен рецепт: {sheet_r['title']}")
                            file_dict[title_key] = sheet_r
                    else:
                        # Если в таблице появился новый рецепт
                        logging.info(f"  ➕ Новый из таблицы: {sheet_r['title']}")
                        file_dict[title_key] = sheet_r

            # 2. Если парсер добавил что-то новое в JSON файл
            if current_file_state != self.last_file_state:
                to_sheet = []
                for title_key, file_r in file_dict.items():
                    if title_key not in sheet_dict:
                        to_sheet.append(file_r)
                        logging.info(f"  📤 Отправляем в таблицу новый рецепт: {file_r['title']}")
                
                if to_sheet:
                    self.add_recipes_to_sheet_batch(to_sheet)

            # Формируем итоговый список и сохраняем
            final_recipes = list(file_dict.values())
            for r in final_recipes:
                r.pop('_sheet_row', None)
                
            self.save_recipes_to_file(final_recipes)
            
            # Обновляем хеши
            self.last_file_state = self.get_state_hash(final_recipes)
            self.last_sheet_state = self.get_state_hash(self.load_recipes_from_sheet())
            
            logging.info(f"✅ Синхронизация завершена. Всего: {len(final_recipes)} рецептов")
            
        except Exception as e:
            logging.error(f"Ошибка при синхронизации: {e}")
    
    def remove_duplicates(self, recipes):
        """
        Удаляет дубликаты рецептов по названию
        Возвращает список уникальных рецептов
        """
        unique_recipes = []
        seen_titles = set()
        duplicates_found = 0
        
        for recipe in recipes:
            # Нормализуем название для сравнения
            title_key = recipe['title'].lower().lstrip('#').strip()
            
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_recipes.append(recipe)
            else:
                duplicates_found += 1
                logging.warning(f"  ⚠️ Дубликат удален: {recipe['title']}")
        
        if duplicates_found > 0:
            logging.info(f"🗑️ Удалено дубликатов: {duplicates_found}")
        
        return unique_recipes

    def clean_duplicates_in_sheet(self):
        """
        Очищает таблицу от дубликатов
        """
        try:
            logging.info("🔍 Проверка таблицы на дубликаты...")
            
            # Загружаем все рецепты из таблицы
            sheet_recipes = self.load_recipes_from_sheet()
            if not sheet_recipes:
                return
            
            # Группируем по названиям
            recipes_by_title = {}
            for recipe in sheet_recipes:
                title_key = recipe['title'].lower().lstrip('#').strip()
                if title_key not in recipes_by_title:
                    recipes_by_title[title_key] = []
                recipes_by_title[title_key].append(recipe)
            
            # Находим дубликаты
            duplicates_to_remove = []
            for title_key, recipes in recipes_by_title.items():
                if len(recipes) > 1:
                    # Оставляем первый, остальные помечаем на удаление
                    logging.warning(f"  ⚠️ Найдено {len(recipes)} дубликатов: {recipes[0]['title']}")
                    for recipe in recipes[1:]:  # Пропускаем первый
                        if '_sheet_row' in recipe:
                            duplicates_to_remove.append(recipe)
            
            # Удаляем дубликаты
            if duplicates_to_remove:
                logging.info(f"🗑️ Удаление {len(duplicates_to_remove)} дубликатов из таблицы...")
                self.delete_recipes_from_sheet_batch(duplicates_to_remove)
                logging.info(f"✅ Таблица очищена от дубликатов")
            else:
                logging.info("✅ В таблице дубликатов не найдено")
                
        except Exception as e:
            logging.error(f"Ошибка при очистке таблицы: {e}")

    def clean_duplicates_in_file(self):
        """
        Очищает файл от дубликатов
        """
        try:
            logging.info("🔍 Проверка файла на дубликаты...")
            
            # Загружаем рецепты из файла
            file_recipes = self.load_recipes_from_file()
            if not file_recipes:
                return
            
            # Удаляем дубликаты
            original_count = len(file_recipes)
            unique_recipes = self.remove_duplicates(file_recipes)
            
            if len(unique_recipes) < original_count:
                self.save_recipes_to_file(unique_recipes)
                logging.info(f"✅ Файл очищен от дубликатов: {original_count} → {len(unique_recipes)}")
            else:
                logging.info("✅ В файле дубликатов не найдено")
                
        except Exception as e:
            logging.error(f"Ошибка при очистке файла: {e}")
    def delete_recipes_from_sheet_batch(self, recipes):
        """
        Пакетное удаление рецептов из таблицы
        """
        if not recipes:
            return 0
            
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=self.scope
            )
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.get_worksheet(0)
            
            deleted = 0
            for recipe in recipes:
                if '_sheet_row' in recipe:
                    row_num = recipe['_sheet_row']
                    # Очищаем строку
                    for col_num in range(1, 8):
                        worksheet.update_cell(row_num, col_num, '')
                    deleted += 1
                    time.sleep(0.1)  # Маленькая задержка
            
            logging.info(f"🗑️ Удалено {deleted} строк из таблицы")
            return deleted
            
        except Exception as e:
            logging.error(f"Ошибка удаления: {e}")
            return 0
    def run(self):
        """Запускает синхронизатор"""
        logging.info("🚀 ЗАПУСК СИНХРОНИЗАТОРА")
        logging.info("="*60)
        
        # ШАГ 1: Первичное слияние всех рецептов
        logging.info("ЭТАП 1: Первичное слияние файла и таблицы")
        merged_recipes = self.merge_all_recipes()
        
        logging.info("="*60)
        logging.info(f"✅ После слияния: {len(merged_recipes)} уникальных рецептов")
        logging.info("="*60)
        
        # ШАГ 2: Запуск мониторинга изменений
        logging.info("ЭТАП 2: Мониторинг изменений")
        logging.info(f"⏰ Проверка каждые {self.check_interval} секунд")
        logging.info("="*60)
        
        # Настраиваем расписание
        schedule.every(self.check_interval).seconds.do(self.sync_changes)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("🛑 Синхронизатор остановлен")
            sys.exit(0)


# ЗАПУСК
if __name__ == "__main__":
    synchronizer = RecipeSynchronizer()
    synchronizer.run()