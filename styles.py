app_stylesheet = """
QWidget {
    background-color: #121212; /* Темно-серый фон для всего приложения */
    color: white; /* Белый цвет текста по умолчанию */
    font-family: Arial, sans-serif;
}

QLabel {
    color: white; /* Цвет текста для меток */
}

QPushButton {
    background-color: #121212; /* Темно-серый фон кнопок */
    color: white; /* Белый текст кнопок */
    border: none;
    padding: 10px 20px;
    border-radius: 8px; /* Скругленные углы кнопок */
    font-weight: bold;
    transition: background-color 0.3s ease; /* Плавный переход для фона */
}

QPushButton:hover {
    background-color: #333333; /* Более светлый фон при наведении */
}

QPushButton:pressed {
    background-color: #1a1a1a; /* Еще более темный фон при нажатии */
}

QPushButton:disabled {
    background-color: #121212; /* Более светлый фон для неактивных кнопок */
    color: #aaaaaa; /* Более тусклый текст для неактивных кнопок */
}

QSlider::groove:horizontal {
    border: 1px solid #444444;
    height: 8px;
    background: #555555;
    margin: 2px 0;
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #ffffff; /* Белый цвет ползунка */
    border: 1px solid #007bff;
    width: 18px;
    margin: -5px 0; /* Увеличиваем размер ползунка */
    border-radius: 9px;
}

QSlider::sub-page:horizontal {
    background: #ffffff; /* Цвет заполненной части ползунка */
    border-radius: 4px;
}

/* Стиль для контейнера левой панели */
QWidget#leftPanel {
    background-color: #121212; /* Немного светлее основного фона для выделения */
    border-top-left-radius: 15px; /* Скругление верхнего левого угла */
    border-bottom-left-radius: 15px; /* Скругление нижнего левого угла */
    border-right: 2px solid #333333; /* Граница справа для отделения от правой панели */
}

QListWidget {
    background-color: #121212; /* Очень темный фон для списка */
    border: 0px solid #333333;
    border-radius: 15px;
    padding: 5px;
}

QListWidget::item {
    background-color: none; /* Фон элемента списка */
    border-radius: 5px;
    margin-bottom: 0px;
    padding: 5px;
}

QListWidget::item:selected {
    background-color: #121212; /* Фон выбранного элемента */
    border: none; /* Убираем обводку */
    border-radius: 5px; /* Сохраняем скругление углов */
}

/* Стиль для QLabel внутри ListItemWidget */
ListItemWidget QLabel {
    background-color: transparent; /* Делаем фон текста прозрачным */
    color: white; /* Убедимся, что цвет текста белый */
}
"""
