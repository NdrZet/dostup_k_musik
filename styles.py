# styles.py

app_stylesheet = """
QWidget {
    background-color: #444444; /* Общий фон приложения - серый */
    color: white;
}

QLabel {
    color: white;
}

QPushButton {
    background-color: #333333;
    color: white;
    border: none;
    padding: 12px 12px; /* Увеличен padding для круглых кнопок */
    border-radius: 50%; /* Сделано круглым */
}

QPushButton:hover {
    background-color: #555555;
}

QPushButton:pressed {
    background-color: #0056b3;
}

QPushButton:disabled {
    background-color: #1a1a1a;
    color: #888888;
}

QListWidget {
    background-color: #222222;
    color: white;
    border: 1px solid #555555;
    border-radius: 5px;
}

QListWidget::item:selected {
    background-color: #007bff;
    color: white;
}

QListWidget::item:hover {
    background-color: #444444;
}

QSlider::groove:horizontal {
    border: 1px solid #bbb;
    background: white;
    height: 8px;
    border-radius: 4px;
}

QSlider::handle:horizontal {
    background: #007bff;
    border: 1px solid #007bff;
    width: 18px;
    margin: -5px 0;
    border-radius: 50%; /* Изменен на 50% для круглого ползунка */
}
"""
