import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QFileDialog, QLabel, QSlider, QSizePolicy, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QSize
from PyQt5.QtGui import QPixmap, QImage, QFont
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
    # Сигнал для обновления списка библиотеки из другого потока
    # Теперь передает полную структуру данных библиотеки
    library_scan_finished_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ДОСТУП К МУЗЫКЕ")
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(1280, 720)

        self.media_player = vlc.MediaPlayer()
        self.current_file = None
        self.total_length_ms = 0
        self.original_cover_pixmap = None

        # Новая структура для хранения данных библиотеки
        self.library_data = {}
        # Отслеживание текущего пути в библиотеке (например, ['Исполнитель', 'Альбом'])
        self.current_library_path = []
        self.root_library_folder = None  # Корневая папка библиотеки

        self.init_ui()
        self.setup_timer()

        self.media_parsed_signal.connect(self._on_media_parsed)
        self.library_scan_finished_signal.connect(self._on_library_scan_finished)

    def init_ui(self):
        # Главный горизонтальный макет, разделяющий окно на две панели
        root_layout = QHBoxLayout()

        # --- Левая панель (Библиотека) ---
        left_panel_layout = QVBoxLayout()

        self.library_label = QLabel("Моя Музыкальная Библиотека")
        left_panel_layout.addWidget(self.library_label)

        self.add_root_folder_button = QPushButton("Добавить корневую папку")
        self.add_root_folder_button.clicked.connect(self.open_library_folder)
        left_panel_layout.addWidget(self.add_root_folder_button)

        # Кнопка "Назад" для навигации по папкам
        self.back_button = QPushButton("Назад")
        self.back_button.clicked.connect(self._navigate_back)
        self.back_button.setEnabled(False)  # Изначально отключена
        left_panel_layout.addWidget(self.back_button)

        self.library_list_widget = QListWidget()
        self.library_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.library_list_widget.itemClicked.connect(self.load_track_from_library)
        left_panel_layout.addWidget(self.library_list_widget)

        root_layout.addLayout(left_panel_layout, 1)  # Левая панель занимает 1/4 ширины

        # --- Правая панель (Плеер) ---
        right_panel_layout = QVBoxLayout()

        # Раздел информации о треке и обложки
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

        # Ползунок прогресса
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setEnabled(False)
        right_panel_layout.addWidget(self.position_slider, 1)

        # Метки времени
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.total_time_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch(1)
        time_layout.addWidget(self.total_time_label)
        right_panel_layout.addLayout(time_layout, 1)

        # Кнопки управления
        controls_layout = QHBoxLayout()
        self.open_button = QPushButton("Открыть файл")
        self.open_button.clicked.connect(self.open_file)
        controls_layout.addWidget(self.open_button)

        self.play_button = QPushButton("Воспроизвести")
        self.play_button.clicked.connect(self.play_music)
        self.play_button.setEnabled(False)
        controls_layout.addWidget(self.play_button)

        self.pause_button = QPushButton("Пауза")
        self.pause_button.clicked.connect(self.pause_music)
        self.pause_button.setEnabled(False)
        controls_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Стоп")
        self.stop_button.clicked.connect(self.stop_music)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)

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
                self.stop_music()

    def format_time(self, ms):
        seconds = int(ms / 1000)
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:02}:{seconds:02}"

    def open_file(self, file_path=None):
        if file_path is None:
            file_name, _ = QFileDialog.getOpenFileName(self, "Открыть музыкальный файл", "",
                                                       "Музыкальные файлы (*.mp3 *.flac *.wav);;Все файлы (*.*)")
        else:
            file_name = file_path

        if file_name:
            self.current_file = file_name
            self.stop_music()

            self.title_label.setText("Название: -")
            self.artist_label.setText("Исполнитель: -")
            self.album_label.setText("Альбом: -")
            self.cover_label.setText("Нет обложки")
            self.cover_label.setPixmap(QPixmap())
            self.original_cover_pixmap = None

            self.read_metadata(file_name)

            self.play_button.setEnabled(True)
            self.position_slider.setEnabled(True)

            threading.Thread(target=self._parse_media_in_thread, args=(self.current_file,)).start()

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

        media = vlc.Media(self.current_file)
        self.media_player.set_media(media)

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
        self.open_button.setFont(font)
        self.play_button.setFont(font)
        self.pause_button.setFont(font)
        self.stop_button.setFont(font)
        self.add_root_folder_button.setFont(font)
        self.back_button.setFont(font)  # Устанавливаем шрифт для кнопки "Назад"

        time_label_font_size = max(8, int(window_side * 0.007))
        time_font = QFont("Arial", time_label_font_size)
        self.current_time_label.setFont(time_font)
        self.total_time_label.setFont(time_font)

        self.library_label.setFont(QFont("Arial", base_font_size, QFont.Bold))

        # QListWidget не имеет прямого метода setFont для всех элементов сразу
        # Шрифт для элементов списка устанавливается при их добавлении в _on_library_scan_finished

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_cover_display)
        QTimer.singleShot(0, self._update_font_sizes)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            QTimer.singleShot(0, self._update_cover_display)
            QTimer.singleShot(0, self._update_font_sizes)
        super().changeEvent(event)

    def play_music(self):
        if self.current_file:
            if self.media_player.get_state() == vlc.State.Paused:
                self.media_player.play()
            else:
                if not self.media_player.get_media() or self.media_player.get_media().get_mrl() != self.current_file:
                    media = vlc.Media(self.current_file)
                    self.media_player.set_media(media)

                self.media_player.play()

            self.play_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.timer.start()

    def pause_music(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.timer.stop()

    def stop_music(self):
        self.media_player.stop()
        self.play_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.position_slider.setValue(0)
        self.current_time_label.setText("00:00")
        self.total_time_label.setText("00:00")
        self.timer.stop()

    def set_position(self, position):
        if self.media_player.is_playing() and self.total_length_ms > 0:
            new_time_ms = int(self.total_length_ms * (position / 1000.0))
            self.media_player.set_time(new_time_ms)

    def open_library_folder(self):
        """Открывает диалог выбора папки и сканирует ее на наличие музыкальных файлов."""
        folder_path = QFileDialog.getExistingDirectory(self, "Выбрать корневую папку с музыкой")
        if folder_path:
            self.root_library_folder = folder_path
            self.library_list_widget.clear()  # Очищаем список перед заполнением
            self.library_data.clear()  # Очищаем структуру данных библиотеки
            self.current_library_path = []  # Сбрасываем путь при выборе новой корневой папки
            self.back_button.setEnabled(False)  # Отключаем кнопку "Назад"

            supported_extensions = ('.mp3', '.flac', '.wav')

            # Запускаем сканирование в отдельном потоке
            threading.Thread(target=self._scan_music_folder_in_thread, args=(folder_path, supported_extensions)).start()

    def _scan_music_folder_in_thread(self, current_folder, supported_extensions):
        """
        Сканирует указанную папку на наличие музыкальных файлов и строит древовидную структуру.
        """
        library_structure = {}

        for root, dirs, files in os.walk(current_folder):
            # Вычисляем относительный путь текущей папки от корневой
            relative_root = os.path.relpath(root, current_folder)
            if relative_root == ".":  # Для корневой папки
                current_node = library_structure
            else:
                # Находим соответствующий узел в древовидной структуре
                path_parts = relative_root.split(os.sep)
                current_node = library_structure
                for part in path_parts:
                    if part not in current_node:
                        current_node[part] = {}  # Создаем новую вложенную папку
                    current_node = current_node[part]

            # Добавляем файлы в текущий узел
            for file in files:
                if file.lower().endswith(supported_extensions):
                    full_path = os.path.join(root, file)
                    current_node[file] = full_path  # Храним полный путь к файлу

        self.library_scan_finished_signal.emit(library_structure)

    def _on_library_scan_finished(self, library_structure):
        """
        Слот, который обрабатывает результаты сканирования библиотеки и отображает корневой уровень.
        """
        self.library_data = library_structure
        self._display_current_library_level()

    def _display_current_library_level(self):
        """
        Отображает содержимое текущего уровня библиотеки в QListWidget.
        """
        self.library_list_widget.clear()
        current_node = self.library_data

        # Переходим к текущему узлу в древовидной структуре
        for part in self.current_library_path:
            if part in current_node:
                current_node = current_node[part]
            else:
                # Если путь некорректен, сбрасываемся в корень
                self.current_library_path = []
                current_node = self.library_data
                break

        # Получаем текущий размер шрифта для элементов списка
        list_item_font_size = max(8, int(min(self.width(), self.height()) * 0.006))
        list_item_font = QFont("Arial", list_item_font_size)

        # Добавляем папки (исполнителей/альбомы)
        folders = sorted([k for k, v in current_node.items() if isinstance(v, dict)])
        for folder_name in folders:
            item = QListWidgetItem(folder_name)
            item.setFont(list_item_font)
            # Сохраняем тип элемента (папка) в UserRole
            item.setData(Qt.UserRole, "folder")
            self.library_list_widget.addItem(item)

        # Добавляем файлы (треки)
        files = sorted([k for k, v in current_node.items() if isinstance(v, str)])
        for file_name in files:
            # !!! ИЗМЕНЕНИЕ ЗДЕСЬ: Удаляем расширение файла для отображения !!!
            display_name = os.path.splitext(file_name)[0]
            item = QListWidgetItem(display_name)
            item.setFont(list_item_font)
            # Сохраняем тип элемента (файл) в UserRole
            item.setData(Qt.UserRole, "file")
            # !!! ВАЖНО: Сохраняем полное имя файла (с расширением) в UserRole + 1 для загрузки !!!
            item.setData(Qt.UserRole + 1, file_name)
            self.library_list_widget.addItem(item)

        if not folders and not files:
            item = QListWidgetItem("Пусто.")
            item.setFont(list_item_font)
            self.library_list_widget.addItem(item)

        # Обновляем состояние кнопки "Назад"
        self.back_button.setEnabled(len(self.current_library_path) > 0)

    def load_track_from_library(self, item):
        """
        Загружает и воспроизводит трек или переходит в папку, выбранную из списка библиотеки.
        """
        item_type = item.data(Qt.UserRole)  # Получаем тип элемента

        if item_type == "folder":
            folder_name = item.text()
            self.current_library_path.append(folder_name)
            self._display_current_library_level()
        elif item_type == "file":
            # !!! ИЗМЕНЕНИЕ ЗДЕСЬ: Получаем полное имя файла из UserRole + 1 !!!
            full_file_name = item.data(Qt.UserRole + 1)
            # Получаем полный путь к файлу из library_data
            current_node = self.library_data
            for part in self.current_library_path:
                current_node = current_node[part]

            # Используем полное имя файла для получения пути
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
            self.current_library_path.pop()  # Удаляем последний элемент пути
            self._display_current_library_level()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())
