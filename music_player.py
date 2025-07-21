import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QFileDialog, QLabel, QSlider, QSizePolicy, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QSize, QSettings  # Добавлен QSettings
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QPainter, QBrush, QPainterPath
import vlc
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.wavpack import WavPack
from mutagen.id3 import ID3NoHeaderError
import io
import threading
import os
import logging  # Импортируем модуль логирования

# Импортируем Pillow для обработки изображений
from PIL import Image, ImageDraw

# Импортируем стили из отдельного файла
from styles import app_stylesheet

# Импортируем функцию настройки логирования
from logger_config import setup_logging


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


# Новый класс для элементов списка библиотеки
class ListItemWidget(QWidget):
    def __init__(self, text, image_data=None, font=None, parent=None, item_type="unknown"):
        super().__init__(parent)
        self.setFixedHeight(60)

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        self.image_label = QLabel()
        self.image_label.setFixedSize(50, 50)
        self.image_label.setStyleSheet("border-radius: 25px; background-color: #333333;")
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        self.text_label = QLabel(text)
        if font:
            self.text_label.setFont(font)
        self.text_label.setStyleSheet("color: white;")
        layout.addWidget(self.text_label)

        layout.addStretch(1)

        self.setLayout(layout)

        self._load_image(image_data, item_type)

    def _load_image(self, image_data, item_type):
        pil_image = None

        logging.debug(
            f"ListItemWidget: Attempting to load image for '{self.text_label.text()}' (item_type: {item_type})")

        if isinstance(image_data, QPixmap) and not image_data.isNull():
            logging.debug(f"ListItemWidget: Image data is QPixmap.")
            qimage = image_data.toImage()
            buffer = io.BytesIO()
            qimage.save(buffer, "PNG")
            buffer.seek(0)
            try:
                pil_image = Image.open(buffer)
                logging.debug(
                    f"ListItemWidget: Converted QPixmap to PIL Image for '{self.text_label.text()}' (Size: {pil_image.size[0]}x{pil_image.size[1]})")
            except Exception as e:
                logging.error(
                    f"ListItemWidget: Failed to convert QPixmap to PIL Image for '{self.text_label.text()}': {e}")
                pil_image = None
        elif isinstance(image_data, bytes):
            logging.debug(f"ListItemWidget: Image data is bytes.")
            try:
                pil_image = Image.open(io.BytesIO(image_data))
                logging.debug(
                    f"ListItemWidget: Successfully loaded PIL Image from raw data for '{self.text_label.text()}' (Size: {pil_image.size[0]}x{pil_image.size[1]})")
            except Exception as e:
                logging.debug(
                    f"ListItemWidget: Failed to load PIL Image from raw data for '{self.text_label.text()}': {e}")
                pil_image = None
        elif isinstance(image_data, str) and os.path.exists(image_data):
            logging.debug(f"ListItemWidget: Image data is path: '{image_data}'.")
            try:
                pil_image = Image.open(image_data)
                logging.debug(
                    f"ListItemWidget: Successfully loaded PIL Image from path '{image_data}' for '{self.text_label.text()}' (Size: {pil_image.size[0]}x{pil_image.size[1]})")
            except Exception as e:
                logging.debug(
                    f"ListItemWidget: Failed to load PIL Image from path '{image_data}' for '{self.text_label.text()}': {e}")
                pil_image = None
        else:
            logging.debug(f"ListItemWidget: No valid image data provided for '{self.text_label.text()}'.")

        if pil_image:
            try:
                # Ensure image has an alpha channel
                if pil_image.mode != 'RGBA':
                    pil_image = pil_image.convert('RGBA')
                    logging.debug(f"ListItemWidget: Converted PIL Image to RGBA for '{self.text_label.text()}'.")

                target_width = self.image_label.size().width()
                target_height = self.image_label.size().height()
                logging.debug(
                    f"ListItemWidget: Target size for '{self.text_label.text()}': {target_width}x{target_height}.")

                # Create a circular mask
                mask = Image.new('L', (target_width, target_height), 0)  # 'L' for grayscale mask
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, target_width, target_height), fill=255)  # Draw white circle on black background
                logging.debug(f"ListItemWidget: Created circular mask for '{self.text_label.text()}'.")

                # Resize the original image to fit the target size, maintaining aspect ratio
                # and expanding to cover the circle
                # Use Image.LANCZOS for high-quality downsampling
                pil_image.thumbnail((target_width, target_height), Image.LANCZOS)
                logging.debug(
                    f"ListItemWidget: Resized PIL Image thumbnail for '{self.text_label.text()}' (New size: {pil_image.width}x{pil_image.height}).")

                # Create a new image with transparent background
                final_pil_image = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))

                # Calculate paste position to center the thumbnail
                paste_x = (target_width - pil_image.width) // 2
                paste_y = (target_height - pil_image.height) // 2

                final_pil_image.paste(pil_image, (paste_x, paste_y), mask)
                logging.debug(f"ListItemWidget: Pasted PIL Image with mask for '{self.text_label.text()}'.")

                # Convert PIL Image to QImage manually
                # Get raw bytes and dimensions
                img_bytes = final_pil_image.tobytes("raw", "RGBA")
                img_width = final_pil_image.width
                img_height = final_pil_image.height
                bytes_per_line = 4 * img_width  # 4 bytes per pixel for RGBA

                qimage_from_pil = QImage(img_bytes, img_width, img_height, bytes_per_line, QImage.Format_RGBA8888)

                final_qpixmap = QPixmap.fromImage(qimage_from_pil)

                if final_qpixmap.isNull():
                    logging.error(
                        f"ListItemWidget: Failed to convert final PIL Image to QPixmap via manual QImage for '{self.text_label.text()}'.")
                    self.image_label.setText("Convert Error")
                    self.image_label.setPixmap(QPixmap())
                    return

                self.image_label.setPixmap(final_qpixmap)
                self.image_label.setText("")
                logging.debug(
                    f"ListItemWidget: Successfully set pixmap for '{self.text_label.text()}' using PIL and manual QImage conversion.")
            except Exception as e:
                logging.error(
                    f"ListItemWidget: Exception during PIL image processing or setting pixmap for '{self.text_label.text()}': {e}")
                self.image_label.setText("Render Error")
                self.image_label.setPixmap(QPixmap())
        else:
            if item_type == "folder":
                self.image_label.setText("Folder")
            elif item_type == "file":
                self.image_label.setText("Track")
            else:
                self.image_label.setText("?")
            self.image_label.setPixmap(QPixmap())
            logging.debug(
                f"ListItemWidget: Displaying placeholder for '{self.text_label.text()}', item_type: {item_type}")

    def sizeHint(self):
        return QSize(self.width(), self.height())


class MusicPlayer(QWidget):
    media_parsed_signal = pyqtSignal(int)
    library_scan_finished_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        setup_logging()  # Инициализируем логирование при запуске приложения

        # Инициализация QSettings для сохранения/загрузки настроек
        self.settings = QSettings("MyMusicPlayer", "MusicPlayerApp")  # Имя организации, Имя приложения

        self.setWindowTitle("ДОСТУП К МУЗЫКЕ")
        # self.setGeometry(100, 100, 1280, 720) # Удалено, так как будет максимизировано
        self.setMinimumSize(1280, 720)

        self.setStyleSheet(app_stylesheet)

        icon_path = os.path.join(os.path.dirname(__file__), 'media', 'zsxdcvbnjm.ico')
        try:
            self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            logging.error(f"Ошибка загрузки иконки: {e}. Убедитесь, что '{icon_path}' существует и доступен.")

        self.media_player = vlc.MediaPlayer()
        self.current_file = None
        self.total_length_ms = 0
        self.original_cover_pixmap = None
        self.artist_pixmap = None

        self.library_data = {}
        self.current_library_path = []
        self.root_library_folder = None

        self.is_shuffling = False
        self.is_repeating = False

        self.current_album_tracks = []
        self.current_track_index = -1

        self.icon_dir = os.path.join(os.path.dirname(__file__), 'media', 'control_panel_track')
        self.play_icon_path = os.path.join(self.icon_dir, 'play.ico')
        self.pause_icon_path = os.path.join(self.icon_dir, 'pause.ico')
        self.prev_icon_path = os.path.join(self.icon_dir, 'prev.ico')
        self.next_icon_path = os.path.join(self.icon_dir, 'next.ico')
        self.shuffle_icon_path = os.path.join(self.icon_dir, 'shuffle.ico')
        self.repeat_icon_path = os.path.join(self.icon_dir, 'repeat.ico')

        self.supported_extensions = ('.mp3', '.flac', '.wav')
        self.image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        self.init_ui()
        self.setup_timer()

        self.media_player.audio_set_volume(50)
        self.volume_slider.setValue(50)

        self.media_parsed_signal.connect(self._on_media_parsed)
        self.library_scan_finished_signal.connect(self._on_library_scan_finished)

        QApplication.instance().installEventFilter(self)

        # Загрузка последней выбранной папки при запуске
        last_folder = self.settings.value("last_music_folder", "", type=str)
        if last_folder and os.path.isdir(last_folder):
            logging.info(f"Загрузка последней папки: {last_folder}")
            self.root_library_folder = last_folder
            self.library_list_widget.clear()
            self.library_data.clear()
            self.current_library_path = []
            self.back_button.setEnabled(False)
            threading.Thread(target=self._scan_music_folder_in_thread,
                             args=(last_folder, self.supported_extensions)).start()
        else:
            logging.info("Последняя папка не найдена или недействительна.")

        self.showMaximized()  # Открываем приложение в полном размере

    def init_ui(self):
        root_layout = QHBoxLayout()

        # --- Левая панель (Библиотека) ---
        self.left_panel_widget = QWidget()  # Создаем контейнер для левой панели
        self.left_panel_widget.setObjectName("leftPanel")  # Устанавливаем objectName для CSS стилизации
        left_panel_layout = QVBoxLayout(self.left_panel_widget)  # Макет для контейнера левой панели
        left_panel_layout.setContentsMargins(15, 15, 15, 15)  # Отступы внутри контейнера

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

        root_layout.addWidget(self.left_panel_widget, 1)  # Добавляем контейнер левой панели в корневой макет

        # --- Правая панель (Плеер) ---
        right_panel_layout = QVBoxLayout()

        # 1. Info layout (cover and track details) - Сверху
        info_layout = QHBoxLayout()
        self.cover_label = SquareLabel()
        self.cover_label.setMinimumSize(50, 50)
        info_layout.addWidget(self.cover_label)

        # Новый лейбл для фотографии артиста
        self.artist_image_label = SquareLabel()
        self.artist_image_label.setText("Нет фото артиста")
        info_layout.addWidget(self.artist_image_label)

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

        right_panel_layout.addStretch(1)

        # Новый контейнер для черной контрольной панели
        self.control_panel_container = QWidget()
        self.control_panel_container.setStyleSheet("background-color: black;")
        control_panel_layout = QVBoxLayout(self.control_panel_container)
        control_panel_layout.setContentsMargins(0, 0, 0, 0)

        # 2. Playback controls row (shuffle, prev, play/pause, next, repeat) - Строго по центру
        playback_controls_row_layout = QHBoxLayout()
        playback_controls_row_layout.addStretch(1)

        # Кнопки в порядке: Перемешать, Предыдущий, Воспроизвести/Пауза, Следующий, Повтор
        self.shuffle_button = QPushButton()
        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        self.shuffle_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.shuffle_button)

        self.prev_track_button = QPushButton()
        self.prev_track_button.clicked.connect(self.play_previous_track)
        self.prev_track_button.setEnabled(False)
        self.prev_track_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.prev_track_button)

        self.play_pause_button = QPushButton()
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.play_pause_button.setEnabled(False)
        self.play_pause_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.play_pause_button)

        self.next_track_button = QPushButton()
        self.next_track_button.clicked.connect(self.play_next_track)
        self.next_track_button.setEnabled(False)
        self.next_track_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.next_track_button)

        self.repeat_button = QPushButton()
        self.repeat_button.clicked.connect(self.toggle_repeat)
        self.repeat_button.setFocusPolicy(Qt.NoFocus)
        playback_controls_row_layout.addWidget(self.repeat_button)

        playback_controls_row_layout.addStretch(1)
        control_panel_layout.addLayout(playback_controls_row_layout)

        # 3. Position slider
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setEnabled(False)
        control_panel_layout.addWidget(self.position_slider)

        # 4. Time labels
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch(1)
        time_layout.addWidget(self.total_time_label)
        control_panel_layout.addLayout(time_layout)

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
        control_panel_layout.addLayout(bottom_right_volume_container)

        right_panel_layout.addWidget(self.control_panel_container)

        root_layout.addLayout(right_panel_layout, 3)

        self.setLayout(root_layout)
        self._update_font_sizes()
        # Инициализируем иконки для кнопок
        self.shuffle_button.setIcon(QIcon(self.shuffle_icon_path))
        self.prev_track_button.setIcon(QIcon(self.prev_icon_path))
        self.next_track_button.setIcon(QIcon(self.next_icon_path))
        self.repeat_button.setIcon(QIcon(self.repeat_icon_path))

        self._update_button_style(self.shuffle_button, self.is_shuffling)
        self._update_button_style(self.prev_track_button, False)
        self._update_play_pause_button_style()
        self._update_button_style(self.next_track_button, False)
        self._update_button_style(self.repeat_button, self.is_repeating)

        self._update_artist_image_display()

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def update_ui(self):
        if not self.position_slider.isSliderDown():
            current_state = self.media_player.get_state()

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
            logging.error("Ошибка: Не указан путь к файлу для открытия.")
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
        self.artist_image_label.setText("Нет фото артиста")
        self.artist_image_label.setPixmap(QPixmap())
        self.artist_pixmap = None

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
            logging.error(f"Ошибка парсинга медиа в потоке: {e}")
            self.media_parsed_signal.emit(0)

    def _on_media_parsed(self, total_length_ms):
        self.total_length_ms = total_length_ms
        self.total_time_label.setText(self.format_time(total_length_ms))
        self.position_slider.setValue(0)

    def read_metadata(self, file_path):
        try:
            audio = None
            if file_path.lower().endswith('.mp3'):
                audio = MP3(file_path)
            elif file_path.lower().endswith('.flac'):
                audio = FLAC(file_path)
            elif file_path.lower().endswith('.wav'):
                logging.info(
                    f"Примечание: Метаданные для WAV-файлов (кроме WavPack) могут быть недоступны: {file_path}")
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

                # Загрузка обложки альбома
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

                # Загрузка фотографии артиста
                dir_name = os.path.dirname(file_path)
                artist_folder_name = os.path.basename(dir_name)

                found_artist_image = False
                for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                    artist_image_filename = artist_folder_name.lower() + ext
                    artist_image_path = os.path.join(dir_name, artist_image_filename)
                    logging.debug(f"Checking for artist image at: {artist_image_path}")
                    if os.path.exists(artist_image_path):
                        artist_pixmap_temp = QPixmap()
                        if artist_pixmap_temp.load(artist_image_path):
                            self.artist_pixmap = artist_pixmap_temp
                            logging.debug(f"Successfully loaded artist image: {artist_image_path}")
                            found_artist_image = True
                            break
                        else:
                            logging.debug(f"Failed to load QPixmap from: {artist_image_path}")

                if not found_artist_image:
                    self.artist_pixmap = None
                    logging.debug(f"No artist image found for folder: {artist_folder_name} in {dir_name}")

                self._update_artist_image_display()

        except ID3NoHeaderError:
            logging.info(f"Нет ID3 тегов для {file_path}. Возможно, это не MP3 или теги отсутствуют.")
            self.title_label.setText("Название: (Нет тегов)")
            self.artist_label.setText("Исполнитель: (Нет тегов)")
            self.album_label.setText("Альбом: (Нет тегов)")
            self.original_cover_pixmap = None
            self.artist_pixmap = None
            self._update_cover_display()
            self._update_artist_image_display()
        except Exception as e:
            logging.error(f"Ошибка чтения метаданных для {file_path}: {e}")
            self.title_label.setText("Название: (Ошибка чтения)")
            self.artist_label.setText("Исполнитель: (Ошибка чтения)")
            self.album_label.setText("Альбом: (Ошибка чтения)")
            self.original_cover_pixmap = None
            self.artist_pixmap = None
            self._update_cover_display()
            self._update_artist_image_display()

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

    def _update_artist_image_display(self):
        """Обновляет отображение фотографии артиста."""
        fixed_side = max(50, int(min(self.width(), self.height()) * 0.1))
        self.artist_image_label.setFixedSize(fixed_side, fixed_side)

        if self.artist_pixmap:
            scaled_pixmap = self.artist_pixmap.scaled(self.artist_image_label.size(),
                                                      Qt.KeepAspectRatio,
                                                      Qt.SmoothTransformation)
            self.artist_image_label.setPixmap(scaled_pixmap)
            self.artist_image_label.setText("")
        else:
            self.artist_image_label.setText("Нет фото артиста")
            self.artist_image_label.setPixmap(QPixmap())

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

        icon_size = max(24, int(window_side * 0.03))

        button_fixed_size = max(50, int(window_side * 0.06))

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

        self._update_button_style(self.shuffle_button, self.is_shuffling)
        self._update_button_style(self.prev_track_button, False)
        self._update_play_pause_button_style()
        self._update_button_style(self.next_track_button, False)
        self._update_button_style(self.repeat_button, self.is_repeating)

        self._update_artist_image_display()

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
        current_state = self.media_player.get_state()
        if current_state == vlc.State.Playing:
            self.pause_music()
        elif current_state == vlc.State.Paused:
            self.play_music()
        else:
            self.play_music()

    def play_music(self):
        if self.current_file:
            self.media_player.play()
            self._update_play_pause_button_style()
            self.play_pause_button.setEnabled(True)
            self.timer.start()

    def pause_music(self):
        if self.media_player.get_state() == vlc.State.Playing:
            self.media_player.pause()
        self._update_play_pause_button_style()
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
        logging.info(f"Режим перемешивания: {'Включен' if self.is_shuffling else 'Выключен'}")

    def toggle_repeat(self):
        """Переключает режим повтора."""
        self.is_repeating = not self.is_repeating
        self._update_button_style(self.repeat_button, self.is_repeating)
        logging.info(f"Режим повтора: {'Включен' if self.is_repeating else 'Выключен'}")

    def _update_button_style(self, button, is_active):
        """Применяет стиль к кнопке в зависимости от ее состояния активности."""
        if is_active:
            button.setStyleSheet(f"background-color: #007bff; color: transparent;")
        else:
            button.setStyleSheet(f"background-color: #333333; color: transparent;")

    def _update_play_pause_button_style(self):
        """Обновляет стиль и текст кнопки воспроизведения/паузы."""
        current_state = self.media_player.get_state()

        if current_state == vlc.State.Playing:
            self.play_pause_button.setIcon(QIcon(self.pause_icon_path))
        else:
            self.play_pause_button.setIcon(QIcon(self.play_icon_path))

        self.play_pause_button.setStyleSheet(f"background-color: white; color: transparent;")

    def open_library_folder(self):
        """Открывает диалог выбора папки и сканирует ее на наличие музыкальных файлов."""
        folder_path = QFileDialog.getExistingDirectory(self, "Выбрать корневую папку с музыкой")
        if folder_path:
            self.root_library_folder = folder_path
            self.settings.setValue("last_music_folder", folder_path)  # Сохраняем выбранную папку
            self.library_list_widget.clear()
            self.library_data.clear()
            self.current_library_path = []
            self.back_button.setEnabled(False)

            threading.Thread(target=self._scan_music_folder_in_thread,
                             args=(folder_path, self.supported_extensions)).start()

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

        current_level_full_path = self.root_library_folder
        if current_level_full_path is None:
            logging.warning("Корневая папка библиотеки не установлена. Невозможно отобразить библиотеку.")
            return

        for part in self.current_library_path:
            current_level_full_path = os.path.join(current_level_full_path, part)

        temp_node = self.library_data
        is_valid_path = True
        for part in self.current_library_path:
            if part in temp_node and isinstance(temp_node[part], dict):
                temp_node = temp_node[part]
            else:
                is_valid_path = False
                break
        if is_valid_path:
            current_node = temp_node
        else:
            self.current_library_path = []
            current_node = self.library_data
            current_level_full_path = self.root_library_folder
            logging.info("Недействительный путь к библиотеке, сброс до корня.")

        list_item_font_size = max(8, int(min(self.width(), self.height()) * 0.006))
        list_item_font = QFont("Arial", list_item_font_size)

        folders = sorted([k for k, v in current_node.items() if isinstance(v, dict)])
        for folder_name in folders:
            item_image_data = None
            folder_full_path = os.path.join(current_level_full_path, folder_name)

            logging.debug(f"Processing folder: {folder_full_path}")

            # --- Логика для папок исполнителей (поиск файла изображения в папке) ---
            found_artist_image_file = False
            for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                artist_image_path = os.path.join(folder_full_path, folder_name + ext)
                if os.path.exists(artist_image_path):
                    item_image_data = artist_image_path
                    found_artist_image_file = True
                    logging.debug(f"Found artist image file for '{folder_name}' at: {artist_image_path}")
                    break

            # --- Логика для папок альбомов (извлечение из музыкальных файлов) ---
            if not found_artist_image_file:
                logging.debug(
                    f"No dedicated artist image file found for '{folder_name}'. Attempting to extract from audio files.")
                found_audio_file_for_cover = False
                try:
                    # Iterate through files in the current folder to find an audio file with cover art
                    for file_inner in os.listdir(folder_full_path):
                        audio_file_path = os.path.join(folder_full_path, file_inner)
                        logging.debug(f"Checking file for cover: {audio_file_path}")
                        if os.path.isfile(audio_file_path) and audio_file_path.lower().endswith(
                                self.supported_extensions):
                            try:
                                audio = None
                                if audio_file_path.lower().endswith('.mp3'):
                                    audio = MP3(audio_file_path)
                                elif audio_file_path.lower().endswith('.flac'):
                                    audio = FLAC(audio_file_path)

                                if audio:
                                    if audio_file_path.lower().endswith('.mp3'):
                                        for tag in audio.getall('APIC'):
                                            if tag.type == 3:  # Front Cover
                                                item_image_data = tag.data
                                                found_audio_file_for_cover = True
                                                logging.debug(
                                                    f"Found MP3 cover data for {folder_name} from {audio_file_path}")
                                                break
                                    elif audio_file_path.lower().endswith('.flac') and audio.pictures:
                                        for pic in audio.pictures:
                                            if pic.type == 3:  # Front Cover
                                                item_image_data = pic.data
                                                found_audio_file_for_cover = True
                                                logging.debug(
                                                    f"Found FLAC cover data for {folder_name} from {audio_file_path}")
                                                break
                            except ID3NoHeaderError:
                                logging.debug(f"No ID3 tags found for {audio_file_path}. Skipping cover extraction.")
                            except Exception as e:
                                logging.debug(f"Error reading metadata for album cover from {audio_file_path}: {e}")

                            if found_audio_file_for_cover:
                                break  # Stop searching for cover in this folder
                except FileNotFoundError:
                    logging.debug(f"Folder not found: {folder_full_path}")
                except Exception as e:
                    logging.debug(f"Error listing directory {folder_full_path}: {e}")

            item_widget = ListItemWidget(folder_name, item_image_data, list_item_font, item_type="folder")
            item = QListWidgetItem(self.library_list_widget)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.UserRole, "folder")
            self.library_list_widget.addItem(item)
            self.library_list_widget.setItemWidget(item, item_widget)

        files = sorted([k for k, v in current_node.items() if isinstance(v, str)])
        for file_name in files:
            display_name = os.path.splitext(file_name)[0]
            # Для отдельных треков извлекаем обложку из самого трека
            track_cover_data = None
            full_file_path = os.path.join(current_level_full_path, file_name)
            logging.debug(f"Checking file for track cover: {full_file_path}")
            try:
                audio = None
                if full_file_path.lower().endswith('.mp3'):
                    audio = MP3(full_file_path)
                elif full_file_path.lower().endswith('.flac'):
                    audio = FLAC(full_file_path)

                if audio:
                    if full_file_path.lower().endswith('.mp3'):
                        for tag in audio.getall('APIC'):
                            if tag.type == 3:  # Front Cover
                                track_cover_data = tag.data
                                logging.debug(f"Found MP3 cover data for track {file_name}")
                                break
                    elif full_file_path.lower().endswith('.flac') and audio.pictures:
                        for pic in audio.pictures:
                            if pic.type == 3:  # Front Cover
                                track_cover_data = pic.data
                                logging.debug(f"Found FLAC cover data for track {file_name}")
                                break
            except ID3NoHeaderError:
                logging.debug(f"No ID3 tags found for track {file_name}. Skipping cover extraction.")
            except Exception as e:
                logging.debug(f"Error reading metadata for track cover from {full_file_path}: {e}")

            item_widget = ListItemWidget(display_name, track_cover_data, list_item_font, item_type="file")
            item = QListWidgetItem(self.library_list_widget)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.UserRole, "file")
            item.setData(Qt.UserRole + 1, file_name)
            self.library_list_widget.addItem(item)
            self.library_list_widget.setItemWidget(item, item_widget)

        if not folders and not files:
            item_widget = ListItemWidget("Пусто.", None, list_item_font, item_type="empty")
            item = QListWidgetItem(self.library_list_widget)
            item.setSizeHint(item_widget.sizeHint())
            self.library_list_widget.addItem(item)
            self.library_list_widget.setItemWidget(item, item_widget)

        self.back_button.setEnabled(len(self.current_library_path) > 0)

    def load_track_from_library(self, item):
        """
        Загружает и воспроизводит трек или переходит в папку, выбранную из списка библиотеки.
        """
        item_widget = self.library_list_widget.itemWidget(item)
        if item_widget:
            item_type = item.data(Qt.UserRole)

            if item_type == "folder":
                folder_name = item_widget.text_label.text()
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
                    logging.error(f"Ошибка: Не удалось найти полный путь для файла: {full_file_name}")
            else:
                logging.warning(f"Неизвестный тип элемента: {item_widget.text_label.text()}")
        else:
            logging.error("Ошибка: Виджет элемента списка не найден.")

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
            logging.info("Нет контекста альбома или трек не воспроизводится из библиотеки.")
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
            logging.error(f"Ошибка: Не удалось найти полный путь для файла: {next_file_name}")

    def play_previous_track(self):
        """
        Воспроизводит предыдущий трек в текущем альбоме/папке.
        """
        if not self.current_album_tracks or self.current_track_index == -1:
            logging.info("Нет контекста альбома или трек не воспроизводится из библиотеки.")
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
            logging.error(f"Ошибка: Не удалось найти предыдущий трек: {prev_file_name}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())
