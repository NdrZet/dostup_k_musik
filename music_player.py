import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QFileDialog, QLabel, QSlider, QSizePolicy, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QSize
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon
import vlc
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.wavpack import WavPack
from mutagen.id3 import ID3NoHeaderError
import io
import threading
import os

# Общие стили для приложения
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


# Новый пользовательский класс для квадратной метки обложки
class SquareLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Нет обложки")
        self.setStyleSheet("border: none;")  # Убрана обводка

    def heightForWidth(self, width):
        return width

    def widthForHeight(self, height):
        return height

    def sizeHint(self):
        side = min(self.width(), self.height())
        if side <= 0:
            return QSize(150, 150)
        return QSize(side, side)


class MusicPlayer(QWidget):
    media_parsed_signal = pyqtSignal(int)
    library_scan_finished_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ДОСТУП К МУЗЫКЕ")
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(1280, 720)

        # Устанавливаем общую темную тему для окна из переменной app_stylesheet
        self.setStyleSheet(app_stylesheet)

        # Установка иконки приложения
        icon_path = os.path.join(os.path.dirname(__file__), 'media', 'zsxdcvbnjm.ico')
        try:
            self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"Ошибка загрузки иконки: {e}. Убедитесь, что '{icon_path}' существует и доступен.")

        self.media_player = vlc.MediaPlayer()
        self.current_file = None
        self.total_length_ms = 0
        self.original_cover_pixmap = None

        self.library_data = {}
        self.current_library_path = []
        self.root_library_folder = None

        self.is_shuffling = False
        self.is_repeating = False

        self.current_album_tracks = []
        self.current_track_index = -1

        # Пути к файлам иконок
        self.icon_dir = os.path.join(os.path.dirname(__file__), 'media', 'control_panel_track')
        self.play_icon_path = os.path.join(self.icon_dir, 'play.ico')
        self.pause_icon_path = os.path.join(self.icon_dir, 'pause.ico')
        self.prev_icon_path = os.path.join(self.icon_dir, 'prev.ico')
        self.next_icon_path = os.path.join(self.icon_dir, 'next.ico')
        self.shuffle_icon_path = os.path.join(self.icon_dir, 'shuffle.ico')
        self.repeat_icon_path = os.path.join(self.icon_dir, 'repeat.ico')

        self.init_ui()
        self.setup_timer()

        self.media_player.audio_set_volume(50)
        self.volume_slider.setValue(50)

        self.media_parsed_signal.connect(self._on_media_parsed)
        self.library_scan_finished_signal.connect(self._on_library_scan_finished)

        QApplication.instance().installEventFilter(self)

    def init_ui(self):
        root_layout = QHBoxLayout()

        # --- Левая панель (Библиотека) ---
        left_panel_layout = QVBoxLayout()

        self.library_label = QLabel("Моя Музыкальная Библиотека")
        left_panel_layout.addWidget(self.library_label)

        self.add_root_folder_button = QPushButton("Добавить корневую папку")
        self.add_root_folder_button.clicked.connect(self.open_library_folder)
        self.add_root_folder_button.setFocusPolicy(Qt.NoFocus)
        left_panel_layout.addWidget(self.add_root_folder_button)

        self.back_button = QPushButton("Назад")
        self.back_button.clicked.connect(self._navigate_back)
        self.back_button.setEnabled(False)
        self.back_button.setFocusPolicy(Qt.NoFocus)
        left_panel_layout.addWidget(self.back_button)

        self.library_list_widget = QListWidget()
        self.library_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.library_list_widget.itemClicked.connect(self.load_track_from_library)
        left_panel_layout.addWidget(self.library_list_widget)

        root_layout.addLayout(left_panel_layout, 1)

        # --- Правая панель (Плеер) ---
        right_panel_layout = QVBoxLayout()

        # 1. Info layout (cover and track details) - Сверху
        info_layout = QHBoxLayout()
        self.cover_label = SquareLabel()
        self.cover_label.setMinimumSize(50, 50)
        info_layout.addWidget(self.cover_label)
        track_info_layout = QVBoxLayout()
        self.title_label = QLabel("Название: -")
        self.artist_label = QLabel("Исполнитель: -")
        self.album_label = QLabel("Альбом: -")
        self.title_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.artist_label.setFont(QFont("Arial", 14))
        self.album_label.setFont(QFont("Arial", 14))
        track_info_layout.addWidget(self.title_label)
        track_info_layout.addWidget(self.artist_label)
        track_info_layout.addWidget(self.album_label)
        track_info_layout.addStretch(1)
        info_layout.addLayout(track_info_layout)
        right_panel_layout.addLayout(info_layout, 3)

        right_panel_layout.addStretch(1)  # Добавляем растяжку, чтобы прижать контрольную панель к низу

        # Новый контейнер для черной контрольной панели
        self.control_panel_container = QWidget()
        self.control_panel_container.setStyleSheet("background-color: black;")
        control_panel_layout = QVBoxLayout(self.control_panel_container)
        control_panel_layout.setContentsMargins(0, 0, 0, 0)  # Убираем отступы для полного растягивания

        # 2. Playback controls row (shuffle, prev, play/pause, next, repeat) - Строго по центру
        playback_controls_row_layout = QHBoxLayout()
        playback_controls_row_layout.addStretch(1)

        # Кнопки в порядке: Перемешать, Предыдущий, Воспроизвести/Пауза, Следующий, Повтор
        self.shuffle_button = QPushButton()  # Инициализируем без текста
        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        self.shuffle_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.shuffle_button)

        self.prev_track_button = QPushButton()  # Инициализируем без текста
        self.prev_track_button.clicked.connect(self.play_previous_track)
        self.prev_track_button.setEnabled(False)
        self.prev_track_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.prev_track_button)

        self.play_pause_button = QPushButton()  # Инициализируем без текста
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.play_pause_button.setEnabled(False)
        self.play_pause_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.play_pause_button)

        self.next_track_button = QPushButton()  # Инициализируем без текста
        self.next_track_button.clicked.connect(self.play_next_track)
        self.next_track_button.setEnabled(False)
        self.next_track_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.next_track_button)

        self.repeat_button = QPushButton()  # Инициализируем без текста
        self.repeat_button.clicked.connect(self.toggle_repeat)
        self.repeat_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.repeat_button)

        playback_controls_row_layout.addStretch(1)
        control_panel_layout.addLayout(playback_controls_row_layout)  # Добавляем в новый контейнер

        # 3. Position slider
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setEnabled(False)
        control_panel_layout.addWidget(self.position_slider)  # Добавляем в новый контейнер

        # 4. Time labels
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch(1)
        time_layout.addWidget(self.total_time_label)
        control_panel_layout.addLayout(time_layout)  # Добавляем в новый контейнер

        # 5. Bottom-right volume control - Внизу справа
        bottom_right_volume_container = QHBoxLayout()
        bottom_right_volume_container.addStretch(1)

        volume_control_layout = QHBoxLayout()
        self.volume_label = QLabel("Громкость: 50%")
        volume_control_layout.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.sliderMoved.connect(self.set_volume)
        self.volume_slider.setFocusPolicy(Qt.NoFocus)
        self.volume_slider.installEventFilter(self)
        volume_control_layout.addWidget(self.volume_slider)

        bottom_right_volume_container.addLayout(volume_control_layout)
        control_panel_layout.addLayout(bottom_right_volume_container)  # Добавляем в новый контейнер

        right_panel_layout.addWidget(self.control_panel_container)  # Добавляем контейнер в правую панель

        root_layout.addLayout(right_panel_layout, 3)

        self.setLayout(root_layout)
        self._update_font_sizes()
        # Инициализируем иконки для кнопок
        self.shuffle_button.setIcon(QIcon(self.shuffle_icon_path))
        self.prev_track_button.setIcon(QIcon(self.prev_icon_path))
        self.next_track_button.setIcon(QIcon(self.next_icon_path))
        self.repeat_button.setIcon(QIcon(self.repeat_icon_path))

        self._update_button_style(self.shuffle_button, self.is_shuffling)
        self._update_button_style(self.prev_track_button, False)  # Prev button is never "active" in terms of color
        self._update_play_pause_button_style()
        self._update_button_style(self.next_track_button, False)  # Next button is never "active" in terms of color
        self._update_button_style(self.repeat_button, self.is_repeating)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def update_ui(self):
        if not self.position_slider.isSliderDown():
            current_state = self.media_player.get_state()
            # _update_play_pause_button_style() теперь вызывается только при изменении состояния плеера
            # чтобы избежать "дергания" кнопки.

            if current_state == vlc.State.Playing or current_state == vlc.State.Paused:
                current_time = self.media_player.get_time()
                if self.total_length_ms > 0:
                    position = int((current_time / self.total_length_ms) * 1000)
                    self.position_slider.setValue(position)

                self.current_time_label.setText(self.format_time(current_time))
            elif current_state == vlc.State.Ended:
                self.play_next_track()
                if self.media_player.get_state() == vlc.State.Ended:
                    self.stop_music()

    def format_time(self, ms):
        seconds = int(ms / 1000)
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02}:{seconds:02}"

    def open_file(self, file_path):
        if not file_path:
            print("Ошибка: Не указан путь к файлу для открытия.")
            self.stop_music()
            return

        if self.media_player.is_playing() or self.media_player.get_state() == vlc.State.Paused:
            self.media_player.stop()

        self.current_file = file_path

        self.title_label.setText("Название: -")
        self.artist_label.setText("Исполнитель: -")
        self.album_label.setText("Альбом: -")
        self.cover_label.setText("Нет обложки")
        self.cover_label.setPixmap(QPixmap())
        self.original_cover_pixmap = None

        media = vlc.Media(self.current_file)
        self.media_player.set_media(media)

        self.read_metadata(file_path)

        self.position_slider.setEnabled(True)
        self.play_pause_button.setEnabled(True)
        self.prev_track_button.setEnabled(True)
        self.next_track_button.setEnabled(True)
        self.shuffle_button.setEnabled(True)
        self.repeat_button.setEnabled(True)

        threading.Thread(target=self._parse_media_in_thread, args=(self.current_file,)).start()

        self.play_music()

    def _parse_media_in_thread(self, file_path):
        try:
            temp_media = vlc.Media(file_path)
            temp_media.parse()

            total_duration = temp_media.get_duration()
            self.media_parsed_signal.emit(total_duration)
        except Exception as e:
            print(f"Ошибка парсинга медиа в потоке: {e}")
            self.media_parsed_signal.emit(0)

    def _on_media_parsed(self, total_length_ms):
        self.total_length_ms = total_length_ms
        self.total_time_label.setText(self.format_time(self.total_length_ms))
        self.position_slider.setValue(0)

    def read_metadata(self, file_path):
        try:
            audio = None
            if file_path.lower().endswith('.mp3'):
                audio = MP3(file_path)
            elif file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
            elif file_path.lower().endswith('.wav'):
                print(f"Примечание: Метаданные для WAV-файлов (кроме WavPack) могут быть недоступны: {file_path}")
                return
            else:
                return

            if audio:
                title = audio.get('TIT2', audio.get('title', ['-']))[0] if audio.get('TIT2') or audio.get(
                    'title') else '-'
                artist = audio.get('TPE1', audio.get('artist', ['-']))[0] if audio.get('TPE1') or audio.get(
                    'artist') else '-'
                album = audio.get('TALB', audio.get('album', ['-']))[0] if audio.get('TALB') or audio.get(
                    'album') else '-'

                self.title_label.setText(f"Название: {title}")
                self.artist_label.setText(f"Исполнитель: {artist}")
                self.album_label.setText(f"Альбом: {album}")

                pixmap = QPixmap()
                if file_path.lower().endswith('.mp3'):
                    for tag in audio.getall('APIC'):
                        if tag.type == 3:
                            pixmap.loadFromData(tag.data)
                            self.original_cover_pixmap = pixmap
                            break
                elif file_path.lower().endswith('.flac') and audio.pictures:
                    for pic in audio.pictures:
                        if pic.type == 3:
                            image = QImage.fromData(pic.data)
                            if not image.isNull():
                                pixmap = QPixmap.fromImage(image)
                                self.original_cover_pixmap = pixmap
                                break

                self._update_cover_display()

        except ID3NoHeaderError:
            print(f"Нет ID3 тегов для {file_path}. Возможно, это не MP3 или теги отсутствуют.")
            self.title_label.setText("Название: (Нет тегов)")
            self.artist_label.setText("Исполнитель: (Нет тегов)")
            self.album_label.setText("Альбом: (Нет тегов)")
            self.original_cover_pixmap = None
            self._update_cover_display()
        except Exception as e:
            print(f"Ошибка чтения метаданных для {file_path}: {e}")
            self.title_label.setText("Название: (Ошибка чтения)")
            self.artist_label.setText("Исполнитель: (Ошибка чтения)")
            self.album_label.setText("Альбом: (Ошибка чтения)")
            self.original_cover_pixmap = None
            self._update_cover_display()

    def _update_cover_display(self):
        if self.original_cover_pixmap:
            scaled_pixmap = self.original_cover_pixmap.scaled(self.cover_label.size(),
                                                              Qt.KeepAspectRatio,
                                                              Qt.SmoothTransformation)
            self.cover_label.setPixmap(scaled_pixmap)
            self.cover_label.setText("")
        else:
            self.cover_label.setText("Нет обложки")
            self.cover_label.setPixmap(QPixmap())

    def _update_font_sizes(self):
        window_side = min(self.width(), self.height())
        base_font_size = max(8, int(window_side * 0.01))

        title_font_size = base_font_size + 2
        artist_album_font_size = base_font_size

        self.title_label.setFont(QFont("Arial", title_font_size, QFont.Bold))
        self.artist_label.setFont(QFont("Arial", artist_album_font_size))
        self.album_label.setFont(QFont("Arial", artist_album_font_size))

        button_font_size = max(8, int(window_side * 0.007))
        font = QFont("Arial", button_font_size)
        self.add_root_folder_button.setFont(font)
        self.back_button.setFont(font)

        # Устанавливаем размер иконок для кнопок воспроизведения/паузы и переключения треков
        icon_size = max(24, int(window_side * 0.03))  # Увеличил размер иконки

        # Устанавливаем фиксированный размер для кнопок управления воспроизведением
        # Увеличил размер, чтобы соответствовать новому padding и круглой форме
        button_fixed_size = max(50, int(window_side * 0.06))

        # Применяем размер иконок и фиксированный размер кнопок
        for button in [self.play_pause_button, self.prev_track_button, self.next_track_button,
                       self.shuffle_button, self.repeat_button]:
            button.setIconSize(QSize(icon_size, icon_size))
            button.setFixedSize(button_fixed_size, button_fixed_size)

        time_label_font_size = max(8, int(window_side * 0.007))
        time_font = QFont("Arial", time_label_font_size)
        self.current_time_label.setFont(time_font)
        self.total_time_label.setFont(time_font)

        self.library_label.setFont(QFont("Arial", base_font_size, QFont.Bold))
        self.volume_label.setFont(time_font)

        # Обновляем стили кнопок после изменения размера шрифта (только фон)
        self._update_button_style(self.shuffle_button, self.is_shuffling)
        # _update_button_style(self.prev_track_button, False) # Удалено, чтобы prev и next не имели заливки
        self._update_play_pause_button_style()
        # _update_button_style(self.next_track_button, False) # Удалено, чтобы prev и next не имели заливки
        self._update_button_style(self.repeat_button, self.is_repeating)

        # Устанавливаем стиль для prev и next без заливки
        self.prev_track_button.setStyleSheet("background-color: #333333; color: transparent;")
        self.next_track_button.setStyleSheet("background-color: #333333; color: transparent;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_cover_display)
        QTimer.singleShot(0, self._update_font_sizes)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            QTimer.singleShot(0, self._update_cover_display)
            QTimer.singleShot(0, self._update_font_sizes)
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        """
        Фильтр событий для обработки прокрутки колесика мыши на ползунке громкости
        и для глобальной обработки нажатия клавиши пробел.
        """
        if obj == self.volume_slider and event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            current_volume = self.volume_slider.value()

            if delta > 0:
                new_volume = min(100, current_volume + 5)
            else:
                new_volume = max(0, current_volume - 5)

            self.volume_slider.setValue(new_volume)
            self.set_volume(new_volume)
            return True

        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.toggle_play_pause()
            return True

        return super().eventFilter(obj, event)

    def toggle_play_pause(self):
        """Переключает воспроизведение/паузу."""
        if self.current_file is None:
            return
        # Проверяем текущее состояние медиаплеера
        current_state = self.media_player.get_state()
        if current_state == vlc.State.Playing:
            self.pause_music()
        elif current_state == vlc.State.Paused:
            self.play_music()
        else:  # Если плеер остановлен или еще не начал воспроизведение
            self.play_music()

    def play_music(self):
        if self.current_file:
            self.media_player.play()
            self._update_play_pause_button_style()
            self.play_pause_button.setEnabled(True)
            self.timer.start()

    def pause_music(self):
        # Проверяем, играет ли медиа, чтобы правильно установить иконку
        if self.media_player.get_state() == vlc.State.Playing:
            self.media_player.pause()
        self._update_play_pause_button_style()  # Обновляем стиль кнопки
        self.play_pause_button.setEnabled(True)
        self.timer.stop()

    def stop_music(self):
        """Останавливает воспроизведение и сбрасывает состояние плеера."""
        self.media_player.stop()
        self.position_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.timer.stop()

        self._update_play_pause_button_style()
        self.play_pause_button.setEnabled(False)
        self.prev_track_button.setEnabled(False)
        self.next_track_button.setEnabled(False)
        self.shuffle_button.setEnabled(False)
        self.repeat_button.setEnabled(False)
        self.current_album_tracks = []
        self.current_track_index = -1

    def set_position(self, position):
        if self.media_player.is_playing() and self.total_length_ms > 0:
            new_time_ms = int(self.total_length_ms * (position / 1000.0))
            self.media_player.set_time(new_time_ms)

    def set_volume(self, volume):
        """Устанавливает громкость медиаплеера и обновляет метку."""
        self.media_player.audio_set_volume(volume)
        self.volume_label.setText(f"Громкость: {volume}%")

    def toggle_shuffle(self):
        """Переключает режим перемешивания."""
        self.is_shuffling = not self.is_shuffling
        self._update_button_style(self.shuffle_button, self.is_shuffling)
        print(f"Режим перемешивания: {'Включен' if self.is_shuffling else 'Выключен'}")

    def toggle_repeat(self):
        """Переключает режим повтора."""
        self.is_repeating = not self.is_repeating
        self._update_button_style(self.repeat_button, self.is_repeating)
        print(f"Режим повтора: {'Включен' if self.is_repeating else 'Выключен'}")

    def _update_button_style(self, button, is_active):
        """Применяет стиль к кнопке в зависимости от ее состояния активности."""
        if is_active:
            button.setStyleSheet(f"background-color: #007bff; color: transparent;")  # Добавлено color: transparent
        else:
            button.setStyleSheet(f"background-color: #333333; color: transparent;")  # Добавлено color: transparent

    def _update_play_pause_button_style(self):
        """Обновляет стиль и текст кнопки воспроизведения/паузы."""
        current_state = self.media_player.get_state()

        # Логика отображения иконки воспроизведения/паузы
        if current_state == vlc.State.Playing:
            self.play_pause_button.setIcon(QIcon(self.pause_icon_path))  # Устанавливаем иконку паузы
        else:
            self.play_pause_button.setIcon(QIcon(self.play_icon_path))  # Устанавливаем иконку воспроизведения

        # Фон всегда белый
        self.play_pause_button.setStyleSheet(f"background-color: white; color: transparent;")

    def open_library_folder(self):
        """Открывает диалог выбора папки и сканирует ее на наличие музыкальных файлов."""
        folder_path = QFileDialog.getExistingDirectory(self, "Выбрать корневую папку с музыкой")
        if folder_path:
            self.root_library_folder = folder_path
            self.library_list_widget.clear()
            self.library_data.clear()
            self.current_library_path = []
            self.back_button.setEnabled(False)

            supported_extensions = ('.mp3', '.flac', '.wav')

            threading.Thread(target=self._scan_music_folder_in_thread, args=(folder_path, supported_extensions)).start()

    def _scan_music_folder_in_thread(self, current_folder, supported_extensions):
        """
        Сканирует указанную папку на наличие музыкальных файлов и строит древовидную структуру.
        """
        library_structure = {}

        for root, dirs, files in os.walk(current_folder):
            relative_root = os.path.relpath(root, current_folder)
            if relative_root == ".":
                current_node = library_structure
            else:
                path_parts = relative_root.split(os.sep)
                current_node = library_structure
                for part in path_parts:
                    if part not in current_node:
                        current_node[part] = {}
                    current_node = current_node[part]

            for file in files:
                if file.lower().endswith(supported_extensions):
                    full_path = os.path.join(root, file)
                    current_node[file] = full_path

        self.library_scan_finished_signal.emit(library_structure)

    def _on_library_scan_finished(self, library_structure):
        self.library_data = library_structure
        self._display_current_library_level()

    def _display_current_library_level(self):
        """
        Отображает содержимое текущего уровня библиотеки в QListWidget.
        """
        self.library_list_widget.clear()
        current_node = self.library_data

        for part in self.current_library_path:
            if part in current_node:
                current_node = current_node[part]
            else:
                self.current_library_path = []
                current_node = self.library_data
                break

        list_item_font_size = max(8, int(min(self.width(), self.height()) * 0.006))
        list_item_font = QFont("Arial", list_item_font_size)

        folders = sorted([k for k, v in current_node.items() if isinstance(v, dict)])
        for folder_name in folders:
            item = QListWidgetItem(folder_name)
            item.setFont(list_item_font)
            item.setData(Qt.UserRole, "folder")
            self.library_list_widget.addItem(item)

        files = sorted([k for k, v in current_node.items() if isinstance(v, str)])
        for file_name in files:
            display_name = os.path.splitext(file_name)[0]
            item = QListWidgetItem(display_name)
            item.setFont(list_item_font)
            item.setData(Qt.UserRole, "file")
            item.setData(Qt.UserRole + 1, file_name)
            self.library_list_widget.addItem(item)

        if not folders and not files:
            item = QListWidgetItem("Пусто.")
            item.setFont(list_item_font)
            self.library_list_widget.addItem(item)

        self.back_button.setEnabled(len(self.current_library_path) > 0)

    def load_track_from_library(self, item):
        """
        Загружает и воспроизводит трек или переходит в папку, выбранную из списка библиотеки.
        """
        item_type = item.data(Qt.UserRole)

        if item_type == "folder":
            folder_name = item.text()
            self.current_library_path.append(folder_name)
            self._display_current_library_level()
        elif item_type == "file":
            full_file_name = item.data(Qt.UserRole + 1)
            current_node = self.library_data
            for part in self.current_library_path:
                current_node = current_node[part]

            album_files = sorted([k for k, v in current_node.items() if isinstance(v, str)])
            self.current_album_tracks = album_files

            try:
                self.current_track_index = self.current_album_tracks.index(full_file_name)
            except ValueError:
                self.current_track_index = -1

            full_path = current_node.get(full_file_name)
            if full_path:
                self.open_file(full_path)
            else:
                print(f"Ошибка: Не удалось найти полный путь для файла: {full_file_name}")
        else:
            print(f"Неизвестный тип элемента: {item.text()}")

    def _navigate_back(self):
        """
        Возвращается на предыдущий уровень в иерархии библиотеки.
        """
        if self.current_library_path:
            self.current_library_path.pop()
            self._display_current_library_level()

    def play_next_track(self):
        """
        Воспроизводит следующий трек в текущем альбоме/папке.
        """
        if not self.current_album_tracks or self.current_track_index == -1:
            print("Нет контекста альбома или трек не воспроизводится из библиотеки.")
            return

        next_index = self.current_track_index + 1
        if next_index >= len(self.current_album_tracks):
            next_index = 0

        next_file_name = self.current_album_tracks[next_index]

        current_node = self.library_data
        for part in self.current_library_path:
            current_node = current_node[part]

        full_path = current_node.get(next_file_name)
        if full_path:
            self.current_track_index = next_index
            self.open_file(full_path)
        else:
            print(f"Ошибка: Не удалось найти следующий трек: {next_file_name}")

    def play_previous_track(self):
        """
        Воспроизводит предыдущий трек в текущем альбоме/папке.
        """
        if not self.current_album_tracks or self.current_track_index == -1:
            print("Нет контекста альбома или трек не воспроизводится из библиотеки.")
            return

        prev_index = self.current_track_index - 1
        if prev_index < 0:
            prev_index = len(self.current_album_tracks) - 1

        prev_file_name = self.current_album_tracks[prev_index]

        current_node = self.library_data
        for part in self.current_library_path:
            current_node = current_node[part]

        full_path = current_node.get(prev_file_name)
        if full_path:
            self.current_track_index = prev_index
            self.open_file(full_path)
        else:
            print(f"Ошибка: Не удалось найти предыдущий трек: {prev_file_name}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())
