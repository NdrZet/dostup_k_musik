import logging
import os

def setup_logging():
    """
    Настраивает систему логирования для приложения.
    Сообщения уровня DEBUG и выше записываются в файл music_player.log.
    Сообщения уровня INFO и выше выводятся в консоль.
    """
    # Создаем корневой логгер
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG) # Устанавливаем минимальный уровень для обработки

    # Удаляем существующие обработчики, чтобы избежать дублирования
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Обработчик для записи в файл (для всех DEBUG сообщений)
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'music_player.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Обработчик для вывода в консоль (для INFO и выше)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logging.info("Система логирования настроена.")

if __name__ == '__main__':
    # Пример использования для тестирования
    setup_logging()
    logging.debug("Это отладочное сообщение.")
    logging.info("Это информационное сообщение.")
    logging.warning("Это предупреждение.")
    logging.error("Это сообщение об ошибке.")
    logging.critical("Это критическое сообщение.")
