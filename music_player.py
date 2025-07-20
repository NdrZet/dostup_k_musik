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


# Новый пользовательский класс для квадратной метки обложки
class SquareLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Нет обложки")
        self.setStyleSheet("border: 1px solid #ccc;")

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

        # Установка иконки приложения
        # Используем абсолютный путь для надежной загрузки иконки
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

        # Контекст для воспроизведения следующего/предыдущего трека
        self.current_album_tracks = []
        self.current_track_index = -1

        self.init_ui()
        self.setup_timer()

        # Устанавливаем начальную громкость (например, 50%)
        self.media_player.audio_set_volume(50)
        self.volume_slider.setValue(50)

        self.media_parsed_signal.connect(self._on_media_parsed)
        self.library_scan_finished_signal.connect(self._on_library_scan_finished)

        # Устанавливаем фильтр событий на экземпляр QApplication для глобальной обработки клавиш
        QApplication.instance().installEventFilter(self)

    def init_ui(self):
        # Главный горизонтальный макет, разделяющий окно на две панели
        root_layout = QHBoxLayout()

        # --- Левая панель (Библиотека) ---
        left_panel_layout = QVBoxLayout()

        self.library_label = QLabel("Моя Музыкальная Библиотека")
        left_panel_layout.addWidget(self.library_label)

        self.add_root_folder_button = QPushButton("Добавить корневую папку")
        self.add_root_folder_button.clicked.connect(self.open_library_folder)
        self.add_root_folder_button.setFocusPolicy(Qt.NoFocus)  # Убираем фокус с кнопки
        left_panel_layout.addWidget(self.add_root_folder_button)

        self.back_button = QPushButton("Назад")
        self.back_button.clicked.connect(self._navigate_back)
        self.back_button.setEnabled(False)
        self.back_button.setFocusPolicy(Qt.NoFocus)  # Убираем фокус с кнопки
        left_panel_layout.addWidget(self.back_button)

        self.library_list_widget = QListWidget()
        self.library_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.library_list_widget.itemClicked.connect(self.load_track_from_library)
        # Оставляем фокус для QListWidget, так как он нужен для навигации по элементам
        left_panel_layout.addWidget(self.library_list_widget)

        root_layout.addLayout(left_panel_layout, 1)

        # --- Правая панель (Плеер) ---
        right_panel_layout = QVBoxLayout()

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

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setEnabled(False)
        # Оставляем фокус для QSlider, так как он нужен для перетаскивания
        right_panel_layout.addWidget(self.position_slider, 1)

        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch(1)
        time_layout.addWidget(self.total_time_label)
        right_panel_layout.addLayout(time_layout, 1)

        controls_layout = QHBoxLayout()
        # Кнопка "Открыть файл" удалена

        # --- Кнопки управления воспроизведением ---
        # Кнопка "Предыдущий"
        self.prev_track_button = QPushButton("Предыдущий")
        self.prev_track_button.clicked.connect(self.play_previous_track)
        self.prev_track_button.setEnabled(False)
        self.prev_track_button.setFocusPolicy(Qt.NoFocus)
        controls_layout.addWidget(self.prev_track_button)

        # Объединенная кнопка "Воспроизвести/Пауза"
        self.play_pause_button = QPushButton("Воспроизвести")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.play_pause_button.setEnabled(False)
        self.play_pause_button.setFocusPolicy(Qt.NoFocus)
        controls_layout.addWidget(self.play_pause_button)

        # Кнопка "Следующий"
        self.next_track_button = QPushButton("Следующий")
        self.next_track_button.clicked.connect(self.play_next_track)
        self.next_track_button.setEnabled(False)
        self.next_track_button.setFocusPolicy(Qt.NoFocus)
        controls_layout.addWidget(self.next_track_button)
        # --- Конец кнопок управления воспроизведением ---

        # --- Добавляем управление громкостью ---
        volume_control_layout = QHBoxLayout()
        self.volume_label = QLabel("Громкость: 50%")
        volume_control_layout.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.sliderMoved.connect(self.set_volume)
        # Оставляем фокус для QSlider, так как он нужен для перетаскивания и колесика мыши
        volume_control_layout.addWidget(self.volume_slider)

        # Устанавливаем фильтр событий для ползунка громкости
        self.volume_slider.installEventFilter(self)

        controls_layout.addLayout(volume_control_layout)

        right_panel_layout.addLayout(controls_layout, 1)

        root_layout.addLayout(right_panel_layout, 3)

        self.setLayout(root_layout)
        self._update_font_sizes()

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def update_ui(self):
        if not self.position_slider.isSliderDown():
            if self.media_player.is_playing() or self.media_player.get_state() == vlc.State.Paused:
                current_time = self.media_player.get_time()
                if self.total_length_ms > 0:
                    position = int((current_time / self.total_length_ms) * 1000)
                    self.position_slider.setValue(position)

                self.current_time_label.setText(self.format_time(current_time))
            elif self.media_player.get_state() == vlc.State.Ended:
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
        self.play_pause_button.setFont(font)
        self.add_root_folder_button.setFont(font)
        self.back_button.setFont(font)
        self.prev_track_button.setFont(font)
        self.next_track_button.setFont(font)

        time_label_font_size = max(8, int(window_side * 0.007))
        time_font = QFont("Arial", time_label_font_size)
        self.current_time_label.setFont(time_font)
        self.total_time_label.setFont(time_font)

        self.library_label.setFont(QFont("Arial", base_font_size, QFont.Bold))
        self.volume_label.setFont(time_font)

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

            # Глобальная обработка нажатия клавиши пробел
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            self.toggle_play_pause()
            return True  # Потребляем событие, чтобы оно не передавалось дальше

        return super().eventFilter(obj, event)

    def toggle_play_pause(self):
        """Переключает воспроизведение/паузу."""
        if self.media_player.is_playing():
            self.pause_music()
        else:
            self.play_music()

    def play_music(self):
        if self.current_file:
            self.media_player.play()
            self.play_pause_button.setText("Пауза")
            self.play_pause_button.setEnabled(True)
            self.timer.start()

    def pause_music(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_pause_button.setText("Воспроизвести")
            self.play_pause_button.setEnabled(True)
            self.timer.stop()

    def stop_music(self):
        """Останавливает воспроизведение и сбрасывает состояние плеера."""
        self.media_player.stop()
        self.position_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.timer.stop()

        self.play_pause_button.setText("Воспроизвести")
        self.play_pause_button.setEnabled(False)
        self.prev_track_button.setEnabled(False)
        self.next_track_button.setEnabled(False)
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

            # Получаем список всех файлов в текущей папке/альбоме для навигации
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

        # Реконструируем полный путь для следующего трека
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

        # Реконструируем полный путь для предыдущего трека
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
