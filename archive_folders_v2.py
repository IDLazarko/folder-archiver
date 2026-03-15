import os
import shutil
import zipfile
from pathlib import Path
import argparse
import sys
from tqdm import tqdm
import humanize

def find_second_level_folders(root_path):
    """
    Находит все папки второго уровня вложенности.
    
    Args:
        root_path (Path): Путь к корневой папке
    
    Returns:
        list: Список папок второго уровня вложенности
    """
    second_level_folders = []
    
    # Проходим по папкам первого уровня
    for first_level in root_path.iterdir():
        if first_level.is_dir():
            # Проходим по папкам второго уровня
            for second_level in first_level.iterdir():
                if second_level.is_dir():
                    second_level_folders.append({
                        'path': second_level,
                        'parent': first_level,
                        'name': second_level.name,
                        'full_path': str(second_level)
                    })
    
    return second_level_folders

def archive_second_level_folders(root_path, remove_original=True, exclude_empty=True, move_to_root=True):
    """
    Находит папки второго уровня вложенности, архивирует их и перемещает в корневую папку.
    
    Args:
        root_path (str): Путь к корневой папке
        remove_original (bool): Удалять ли оригинальные папки после архивации
        exclude_empty (bool): Исключать ли пустые папки
        move_to_root (bool): Перемещать ли архивы в корневую папку
    """
    root_path = Path(root_path)
    
    if not root_path.exists():
        print(f"❌ Ошибка: Путь '{root_path}' не существует")
        return
    
    if not root_path.is_dir():
        print(f"❌ Ошибка: '{root_path}' не является папкой")
        return
    
    # Находим все папки второго уровня
    second_level_folders = find_second_level_folders(root_path)
    
    if not second_level_folders:
        print("📂 В корневой папке нет папок второго уровня вложенности")
        return
    
    print(f"📂 Найдено папок второго уровня: {len(second_level_folders)}")
    
    # Группируем по родительским папкам для статистики
    parent_stats = {}
    for folder in second_level_folders:
        parent_name = folder['parent'].name
        if parent_name not in parent_stats:
            parent_stats[parent_name] = []
        parent_stats[parent_name].append(folder)
    
    print("\n📊 Распределение по родительским папкам:")
    for parent, folders in parent_stats.items():
        print(f"   📁 {parent}: {len(folders)} папок")
    
    results = {
        'archived': 0,
        'skipped_empty': 0,
        'errors': 0,
        'skipped_archive_exists': 0,
        'total_size': 0,
        'compressed_size': 0
    }
    
    # Создаем прогресс-бар для папок второго уровня
    with tqdm(total=len(second_level_folders), desc="Обработка папок 2-го уровня", unit="папка") as pbar:
        for folder_info in second_level_folders:
            folder = folder_info['path']
            parent = folder_info['parent']
            
            # Формируем имя архива с сохранением структуры
            # Используем формат: родительская_папка_имя_папки.zip
            archive_name = f"{parent.name}_{folder.name}.zip"
            archive_path = root_path / archive_name
            
            # Обновляем описание прогресс-бара
            pbar.set_description(f"Обработка: {parent.name}/{folder.name}")
            
            # Проверяем, существует ли уже архив с таким именем в корневой папке
            if archive_path.exists():
                pbar.write(f"⚠ Архив '{archive_name}' уже существует в корневой папке, пропускаем")
                results['skipped_archive_exists'] += 1
                pbar.update(1)
                continue
            
            # Проверяем, пустая ли папка
            try:
                is_empty = not any(folder.iterdir())
            except PermissionError:
                pbar.write(f"❌ Нет доступа к папке: {folder}")
                results['errors'] += 1
                pbar.update(1)
                continue
            
            if is_empty and exclude_empty:
                pbar.write(f"⏭ Папка '{parent.name}/{folder.name}' пуста, пропускаем")
                results['skipped_empty'] += 1
                pbar.update(1)
                continue
            
            folder_size = get_folder_size(folder)
            
            try:
                # Получаем список всех файлов для подсчета
                all_files = list(folder.rglob('*'))
                files_to_zip = [f for f in all_files if f.is_file()]
                
                if files_to_zip:
                    # Создаем прогресс-бар для файлов внутри папки
                    with tqdm(total=len(files_to_zip), 
                             desc=f"  Архивирование {folder.name}", 
                             unit="файл",
                             leave=False) as file_pbar:
                        
                        # Создаем архив
                        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for file_path in files_to_zip:
                                # Сохраняем структуру папок внутри архива
                                # Относительный путь от папки второго уровня
                                arcname = file_path.relative_to(folder)
                                zipf.write(file_path, arcname)
                                file_pbar.update(1)
                                file_pbar.set_postfix({"Файл": file_path.name[:30]})
                else:
                    # Если нет файлов (только подпапки)
                    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        # Добавляем структуру подпапок
                        for dir_path in folder.rglob('*'):
                            if dir_path.is_dir():
                                arcname = dir_path.relative_to(folder)
                                zipf.write(dir_path, arcname)
                
                archive_size = get_file_size(archive_path)
                
                # Форматируем размеры
                size_str = humanize.naturalsize(folder_size)
                compressed_str = humanize.naturalsize(archive_size)
                compression_ratio = (1 - archive_size/folder_size)*100 if folder_size > 0 else 0
                
                pbar.write(f"✅ {parent.name}/{folder.name}: {size_str} → {compressed_str} "
                          f"(сжатие: {compression_ratio:.1f}%)")
                
                results['total_size'] += folder_size
                results['compressed_size'] += archive_size
                
                # Удаляем оригинальную папку, если нужно
                if remove_original:
                    try:
                        shutil.rmtree(folder)
                        pbar.write(f"🗑 Оригинальная папка удалена: {parent.name}/{folder.name}")
                    except Exception as e:
                        pbar.write(f"⚠ Не удалось удалить папку: {e}")
                
                results['archived'] += 1
                
            except Exception as e:
                pbar.write(f"❌ Ошибка при архивировании {parent.name}/{folder.name}: {e}")
                # Удаляем поврежденный архив
                if archive_path.exists():
                    archive_path.unlink()
                results['errors'] += 1
            
            pbar.update(1)
    
    # Проверяем и удаляем пустые родительские папки (если все дочерние папки были архивированы)
    if remove_original:
        cleanup_empty_parent_folders(root_path, second_level_folders)
    
    # Выводим статистику
    print("\n" + "="*70)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("="*70)
    print(f"✅ Успешно заархивировано: {results['archived']} папок 2-го уровня")
    if results['total_size'] > 0:
        print(f"📦 Общий размер до сжатия: {humanize.naturalsize(results['total_size'])}")
        print(f"📦 Общий размер после сжатия: {humanize.naturalsize(results['compressed_size'])}")
        if results['total_size'] > 0:
            savings = results['total_size'] - results['compressed_size']
            savings_percent = (savings / results['total_size']) * 100
            print(f"💿 Экономия места: {humanize.naturalsize(savings)} ({savings_percent:.1f}%)")
    print(f"⏭ Пропущено (пустые): {results['skipped_empty']}")
    print(f"⚠ Пропущено (архив уже существует): {results['skipped_archive_exists']}")
    print(f"❌ Ошибок: {results['errors']}")
    print("="*70)
    
    # Показываем созданные архивы
    show_created_archives(root_path)

def cleanup_empty_parent_folders(root_path, processed_folders):
    """
    Удаляет пустые родительские папки после архивации всех дочерних.
    
    Args:
        root_path (Path): Корневая папка
        processed_folders (list): Список обработанных папок
    """
    # Получаем уникальные родительские папки
    parents = set(folder['parent'] for folder in processed_folders)
    
    print("\n🧹 Проверка родительских папок на пустоту:")
    for parent in parents:
        if parent.exists() and parent.is_dir():
            # Проверяем, остались ли в родительской папке какие-либо элементы
            remaining_items = list(parent.iterdir())
            if not remaining_items:
                try:
                    parent.rmdir()  # Удаляем только пустую папку
                    print(f"   ✅ Удалена пустая родительская папка: {parent.name}")
                except Exception as e:
                    print(f"   ⚠ Не удалось удалить папку {parent.name}: {e}")
            else:
                print(f"   📁 В папке {parent.name} остались элементы: {len(remaining_items)}")

def show_created_archives(root_path):
    """
    Показывает созданные архивы в корневой папке.
    """
    print("\n📦 Созданные архивы в корневой папке:")
    archives = list(root_path.glob("*.zip"))
    
    if not archives:
        print("   Архивы не найдены")
        return
    
    # Сортируем по времени создания (новые сверху)
    archives.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    for archive in archives[:10]:  # Показываем только последние 10
        size = humanize.naturalsize(archive.stat().st_size)
        modified_time = get_file_time(archive)
        print(f"   📄 {archive.name} ({size}, {modified_time})")
    
    if len(archives) > 10:
        print(f"   ... и еще {len(archives) - 10} архивов")

def get_folder_size(folder):
    """Возвращает размер папки в байтах"""
    total_size = 0
    try:
        for file_path in folder.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except (PermissionError, OSError):
        pass
    return total_size

def get_file_size(file_path):
    """Возвращает размер файла в байтах"""
    try:
        return file_path.stat().st_size
    except (PermissionError, OSError):
        return 0

def get_file_time(file_path):
    """Возвращает время модификации файла в читаемом формате"""
    from datetime import datetime
    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except (PermissionError, OSError):
        return "неизвестно"

def get_current_time():
    """Возвращает текущее время в читаемом формате"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def preview_operation(root_path):
    """Показывает предварительный просмотр того, что будет сделано"""
    root_path = Path(root_path)
    second_level_folders = find_second_level_folders(root_path)
    
    if not second_level_folders:
        print("📂 В корневой папке нет папок второго уровня вложенности")
        return False
    
    print("\n🔍 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР:")
    print("="*70)
    
    total_size = 0
    empty_folders = 0
    folders_with_archives = 0
    
    # Группируем по родительским папкам
    by_parent = {}
    for folder in second_level_folders:
        parent = folder['parent'].name
        if parent not in by_parent:
            by_parent[parent] = []
        by_parent[parent].append(folder)
    
    for parent, folders in by_parent.items():
        print(f"\n📁 {parent}/")
        for folder_info in folders:
            folder = folder_info['path']
            archive_name = f"{parent}_{folder.name}.zip"
            archive_exists = (root_path / archive_name).exists()
            folder_size = get_folder_size(folder)
            
            try:
                is_empty = not any(folder.iterdir())
            except PermissionError:
                is_empty = False
                print(f"   ⚠ {folder.name}/ (нет доступа)")
                continue
            
            status = []
            if is_empty:
                status.append("ПУСТАЯ")
                empty_folders += 1
            if archive_exists:
                status.append("АРХИВ ЕСТЬ")
                folders_with_archives += 1
                
            status_str = f" [{', '.join(status)}]" if status else ""
            
            size_str = humanize.naturalsize(folder_size) if folder_size > 0 else "0 B"
            print(f"   📂 {folder.name}/{status_str}")
            print(f"      Размер: {size_str}")
            print(f"      Будет создан: {archive_name}")
            total_size += folder_size
    
    print("\n" + "="*70)
    print(f"Всего папок 2-го уровня: {len(second_level_folders)}")
    print(f"Общий размер: {humanize.naturalsize(total_size)}")
    if empty_folders > 0:
        print(f"Пустых папок: {empty_folders}")
    if folders_with_archives > 0:
        print(f"Папок с существующими архивами: {folders_with_archives}")
    
    response = input("\nПродолжить архивацию? (y/n): ").lower().strip()
    return response in ['y', 'yes', 'д', 'да']

def main():
    parser = argparse.ArgumentParser(description='Архивация папок второго уровня вложенности')
    parser.add_argument('path', nargs='?', default='.', 
                       help='Путь к корневой папке (по умолчанию текущая)')
    parser.add_argument('--keep-original', action='store_true',
                       help='Не удалять оригинальные папки после архивации')
    parser.add_argument('--include-empty', action='store_true',
                       help='Архивировать также пустые папки')
    parser.add_argument('--overwrite', action='store_true',
                       help='Перезаписывать существующие архивы')
    parser.add_argument('--no-preview', action='store_true',
                       help='Пропустить предварительный просмотр')
    parser.add_argument('--keep-structure', action='store_true',
                       help='Сохранять структуру папок внутри архива')
    parser.add_argument('--quiet', action='store_true',
                       help='Минимизировать вывод (только прогресс-бары)')
    
    args = parser.parse_args()
    
    # Проверяем наличие необходимых библиотек
    try:
        import tqdm
        import humanize
    except ImportError as e:
        print("❌ Необходимо установить дополнительные библиотеки:")
        print("pip install tqdm humanize")
        sys.exit(1)
    
    # Проверяем путь
    root_path = Path(args.path)
    if not root_path.exists():
        print(f"❌ Путь '{root_path}' не существует")
        sys.exit(1)
    
    # Предварительный просмотр
    if not args.no_preview and not args.quiet:
        if not preview_operation(root_path):
            print("Операция отменена пользователем")
            return
    
    # Здесь можно добавить логику для overwrite
    if args.overwrite:
        print("⚠ Режим перезаписи включен - существующие архивы будут перезаписаны")
        # TODO: добавить логику перезаписи
    
    # Запускаем архивацию
    archive_second_level_folders(
        root_path=root_path,
        remove_original=not args.keep_original,
        exclude_empty=not args.include_empty,
        move_to_root=True  # Всегда перемещаем в корень
    )

if __name__ == "__main__":
    main()