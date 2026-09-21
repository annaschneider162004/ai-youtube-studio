from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDateTime
from pathlib import Path
import json
from app.services.google_auth import GoogleAuth
from app.services.ai import AIProvider
from app.services.youtube_service import YouTubeService
from app.services.video_assembler import VideoAssembler
from app.services.subtitles import make_srt
from app.services.safety import review

class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__(); self.db=db; self.setWindowTitle('AI YouTube Studio V4'); self.resize(1450,900)
        root=QWidget(); layout=QHBoxLayout(root); self.nav=QListWidget(); self.nav.addItems(['Dashboard','Accounts','Projects','AI Script','Video','Subtitles','Thumbnail','Publish','Analytics','Safety','Settings']); self.nav.setFixedWidth(190)
        self.stack=QStackedWidget(); self.pages=[Dashboard(db),Accounts(db),Projects(db),ScriptPage(db),VideoPage(db),SubtitlePage(db),ThumbnailPage(),PublishPage(db),AnalyticsPage(db),SafetyPage(db),SettingsPage(db)]
        for p in self.pages:self.stack.addWidget(p)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); layout.addWidget(self.nav); layout.addWidget(self.stack,1); self.setCentralWidget(root)
        self.nav.setCurrentRow(0)

class Dashboard(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); t=QLabel('AI YouTube Studio V4'); t.setStyleSheet('font-size:30px;font-weight:700;'); l.addWidget(t); l.addWidget(QLabel('One workspace: Accounts → Project → Script → Voice/Video → Safety → Publish → Analytics'))
        self.stats=QLabel(); l.addWidget(self.stats); l.addStretch(); self.refresh()
    def refresh(self): self.stats.setText(f'Accounts: {len(self.db.accounts())}    Projects: {len(self.db.projects())}    Upload records: {len(self.db.uploads())}')

class Accounts(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Google / YouTube Accounts'))
        row=QHBoxLayout(); add=QPushButton('Add Google account (OAuth)'); add.clicked.connect(self.add); delete=QPushButton('Remove selected'); delete.clicked.connect(self.remove); refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh); row.addWidget(add); row.addWidget(delete); row.addWidget(refresh); row.addStretch(); l.addLayout(row)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(['ID','Email','Channel','Channel ID']); self.table.horizontalHeader().setStretchLastSection(True); l.addWidget(self.table); l.addWidget(QLabel('OAuth only. The app does not ask for or store your Google password.')) ; self.refresh()
    def refresh(self):
        rows=self.db.accounts(); self.table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate([r['id'],r['email'],r['channel_title'],r['channel_id']]): self.table.setItem(i,j,QTableWidgetItem(str(v or '')))
    def add(self):
        try:
            r=GoogleAuth(self.db.get_setting('google_client_secret','data/client_secret.json')).login(); self.db.add_account(**r); self.refresh(); QMessageBox.information(self,'Connected',f"Connected: {r['channel_title']}")
        except Exception as e: QMessageBox.critical(self,'OAuth error',str(e))
    def remove(self):
        row=self.table.currentRow()
        if row<0:return
        aid=int(self.table.item(row,0).text()); self.db.delete_account(aid); self.refresh()

class Projects(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Content Projects'))
        form=QHBoxLayout(); self.name=QLineEdit(); self.name.setPlaceholderText('Project name'); self.topic=QLineEdit(); self.topic.setPlaceholderText('Topic'); self.account=QComboBox(); self.load_accounts(); b=QPushButton('Create project'); b.clicked.connect(self.create); form.addWidget(self.name); form.addWidget(self.topic); form.addWidget(self.account); form.addWidget(b); l.addLayout(form)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(['ID','Project','Channel','Topic','Status']); l.addWidget(self.table); self.refresh()
    def load_accounts(self):
        self.account.clear(); self.account.addItem('Select account',None)
        for r in self.db.accounts(): self.account.addItem(f"{r['channel_title']} ({r['email']})",r['id'])
    def create(self):
        if not self.name.text().strip() or self.account.currentData() is None:return
        self.db.add_project(self.account.currentData(),self.name.text().strip(),self.topic.text().strip()); self.refresh()
    def refresh(self):
        self.load_accounts(); rows=self.db.projects(); self.table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[r['id'],r['name'],r['channel_title'] or '',r['topic'],r['status']]
            for j,v in enumerate(vals): self.table.setItem(i,j,QTableWidgetItem(str(v)))

class ScriptPage(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('AI Script Studio'))
        self.topic=QLineEdit(); self.topic.setPlaceholderText('Topic'); l.addWidget(self.topic); self.language=QComboBox(); self.language.addItems(['English','Vietnamese']); l.addWidget(self.language); b=QPushButton('Generate script'); b.clicked.connect(self.generate); l.addWidget(b); self.out=QTextEdit(); l.addWidget(self.out); self.status=QLabel(); l.addWidget(self.status)
    def generate(self):
        try:
            ai=AIProvider(self.db.get_setting('ai_endpoint'),self.db.get_setting('ai_api_key'),self.db.get_setting('ai_model')); self.out.setPlainText(ai.generate_script(self.topic.text(),self.language.currentText())); self.status.setText('Generated. Copy/save it into a project from the workflow.')
        except Exception as e:self.status.setText(str(e))

class VideoPage(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Video Assembly'))
        self.image=QLineEdit(); self.voice=QLineEdit(); self.srt=QLineEdit(); self.output=QLineEdit('output.mp4')
        for label,field in [('Visual/image',self.image),('Voice audio',self.voice),('SRT (optional)',self.srt),('Output MP4',self.output)]:
            row=QHBoxLayout(); row.addWidget(QLabel(label)); row.addWidget(field); b=QPushButton('Browse'); b.clicked.connect(lambda _,f=field:self.pick(f)); row.addWidget(b); l.addLayout(row)
        self.run=QPushButton('Assemble video'); self.run.clicked.connect(self.assemble); l.addWidget(self.run); self.status=QLabel(); l.addWidget(self.status); l.addStretch()
    def pick(self,f):
        p,_=QFileDialog.getOpenFileName(self,'Choose file');
        if p:f.setText(p)
    def assemble(self):
        try: VideoAssembler().assemble(self.image.text(),self.voice.text(),self.output.text(),self.srt.text() or None); self.status.setText(f'Created: {self.output.text()}')
        except Exception as e:self.status.setText(str(e))

class SubtitlePage(QWidget):
    def __init__(self,db):
        super().__init__(); l=QVBoxLayout(self); l.addWidget(QLabel('Subtitle / SRT')); self.script=QTextEdit(); l.addWidget(self.script); b=QPushButton('Create SRT'); b.clicked.connect(self.create); l.addWidget(b); self.status=QLabel(); l.addWidget(self.status)
    def create(self):
        p,_=QFileDialog.getSaveFileName(self,'Save SRT','subtitles.srt','SRT (*.srt)');
        if p: make_srt(self.script.toPlainText(),p); self.status.setText(f'Created: {p}')

class ThumbnailPage(QWidget):
    def __init__(self):
        super().__init__(); l=QVBoxLayout(self); l.addWidget(QLabel('Thumbnail Studio')); self.prompt=QLineEdit(); self.prompt.setPlaceholderText('Accurate thumbnail concept'); l.addWidget(self.prompt); self.out=QTextEdit(); l.addWidget(self.out); l.addWidget(QPushButton('Create brief',clicked=self.brief))
    def brief(self): self.out.setPlainText(f'Thumbnail brief\n\nConcept: {self.prompt.text()}\n\n• One clear focal subject\n• Large readable text\n• Strong contrast\n• Accurately represents the video\n• Avoid misleading claims')

class PublishPage(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Publish / Schedule'))
        self.project=QComboBox(); self.load_projects(); l.addWidget(self.project)
        self.title=QLineEdit(); self.title.setPlaceholderText('Title'); self.desc=QTextEdit(); self.desc.setPlaceholderText('Description'); self.tags=QLineEdit(); self.tags.setPlaceholderText('Tags, comma separated'); self.file=QLineEdit(); self.privacy=QComboBox(); self.privacy.addItems(['private','unlisted','public']); self.schedule=QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600)); self.schedule.setCalendarPopup(True); self.schedule.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        for x in [self.title,self.desc,self.tags]: l.addWidget(x)
        row=QHBoxLayout(); row.addWidget(QLabel('Video file')); row.addWidget(self.file); row.addWidget(QPushButton('Browse',clicked=self.pick)); l.addLayout(row)
        row=QHBoxLayout(); row.addWidget(QLabel('Privacy')); row.addWidget(self.privacy); row.addWidget(QLabel('Schedule time')); row.addWidget(self.schedule); l.addLayout(row)
        self.approve=QCheckBox('I reviewed the final video, metadata and rights'); l.addWidget(self.approve); self.status=QLabel(); l.addWidget(self.status); l.addWidget(QPushButton('Upload / Schedule',clicked=self.publish)); l.addStretch()
    def load_projects(self):
        self.project.clear();
        for r in self.db.projects(): self.project.addItem(f"{r['name']} — {r['channel_title']}",r['id'])
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,'Video file','','Video (*.mp4 *.mov *.mkv)');
        if p:self.file.setText(p)
    def publish(self):
        if not self.approve.isChecked(): self.status.setText('Blocked: human approval is required.'); return
        pr=next((r for r in self.db.projects() if r['id']==self.project.currentData()),None)
        if not pr or not self.file.text(): self.status.setText('Select a project and video file.'); return
        account=next((r for r in self.db.accounts() if r['id']==pr['account_id']),None)
        if not account: self.status.setText('Project account not found.'); return
        result=review(self.title.text(),self.desc.toPlainText(),[r['title'] for r in self.db.conn.execute('SELECT title FROM videos WHERE title IS NOT NULL').fetchall()])
        if result['blocked']: self.status.setText('BLOCKED: '+' '.join(result['issues'])); return
        try:
            service=YouTubeService(account['token_json']); privacy=self.privacy.currentText(); publish_at=self.schedule.dateTime().toString(Qt.DateFormat.ISODate) if self.schedule.isEnabled() else None
            if self.schedule.dateTime() > QDateTime.currentDateTime(): privacy='private'
            resp=service.upload(self.file.text(),self.title.text(),self.desc.toPlainText(),[x.strip() for x in self.tags.text().split(',') if x.strip()],privacy,publish_at)
            self.db.add_upload(pr['id'],account['id'],resp.get('id',''),'uploaded',privacy,publish_at); self.db.update_project(pr['id'],title=self.title.text(),description=self.desc.toPlainText(),video_path=self.file.text(),status='uploaded'); self.status.setText(f"Success. YouTube video ID: {resp.get('id')}")
        except Exception as e: self.db.add_upload(pr['id'],account['id'],status='error',privacy=privacy,error=str(e)); self.status.setText(str(e))

class AnalyticsPage(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Channel Analytics')); self.account=QComboBox(); self.load_accounts(); l.addWidget(self.account); l.addWidget(QPushButton('Refresh from YouTube',clicked=self.refresh)); self.out=QTextEdit(); self.out.setReadOnly(True); l.addWidget(self.out)
    def load_accounts(self):
        self.account.clear();
        for r in self.db.accounts():self.account.addItem(r['channel_title'],r['id'])
    def refresh(self):
        r=next((x for x in self.db.accounts() if x['id']==self.account.currentData()),None)
        if not r:return
        try:
            snap=YouTubeService(r['token_json']).analytics_snapshot(); self.db.save_analytics(r['id'],snap['channel_id'],snap['views'],snap['subscribers'],snap['video_count']); self.out.setPlainText(json.dumps(snap,indent=2))
        except Exception as e:self.out.setPlainText(str(e))

class SafetyPage(QWidget):
    def __init__(self,db):
        super().__init__(); l=QVBoxLayout(self); l.addWidget(QLabel('Safety Center')); 
        for x in ['OAuth only; no Google passwords','No fake views / likes / subscribers','No comment spam or automated engagement','No CAPTCHA / rate-limit / restriction bypass','No deceptive metadata','Warn/block highly duplicated titles','Human approval before publish','Voice cloning only with ownership/permission'] : l.addWidget(QLabel('✓ '+x))
        l.addStretch()

class SettingsPage(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; l=QVBoxLayout(self); l.addWidget(QLabel('Settings')); self.fields={}
        for key,label,default in [('google_client_secret','Google OAuth client JSON','data/client_secret.json'),('ai_endpoint','AI endpoint',''),('ai_api_key','AI API key',''),('ai_model','AI model',''),('voice_endpoint','Voice endpoint',''),('voice_api_key','Voice API key',''),('voice_id','Voice ID','')]:
            row=QHBoxLayout(); row.addWidget(QLabel(label)); e=QLineEdit(self.db.get_setting(key,default)); e.setEchoMode(QLineEdit.Password if 'key' in key else QLineEdit.Normal); row.addWidget(e); l.addLayout(row); self.fields[key]=e
        l.addWidget(QPushButton('Save settings',clicked=self.save)); self.status=QLabel(); l.addWidget(self.status); l.addStretch()
    def save(self):
        for k,e in self.fields.items():self.db.set_setting(k,e.text())
        self.status.setText('Saved.')
