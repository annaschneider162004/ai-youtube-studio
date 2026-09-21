import json
import os
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.google_auth import GoogleAuth
from app.services.pipeline import PipelineManager
from app.services.voice import VoiceSettings, convert_audio_format, validate_voice_sample
from app.services.youtube_service import YouTubeService


def parse_tags(value):
    return [item.strip() for item in (value or '').split(',') if item.strip()]


def path_text(value):
    return str(value or '')


def parse_float_text(value, default):
    try:
        return float((value or '').strip())
    except ValueError:
        return default


def parse_int_text(value, default):
    try:
        return int((value or '').strip())
    except ValueError:
        return default


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.pipeline = PipelineManager(db)
        self.setWindowTitle('AI YouTube Studio V5')
        self.resize(1540, 980)
        self.setMinimumSize(1200, 760)

        root = QWidget()
        layout = QHBoxLayout(root)
        self.nav = QListWidget()
        self.nav.setObjectName('sidebar')
        self.nav.addItems(['Tổng quan', 'Tài khoản', 'Dự án', 'Quy trình V5', 'Voice Studio', 'Xuất bản', 'Phân tích', 'Cài đặt'])
        self.nav.setFixedWidth(240)
        self.stack = QStackedWidget()
        self.stack.setObjectName('contentStack')

        self.dashboard_page = DashboardPage(db)
        self.accounts_page = AccountsPage(db, self.refresh_all)
        self.projects_page = ProjectsPage(db, self.refresh_all)
        self.workflow_page = WorkflowPage(db, self.pipeline, self.read_settings, self.refresh_all)
        self.voice_page = VoiceStudioPage(db, self.pipeline, self.read_settings, self.refresh_all)
        self.publish_page = PublishPage(db, self.pipeline, self.refresh_all)
        self.analytics_page = AnalyticsPage(db)
        self.settings_page = SettingsPage(db, self.refresh_all)

        self.pages = [
            self.dashboard_page,
            self.accounts_page,
            self.projects_page,
            self.workflow_page,
            self.voice_page,
            self.publish_page,
            self.analytics_page,
            self.settings_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.apply_theme()
        self.nav.setCurrentRow(0)
        self.refresh_all()

    def read_settings(self):
        data_root = Path(os.environ.get('AIYS_DATA_DIR', 'data')).expanduser()
        output_default = str((data_root / 'outputs').resolve())
        defaults = {
            'google_client_secret': os.environ.get('AIYS_GOOGLE_CLIENT_SECRET', 'data/client_secret.json'),
            'ai_endpoint': os.environ.get('AIYS_AI_ENDPOINT', ''),
            'ai_api_key': os.environ.get('AIYS_AI_API_KEY', ''),
            'ai_model': os.environ.get('AIYS_AI_MODEL', ''),
            'voice_endpoint': os.environ.get('AIYS_VOICE_ENDPOINT', ''),
            'voice_api_key': os.environ.get('AIYS_VOICE_API_KEY', ''),
            'voice_id': os.environ.get('AIYS_VOICE_ID', ''),
            'voice_http_timeout': os.environ.get('AIYS_VOICE_HTTP_TIMEOUT', '90'),
            'ffmpeg_path': os.environ.get('AIYS_FFMPEG_PATH', 'ffmpeg'),
            'output_dir': os.environ.get('AIYS_OUTPUT_DIR', output_default),
            'locale': os.environ.get('AIYS_LOCALE', 'vi-VN'),
            'log_level': os.environ.get('AIYS_LOG_LEVEL', 'INFO'),
        }
        return {key: self.db.get_setting(key, default) for key, default in defaults.items()}

    def refresh_all(self):
        for page in self.pages:
            if hasattr(page, 'refresh'):
                page.refresh()

    def apply_theme(self):
        self.setStyleSheet(
            '''
            QWidget {
                background: #070b14;
                color: #d9efff;
                font-size: 13px;
            }
            #sidebar {
                background: #0e1526;
                border: 1px solid #183053;
                border-radius: 12px;
                outline: 0;
            }
            #sidebar::item {
                padding: 12px 10px;
                border-radius: 8px;
                margin: 4px;
            }
            #sidebar::item:selected {
                background: #1a2c4e;
                color: #70f6ff;
                border: 1px solid #2f86ff;
            }
            QGroupBox {
                border: 1px solid #20395f;
                border-radius: 10px;
                margin-top: 12px;
                padding: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDateTimeEdit, QTableWidget {
                background: #0c1220;
                border: 1px solid #2c4268;
                border-radius: 8px;
                padding: 6px;
                selection-background-color: #224b78;
            }
            QPushButton {
                background: #14233d;
                border: 1px solid #2c5385;
                border-radius: 8px;
                padding: 8px 12px;
                color: #cde6ff;
                font-weight: 600;
            }
            QPushButton:hover { background: #1b3256; border-color: #45d2ff; }
            QPushButton:pressed { background: #122844; }
            QTableWidget {
                gridline-color: #1e3559;
            }
            QHeaderView::section {
                background: #14213a;
                color: #87c9ff;
                border: 0;
                padding: 6px;
            }
            QProgressBar {
                border: 1px solid #2f4c73;
                border-radius: 8px;
                background: #09111f;
                text-align: center;
                color: #dbf9ff;
            }
            QProgressBar::chunk {
                background: #00d2a8;
                border-radius: 8px;
            }
            QLabel#statusBadge {
                border: 1px solid #2f5f8f;
                border-radius: 9px;
                padding: 4px 10px;
                font-weight: 700;
                max-width: 280px;
            }
            QLabel#statusBadge[state="ok"] { color: #66f7cf; border-color: #228a66; background: #0f2a23; }
            QLabel#statusBadge[state="busy"] { color: #72f0ff; border-color: #2b8da9; background: #0f2331; }
            QLabel#statusBadge[state="warn"] { color: #ff7cf0; border-color: #8d3fb0; background: #231738; }
            '''
        )


class DashboardPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        title = QLabel('AI YouTube Studio V5')
        title.setStyleSheet('font-size:30px;font-weight:700;')
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                'Workflow chuẩn: Project → Script → Voice/TTS → Subtitle → Video Assembly → '
                'Thumbnail → Safety Check → Human Approval → Upload/Schedule'
            )
        )
        self.stats = QLabel()
        self.status_overview = QLabel()
        self.control_badge = QLabel('CONTROL CENTER')
        self.control_badge.setObjectName('statusBadge')
        self.control_badge.setProperty('state', 'ok')
        self.pipeline_panel = QTextEdit()
        self.pipeline_panel.setReadOnly(True)
        layout.addWidget(self.stats)
        layout.addWidget(self.status_overview)
        layout.addWidget(self.control_badge)
        safety = QGroupBox('Nguyên tắc an toàn')
        safety_layout = QVBoxLayout(safety)
        for line in [
            'Dùng Google OAuth và YouTube Data API chính thức.',
            'Không lưu mật khẩu Google.',
            'Không fake views/likes/subscribers/comments.',
            'Không bypass CAPTCHA, rate limit hay restriction.',
            'Voice/TTS và media đều phải có quyền sử dụng hợp lệ.',
            'Safety check và human approval là bắt buộc trước upload.',
        ]:
            safety_layout.addWidget(QLabel(f'• {line}'))
        layout.addWidget(safety)
        pipeline_box = QGroupBox('Workflow pipeline monitor')
        pipeline_layout = QVBoxLayout(pipeline_box)
        pipeline_layout.addWidget(self.pipeline_panel)
        layout.addWidget(pipeline_box, 1)
        layout.addStretch()

    def refresh(self):
        projects = self.db.projects()
        uploads = self.db.uploads()
        accounts = self.db.accounts()
        self.stats.setText(
            f'Tài khoản: {len(accounts)}    Dự án: {len(projects)}    Lịch sử upload: {len(uploads)}'
        )
        status_counts = {}
        for row in projects:
            status_counts[row['status']] = status_counts.get(row['status'], 0) + 1
        summary = ', '.join(f'{key}: {value}' for key, value in sorted(status_counts.items())) or 'Chưa có project.'
        self.status_overview.setText(f'Trạng thái workflow: {summary}')
        active = status_counts.get('processing', 0)
        failed = status_counts.get('failed', 0)
        if failed:
            state, text = 'warn', f'FAILED: {failed} project'
        elif active:
            state, text = 'busy', f'RUNNING: {active} pipeline'
        else:
            state, text = 'ok', 'ALL SYSTEMS READY'
        self.control_badge.setProperty('state', state)
        self.control_badge.style().unpolish(self.control_badge)
        self.control_badge.style().polish(self.control_badge)
        self.control_badge.setText(text)

        lines = []
        for row in projects[:8]:
            lines.append(
                f"[{row['status']:<11}] {row['name']} | step={row['workflow_step']} | "
                f"progress={row['progress']}% | safety={row['safety_status']}"
            )
        self.pipeline_panel.setPlainText('\n'.join(lines) if lines else 'Chưa có project để hiển thị pipeline.')


class AccountsPage(QWidget):
    def __init__(self, db, refresh_all):
        super().__init__()
        self.db = db
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Tài khoản Google / YouTube'))
        row = QHBoxLayout()
        add_button = QPushButton('Thêm tài khoản Google (OAuth)')
        add_button.clicked.connect(self.add_account)
        remove_button = QPushButton('Xoá dòng đã chọn')
        remove_button.clicked.connect(self.remove_account)
        refresh_button = QPushButton('Tải lại')
        refresh_button.clicked.connect(self.refresh)
        row.addWidget(add_button)
        row.addWidget(remove_button)
        row.addWidget(refresh_button)
        row.addStretch()
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['ID', 'Email', 'Channel', 'Channel ID'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        layout.addWidget(QLabel('Chỉ dùng OAuth. Ứng dụng không yêu cầu hoặc lưu mật khẩu Google.'))

    def refresh(self):
        rows = self.db.accounts()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row['id'], row['email'], row['channel_title'], row['channel_id']]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(str(value or '')))

    def add_account(self):
        try:
            secret = self.db.get_setting('google_client_secret', 'data/client_secret.json')
            result = GoogleAuth(secret).login()
            self.db.add_account(**result)
            self.refresh_all()
            QMessageBox.information(self, 'Kết nối thành công', f"Đã kết nối channel: {result['channel_title']}")
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi OAuth', str(exc))

    def remove_account(self):
        row = self.table.currentRow()
        if row < 0:
            return
        account_id = int(self.table.item(row, 0).text())
        self.db.delete_account(account_id)
        self.refresh_all()


class ProjectsPage(QWidget):
    def __init__(self, db, refresh_all):
        super().__init__()
        self.db = db
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText('Tên project')
        self.new_topic = QLineEdit()
        self.new_topic.setPlaceholderText('Topic')
        self.new_account = QComboBox()
        create_button = QPushButton('Tạo project')
        create_button.clicked.connect(self.create_project)
        header.addWidget(self.new_name)
        header.addWidget(self.new_topic)
        header.addWidget(self.new_account)
        header.addWidget(create_button)
        layout.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['ID', 'Project', 'Channel', 'Status', 'Bước', 'Updated'])
        self.table.itemSelectionChanged.connect(self.load_selected_project)
        layout.addWidget(self.table)

        form_box = QGroupBox('Chi tiết project')
        form = QFormLayout(form_box)
        self.account = QComboBox()
        self.name = QLineEdit()
        self.topic = QLineEdit()
        self.title = QLineEdit()
        self.tags = QLineEdit()
        self.voice_profile = QLineEdit()
        self.script = QPlainTextEdit()
        self.description = QPlainTextEdit()
        self.media_path = self._path_field('Media/visual')
        self.voice_path = self._path_field('Voice audio')
        self.thumbnail_path = self._path_field('Thumbnail')
        self.srt_path = self._path_field('Subtitle SRT/VTT')
        self.video_path = self._path_field('Video output')
        self.thumbnail_brief = QPlainTextEdit()
        self.thumbnail_brief.setPlaceholderText('Brief thumbnail...')
        self.voice_authorized = QCheckBox('Tôi xác nhận có quyền sử dụng voice/TTS')
        self.media_authorized = QCheckBox('Tôi xác nhận có quyền sử dụng media nguồn')
        self.status = QLabel('-')
        self.safety_status = QLabel('-')
        self.timestamps = QLabel('-')

        form.addRow('Tài khoản / channel', self.account)
        form.addRow('Tên project', self.name)
        form.addRow('Topic', self.topic)
        form.addRow('Title', self.title)
        form.addRow('Tags (phân tách dấu phẩy)', self.tags)
        form.addRow('Voice profile', self.voice_profile)
        form.addRow('Script', self.script)
        form.addRow('Description', self.description)
        form.addRow('Media path', self.media_path['row'])
        form.addRow('Voice path', self.voice_path['row'])
        form.addRow('Thumbnail path', self.thumbnail_path['row'])
        form.addRow('SRT/VTT path', self.srt_path['row'])
        form.addRow('Video path', self.video_path['row'])
        form.addRow('Thumbnail brief', self.thumbnail_brief)
        form.addRow('', self.voice_authorized)
        form.addRow('', self.media_authorized)
        form.addRow('Workflow status', self.status)
        form.addRow('Safety status', self.safety_status)
        form.addRow('Timestamps', self.timestamps)
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        save_button = QPushButton('Lưu project')
        save_button.clicked.connect(self.save_project)
        delete_button = QPushButton('Xoá project')
        delete_button.clicked.connect(self.delete_project)
        buttons.addWidget(save_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        layout.addLayout(buttons)

    def _path_field(self, title):
        field = QLineEdit()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton('Browse')
        button.clicked.connect(lambda: self.pick_file(field, title))
        row_layout.addWidget(field)
        row_layout.addWidget(button)
        return {'field': field, 'row': row}

    def pick_file(self, field, title):
        file_path, _ = QFileDialog.getOpenFileName(self, title)
        if file_path:
            field.setText(file_path)

    def selected_project_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def refresh(self):
        current_project_id = self.selected_project_id()
        self.new_account.clear()
        self.account.clear()
        self.new_account.addItem('Chọn account', None)
        self.account.addItem('Chọn account', None)
        for account in self.db.accounts():
            label = f"{account['channel_title']} ({account['email']})"
            self.new_account.addItem(label, account['id'])
            self.account.addItem(label, account['id'])
        rows = self.db.projects()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [
                row['id'],
                row['name'],
                row['channel_title'] or '',
                row['status'],
                row['workflow_step'],
                row['updated_at'],
            ]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(str(value or '')))
        if current_project_id:
            self.select_project(current_project_id)
        elif rows:
            self.table.selectRow(0)
            self.load_selected_project()

    def select_project(self, project_id):
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 0).text()) == project_id:
                self.table.selectRow(row)
                self.load_selected_project()
                break

    def create_project(self):
        if not self.new_name.text().strip() or self.new_account.currentData() is None:
            return
        project_id = self.db.add_project(
            self.new_account.currentData(),
            self.new_name.text().strip(),
            self.new_topic.text().strip(),
        )
        self.new_name.clear()
        self.new_topic.clear()
        self.refresh_all()
        self.select_project(project_id)

    def load_selected_project(self):
        project_id = self.selected_project_id()
        if not project_id:
            return
        row = self.db.project(project_id)
        if not row:
            return
        self.account.setCurrentIndex(max(self.account.findData(row['account_id']), 0))
        self.name.setText(row['name'] or '')
        self.topic.setText(row['topic'] or '')
        self.title.setText(row['title'] or '')
        self.tags.setText(', '.join(json.loads(row['tags_json'] or '[]')))
        self.voice_profile.setText(row['voice_profile'] or '')
        self.script.setPlainText(row['script'] or '')
        self.description.setPlainText(row['description'] or '')
        self.media_path['field'].setText(path_text(row['media_path']))
        self.voice_path['field'].setText(path_text(row['voice_path']))
        self.thumbnail_path['field'].setText(path_text(row['thumbnail_path']))
        self.srt_path['field'].setText(path_text(row['srt_path']))
        self.video_path['field'].setText(path_text(row['video_path']))
        self.thumbnail_brief.setPlainText(row['thumbnail_brief'] or '')
        self.voice_authorized.setChecked(bool(row['voice_authorized']))
        self.media_authorized.setChecked(bool(row['media_authorized']))
        self.status.setText(f"{row['status']} ({row['progress']}%) - bước {row['workflow_step']}")
        self.safety_status.setText(row['safety_status'] or 'pending')
        self.timestamps.setText(f"Tạo: {row['created_at']} | Cập nhật: {row['updated_at']}")

    def save_project(self):
        project_id = self.selected_project_id()
        if not project_id:
            return
        self.db.update_project(
            project_id,
            account_id=self.account.currentData(),
            name=self.name.text().strip(),
            topic=self.topic.text().strip(),
            title=self.title.text().strip(),
            script=self.script.toPlainText().strip(),
            description=self.description.toPlainText().strip(),
            tags_json=json.dumps(parse_tags(self.tags.text()), ensure_ascii=False),
            media_path=self.media_path['field'].text().strip(),
            voice_path=self.voice_path['field'].text().strip(),
            thumbnail_path=self.thumbnail_path['field'].text().strip(),
            srt_path=self.srt_path['field'].text().strip(),
            video_path=self.video_path['field'].text().strip(),
            voice_profile=self.voice_profile.text().strip(),
            thumbnail_brief=self.thumbnail_brief.toPlainText().strip(),
            voice_authorized=1 if self.voice_authorized.isChecked() else 0,
            media_authorized=1 if self.media_authorized.isChecked() else 0,
        )
        self.refresh_all()
        QMessageBox.information(self, 'Đã lưu', 'Đã cập nhật project.')

    def delete_project(self):
        project_id = self.selected_project_id()
        if not project_id:
            return
        self.db.delete_project(project_id)
        self.refresh_all()


class WorkflowPage(QWidget):
    def __init__(self, db, pipeline, settings_provider, refresh_all):
        super().__init__()
        self.db = db
        self.pipeline = pipeline
        self.settings_provider = settings_provider
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Quy trình V5'))
        self.project = QComboBox()
        layout.addWidget(self.project)

        steps = QGridLayout()
        self.buttons = {}
        actions = [
            ('generate_script', '1. Tạo script'),
            ('generate_voice', '2. Tạo voice'),
            ('generate_subtitles', '3. Tạo subtitle'),
            ('dub_video', '4. Lồng tiếng video'),
            ('thumbnail_brief', '5. Tạo brief thumbnail'),
            ('assemble_video', '6. Ghép video tĩnh'),
            ('safety_check', '7. Safety check'),
            ('approve', '8. Human approval'),
        ]
        for index, (task_name, label) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(lambda _, task=task_name: self.start_task(task))
            self.buttons[task_name] = button
            steps.addWidget(button, index // 2, index % 2)
        layout.addLayout(steps)

        controls = QHBoxLayout()
        self.retry_button = QPushButton('Retry tác vụ gần nhất')
        self.retry_button.clicked.connect(self.retry_latest)
        self.cancel_button = QPushButton('Huỷ tác vụ đang chạy')
        self.cancel_button.clicked.connect(self.cancel_task)
        controls.addWidget(self.retry_button)
        controls.addWidget(self.cancel_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.progress = QProgressBar()
        self.message = QLabel('-')
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)
        layout.addWidget(self.report, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)

    def refresh(self):
        current = self.project.currentData()
        self.project.clear()
        for row in self.db.projects():
            self.project.addItem(f"{row['name']} — {row['status']} — {row['channel_title'] or 'No channel'}", row['id'])
        if current is not None:
            index = self.project.findData(current)
            if index >= 0:
                self.project.setCurrentIndex(index)
        self.refresh_status()

    def current_project_id(self):
        return self.project.currentData()

    def start_task(self, task_name):
        project_id = self.current_project_id()
        if not project_id:
            self.message.setText('Hãy chọn project.')
            return
        try:
            self.pipeline.start(project_id, task_name, self.settings_provider())
            self.message.setText(f'Đã bắt đầu: {task_name}')
            self.refresh_all()
        except Exception as exc:
            self.message.setText(str(exc))

    def retry_latest(self):
        project_id = self.current_project_id()
        if not project_id:
            return
        latest = self.db.latest_pipeline(project_id)
        if not latest:
            self.message.setText('Chưa có tác vụ nào để retry.')
            return
        self.start_task(latest['task_name'])

    def cancel_task(self):
        project_id = self.current_project_id()
        if not project_id:
            return
        self.pipeline.cancel(project_id)
        self.message.setText('Đã gửi yêu cầu huỷ.')

    def refresh_status(self):
        project_id = self.current_project_id()
        if not project_id:
            self.progress.setValue(0)
            self.report.setPlainText('')
            return
        project = self.db.project(project_id)
        latest = self.db.latest_pipeline(project_id)
        if project:
            self.message.setText(
                f"Project: {project['status']} | bước: {project['workflow_step']} | "
                f"safety: {project['safety_status']} | lỗi gần nhất: {project['last_error'] or '-'}"
            )
        if latest:
            self.progress.setValue(int(latest['progress'] or 0))
            logs = self.db.pipeline_logs(project_id)
            report = '\n'.join(logs[-40:])
            if project and project['safety_report_json'] and project['safety_report_json'] != '{}':
                report += '\n\nSafety report:\n' + json.dumps(
                    json.loads(project['safety_report_json']),
                    ensure_ascii=False,
                    indent=2,
                )
            self.report.setPlainText(report.strip())


class VoiceStudioPage(QWidget):
    def __init__(self, db, pipeline, settings_provider, refresh_all):
        super().__init__()
        self.db = db
        self.pipeline = pipeline
        self.settings_provider = settings_provider
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Voice Studio'))
        self.project = QComboBox()
        self.project.currentIndexChanged.connect(self.load_project)
        layout.addWidget(self.project)

        form_box = QGroupBox('Thiết lập voice & dubbing')
        form = QFormLayout(form_box)
        self.provider = QComboBox()
        self.provider.addItem('Local Windows SAPI (offline)', 'sapi')
        self.provider.addItem('HTTP/API provider', 'http')
        self.provider.currentIndexChanged.connect(self.update_provider_hint)
        self.voice_profile = QLineEdit()
        self.language = QLineEdit('vi-VN')
        self.speed = QLineEdit('1.0')
        self.pitch = QLineEdit('0.0')
        self.emotion = QLineEdit()
        self.pause_ms = QLineEdit('150')
        self.output_format = QComboBox()
        self.output_format.addItems(['wav', 'mp3'])
        self.fit_strategy = QComboBox()
        self.fit_strategy.addItems(['speed', 'trim', 'warn'])
        self.sample_path = self._path_field('Mẫu giọng WAV/MP3/M4A/OGG/FLAC')
        self.text_source_path = self._path_field('Nguồn văn bản .txt/.srt/.vtt')
        self.video_source_path = self._path_field('Video nguồn để lồng tiếng')
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText('Nhập văn bản tiếng Việt để tạo voice hoặc lưu script riêng cho Voice Studio…')
        self.authorized = QCheckBox('Tôi xác nhận tôi sở hữu hoặc được ủy quyền sử dụng voice/mẫu giọng này')
        self.provider_hint = QLabel()
        self.provider_hint.setWordWrap(True)
        self.output_path = QLabel('-')

        form.addRow('Provider', self.provider)
        form.addRow('Voice profile / voice id', self.voice_profile)
        form.addRow('Ngôn ngữ', self.language)
        form.addRow('Tốc độ', self.speed)
        form.addRow('Pitch', self.pitch)
        form.addRow('Cảm xúc', self.emotion)
        form.addRow('Khoảng nghỉ (ms)', self.pause_ms)
        form.addRow('Định dạng output', self.output_format)
        form.addRow('Fit nếu audio dài hơn timestamp', self.fit_strategy)
        form.addRow('Mẫu giọng', self.sample_path['row'])
        form.addRow('Text/subtitle source', self.text_source_path['row'])
        form.addRow('Video source', self.video_source_path['row'])
        form.addRow('Văn bản trực tiếp', self.text_input)
        form.addRow('', self.authorized)
        form.addRow('Gợi ý provider', self.provider_hint)
        form.addRow('Output hiện tại', self.output_path)
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        save_button = QPushButton('Lưu Voice Studio')
        save_button.clicked.connect(self.save_project_voice)
        preview_button = QPushButton('Preview')
        preview_button.clicked.connect(lambda: self.start_task('preview_voice'))
        generate_button = QPushButton('Generate')
        generate_button.clicked.connect(lambda: self.start_task('generate_voice'))
        dub_button = QPushButton('Lồng tiếng video')
        dub_button.clicked.connect(lambda: self.start_task('dub_video'))
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.cancel_task)
        download_wav_button = QPushButton('Download WAV')
        download_wav_button.clicked.connect(lambda: self.download_audio('wav'))
        download_mp3_button = QPushButton('Download MP3')
        download_mp3_button.clicked.connect(lambda: self.download_audio('mp3'))
        for widget in [save_button, preview_button, generate_button, dub_button, cancel_button, download_wav_button, download_mp3_button]:
            buttons.addWidget(widget)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.progress = QProgressBar()
        self.status = QLabel('-')
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.log, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)
        self.update_provider_hint()

    def _path_field(self, title):
        field = QLineEdit()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton('Browse')
        button.clicked.connect(lambda: self.pick_file(field, title))
        row_layout.addWidget(field)
        row_layout.addWidget(button)
        return {'field': field, 'row': row}

    def pick_file(self, field, title):
        file_path, _ = QFileDialog.getOpenFileName(self, title)
        if file_path:
            field.setText(file_path)

    def refresh(self):
        current = self.project.currentData()
        self.project.blockSignals(True)
        self.project.clear()
        for row in self.db.projects():
            self.project.addItem(f"{row['name']} — {row['status']} — {row['channel_title'] or 'No channel'}", row['id'])
        self.project.blockSignals(False)
        if current is not None:
            index = self.project.findData(current)
            if index >= 0:
                self.project.setCurrentIndex(index)
        if self.project.count() and self.project.currentIndex() < 0:
            self.project.setCurrentIndex(0)
        self.load_project()
        self.refresh_status()

    def current_project(self):
        project_id = self.project.currentData()
        return self.db.project(project_id) if project_id else None

    def load_project(self):
        project = self.current_project()
        if not project:
            return
        settings = VoiceSettings.from_project(project)
        self.provider.setCurrentIndex(max(self.provider.findData(settings.provider or project['voice_provider'] or 'sapi'), 0))
        self.voice_profile.setText(settings.voice_profile or project['voice_profile'] or '')
        self.language.setText(settings.language or 'vi-VN')
        self.speed.setText(str(settings.speed))
        self.pitch.setText(str(settings.pitch))
        self.emotion.setText(settings.emotion or '')
        self.pause_ms.setText(str(settings.pause_ms))
        self.output_format.setCurrentIndex(max(self.output_format.findText(settings.output_format or 'wav'), 0))
        self.fit_strategy.setCurrentIndex(max(self.fit_strategy.findText(settings.fit_strategy or 'speed'), 0))
        self.sample_path['field'].setText(path_text(settings.sample_path or project['voice_sample_path']))
        source_path = project['srt_path'] or settings.text_source_path or project['text_source_path'] or ''
        self.text_source_path['field'].setText(path_text(source_path))
        self.video_source_path['field'].setText(path_text(project['media_path']))
        self.text_input.setPlainText(project['script'] or '')
        self.authorized.setChecked(bool(project['voice_authorized']))
        self.output_path.setText(project['voice_path'] or '-')
        self.update_provider_hint()

    def collect_settings(self):
        return VoiceSettings(
            provider=self.provider.currentData() or 'sapi',
            voice_profile=self.voice_profile.text().strip(),
            language=self.language.text().strip() or 'vi-VN',
            speed=parse_float_text(self.speed.text(), 1.0),
            pitch=parse_float_text(self.pitch.text(), 0.0),
            emotion=self.emotion.text().strip(),
            pause_ms=parse_int_text(self.pause_ms.text(), 150),
            output_format=self.output_format.currentText(),
            clone_enabled=bool(self.sample_path['field'].text().strip()),
            fit_strategy=self.fit_strategy.currentText(),
            sample_path=self.sample_path['field'].text().strip(),
            text_source_path=self.text_source_path['field'].text().strip(),
        )

    def save_project_voice(self, silent=False):
        project = self.current_project()
        if not project:
            return False
        settings = self.collect_settings()
        try:
            settings.validate(ffmpeg_path=self.settings_provider().get('ffmpeg_path', 'ffmpeg'))
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, 'Voice Studio', str(exc))
            else:
                self.status.setText(str(exc))
            return False
        source_path = settings.text_source_path
        srt_path = source_path if source_path.lower().endswith(('.srt', '.vtt')) else ''
        text_source_path = source_path if source_path.lower().endswith('.txt') else ''
        self.db.update_project(
            project['id'],
            script=self.text_input.toPlainText().strip(),
            media_path=self.video_source_path['field'].text().strip(),
            voice_profile=settings.voice_profile,
            voice_provider=settings.provider,
            voice_settings_json=settings.to_json(),
            voice_sample_path=settings.sample_path,
            text_source_path=text_source_path,
            srt_path=srt_path,
            voice_authorized=1 if self.authorized.isChecked() else 0,
        )
        self.refresh_all()
        if not silent:
            QMessageBox.information(self, 'Voice Studio', 'Đã lưu thiết lập Voice Studio.')
        return True

    def start_task(self, task_name):
        project = self.current_project()
        if not project:
            self.status.setText('Hãy chọn project.')
            return
        if not self.save_project_voice(silent=True):
            return
        try:
            self.pipeline.start(project['id'], task_name, self.settings_provider())
            self.status.setText(f'Đã bắt đầu tác vụ: {task_name}')
            self.refresh_all()
        except Exception as exc:
            self.status.setText(str(exc))

    def cancel_task(self):
        project = self.current_project()
        if not project:
            return
        self.pipeline.cancel(project['id'])
        self.status.setText('Đã gửi yêu cầu huỷ Voice Studio task.')

    def refresh_status(self):
        project = self.current_project()
        if not project:
            self.progress.setValue(0)
            self.log.setPlainText('')
            return
        latest = self.db.latest_pipeline(project['id'])
        self.output_path.setText(project['voice_path'] or '-')
        self.status.setText(
            f"Voice provider: {project['voice_provider'] or 'sapi'} | workflow: {project['status']} | "
            f"bước: {project['workflow_step']} | video: {project['video_path'] or '-'} | lỗi: {project['last_error'] or '-'}"
        )
        if latest:
            self.progress.setValue(int(latest['progress'] or 0))
            self.log.setPlainText('\n'.join(self.db.pipeline_logs(project['id'])[-60:]))

    def update_provider_hint(self):
        provider = self.provider.currentData() or 'sapi'
        if provider == 'sapi':
            self.provider_hint.setText(
                'Local/offline adapter dùng Windows SAPI. Không cần API key, không hỗ trợ voice cloning, và cần chạy trên Windows có PowerShell/System.Speech.'
            )
        else:
            self.provider_hint.setText(
                'HTTP/API adapter đọc endpoint và API key từ Settings/env. Nếu chưa cấu hình endpoint/voice id hợp lệ, app sẽ báo lỗi rõ ràng thay vì giả lập audio.'
            )

    def download_audio(self, extension):
        project = self.current_project()
        if not project or not project['voice_path']:
            QMessageBox.warning(self, 'Voice Studio', 'Chưa có audio output để tải xuống.')
            return
        source = Path(project['voice_path'])
        if not source.exists():
            QMessageBox.warning(self, 'Voice Studio', f'Không tìm thấy output hiện tại: {source}')
            return
        destination, _ = QFileDialog.getSaveFileName(self, f'Lưu file {extension.upper()}', source.stem + f'.{extension}')
        if not destination:
            return
        destination = Path(destination)
        try:
            if source.suffix.lower() == f'.{extension}':
                destination.write_bytes(source.read_bytes())
            else:
                convert_audio_format(source, destination, self.settings_provider().get('ffmpeg_path', 'ffmpeg'))
            QMessageBox.information(self, 'Voice Studio', f'Đã lưu file: {destination}')
        except Exception as exc:
            QMessageBox.critical(self, 'Voice Studio', str(exc))


class PublishPage(QWidget):
    def __init__(self, db, pipeline, refresh_all):
        super().__init__()
        self.db = db
        self.pipeline = pipeline
        self.refresh_all = refresh_all
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Xuất bản / Lên lịch'))
        self.project = QComboBox()
        layout.addWidget(self.project)
        self.privacy = QComboBox()
        self.privacy.addItems(['private', 'unlisted', 'public'])
        self.schedule_enabled = QCheckBox('Lên lịch publishAt')
        self.schedule = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self.schedule.setCalendarPopup(True)
        self.schedule.setEnabled(False)
        self.schedule_enabled.toggled.connect(self.schedule.setEnabled)
        self.preview = QLabel('-')
        upload_button = QPushButton('Upload / Schedule')
        upload_button.clicked.connect(self.publish)
        layout.addWidget(self.privacy)
        layout.addWidget(self.schedule_enabled)
        layout.addWidget(self.schedule)
        layout.addWidget(self.preview)
        layout.addWidget(upload_button)

        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(['ID', 'Project', 'Channel', 'Privacy', 'Status', 'YouTube ID'])
        layout.addWidget(self.history, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_preview)
        self.timer.start(1000)

    def refresh(self):
        current = self.project.currentData()
        self.project.clear()
        for row in self.db.projects():
            self.project.addItem(f"{row['name']} — {row['status']}", row['id'])
        if current is not None:
            index = self.project.findData(current)
            if index >= 0:
                self.project.setCurrentIndex(index)
        rows = self.db.uploads()
        self.history.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row['id'], row['project_name'], row['channel_title'], row['privacy'], row['status'], row['youtube_id']]
            for j, value in enumerate(values):
                self.history.setItem(i, j, QTableWidgetItem(str(value or '')))
        self.refresh_preview()

    def refresh_preview(self):
        project = self.db.project(self.project.currentData()) if self.project.currentData() else None
        if not project:
            self.preview.setText('Chọn project để xem điều kiện upload.')
            return
        self.preview.setText(
            f"Title: {project['title'] or '-'} | Safety: {project['safety_status']} | "
            f"Status: {project['status']} | Video: {project['video_path'] or '-'}"
        )

    def publish(self):
        project_id = self.project.currentData()
        project = self.db.project(project_id) if project_id else None
        if not project:
            QMessageBox.warning(self, 'Thiếu project', 'Hãy chọn project.')
            return
        if project['safety_status'] != 'passed' or project['status'] != 'approved':
            QMessageBox.warning(self, 'Chưa đủ điều kiện', 'Project phải safety-pass và human-approved trước khi upload.')
            return
        publish_at = None
        if self.schedule_enabled.isChecked():
            publish_at = self.schedule.dateTime().toString(Qt.DateFormat.ISODate)
        try:
            self.pipeline.start(
                project_id,
                'upload_video',
                {
                    'privacy': self.privacy.currentText(),
                    'publish_at': publish_at,
                },
            )
            self.refresh_all()
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi upload', str(exc))


class AnalyticsPage(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Analytics'))
        self.account = QComboBox()
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        refresh_button = QPushButton('Đồng bộ analytics từ YouTube')
        refresh_button.clicked.connect(self.refresh_analytics)
        layout.addWidget(self.account)
        layout.addWidget(refresh_button)
        layout.addWidget(self.output, 1)

    def refresh(self):
        current = self.account.currentData()
        self.account.clear()
        for row in self.db.accounts():
            self.account.addItem(f"{row['channel_title']} ({row['email']})", row['id'])
        if current is not None:
            index = self.account.findData(current)
            if index >= 0:
                self.account.setCurrentIndex(index)

    def refresh_analytics(self):
        account = self.db.account(self.account.currentData()) if self.account.currentData() else None
        if not account:
            return
        try:
            snapshot = YouTubeService(account['token_json']).analytics_snapshot()
            self.db.save_analytics(
                account['id'],
                snapshot['channel_id'],
                snapshot['views'],
                snapshot['subscribers'],
                snapshot['video_count'],
            )
            self.output.setPlainText(json.dumps(snapshot, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.output.setPlainText(str(exc))


class SettingsPage(QWidget):
    def __init__(self, db, refresh_all):
        super().__init__()
        self.db = db
        self.refresh_all = refresh_all
        self.fields = {}
        self.defaults = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        settings = [
            ('google_client_secret', 'Google OAuth client JSON', 'data/client_secret.json'),
            ('ai_endpoint', 'AI endpoint', ''),
            ('ai_api_key', 'AI API key', ''),
            ('ai_model', 'AI model', ''),
            ('voice_endpoint', 'Voice endpoint', ''),
            ('voice_api_key', 'Voice API key', ''),
            ('voice_id', 'Voice ID', ''),
            ('voice_http_timeout', 'Voice HTTP timeout (s)', '90'),
            ('ffmpeg_path', 'FFmpeg path', 'ffmpeg'),
            ('output_dir', 'Output directory', str((Path(os.environ.get('AIYS_DATA_DIR', 'data')).expanduser() / 'outputs').resolve())),
            ('locale', 'Locale', 'vi-VN'),
            ('log_level', 'Logging level', 'INFO'),
        ]
        for key, label, default in settings:
            self.defaults[key] = default
            field = QLineEdit(self.db.get_setting(key, default))
            if 'key' in key:
                field.setEchoMode(QLineEdit.Password)
            form.addRow(label, field)
            self.fields[key] = field
        layout.addLayout(form)

        actions = QHBoxLayout()
        save_button = QPushButton('Lưu Settings')
        save_button.clicked.connect(self.save)
        backup_button = QPushButton('Backup database')
        backup_button.clicked.connect(self.backup)
        restore_button = QPushButton('Restore database')
        restore_button.clicked.connect(self.restore)
        actions.addWidget(save_button)
        actions.addWidget(backup_button)
        actions.addWidget(restore_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QLabel('-')
        layout.addWidget(self.status)
        layout.addWidget(
            QLabel(
                'Lưu ý: không đóng gói client_secret.json hoặc API key thật. '
                'Bạn có thể dùng biến môi trường hoặc nhập trong UI sau khi cài đặt.'
            )
        )
        layout.addStretch()

    def refresh(self):
        for key, field in self.fields.items():
            if not field.hasFocus():
                field.setText(self.db.get_setting(key, self.defaults[key]))

    def save(self):
        for key, field in self.fields.items():
            self.db.set_setting(key, field.text().strip())
        self.refresh_all()
        self.status.setText('Đã lưu settings.')

    def backup(self):
        destination, _ = QFileDialog.getSaveFileName(self, 'Lưu backup database', 'studio-backup.db')
        if not destination:
            return
        path = self.db.backup_to(destination)
        self.status.setText(f'Đã backup database: {path}')

    def restore(self):
        source, _ = QFileDialog.getOpenFileName(self, 'Chọn file backup database', '', 'DB (*.db *.sqlite)')
        if not source:
            return
        self.db.restore_from(source)
        self.refresh_all()
        self.status.setText('Đã restore database. Nếu đang có job chạy dở, hãy kiểm tra lại trạng thái workflow.')
