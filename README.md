# AI YouTube Studio V5

Desktop app Python/PySide6 cho workflow sản xuất video YouTube an toàn:

**Project → Script → Voice/TTS → Subtitle → Video Assembly → Thumbnail → Safety Check → Human Approval → Upload/Schedule**

This repository now contains an executable-oriented V5 codebase instead of only the archived V4 zip.

## Tính năng chính / Key features

- Giao diện desktop PySide6, ưu tiên tiếng Việt.
- Google OAuth + YouTube Data API chính thức, không lưu mật khẩu Google.
- Project Manager lưu topic, script, title, description, tags, media, thumbnail, SRT, video, voice profile, trạng thái workflow, progress và lỗi gần nhất.
- Pipeline chạy nền cho các bước script/subtitle/thumbnail/video/safety/approval/upload.
- Cancel/retry/log cho từng task; job đang chạy dở được đánh dấu failed rõ ràng khi app mở lại.
- Subtitle service hỗ trợ tạo SRT, parse/validate SRT + VTT.
- Safety Center chặn fake engagement, bypass language, title trùng, thiếu xác nhận voice/media rights.
- FFmpeg assembly có kiểm tra FFmpeg, file input/output và progress message.
- Upload/Schedule qua YouTube Data API với lịch sử upload.
- Backup/restore SQLite database ngay trong Settings.
- Script build Windows một lệnh bằng PyInstaller, tạo `AIYouTubeStudio.exe`.

## Kiến trúc / Architecture

- `main.py`: entrypoint ứng dụng desktop.
- `app/db.py`: SQLite + migration nhẹ + state cho project/pipeline.
- `app/ui/main_window.py`: giao diện chính V5.
- `app/services/ai.py`: adapter AI provider.
- `app/services/voice.py`: adapter TTS/voice với authorization gate.
- `app/services/subtitles.py`: tạo/parse/validate subtitle.
- `app/services/video_assembler.py`: FFmpeg wrapper.
- `app/services/safety.py`: safety review.
- `app/services/pipeline.py`: background workflow runner.
- `app/services/google_auth.py`: OAuth desktop flow.
- `app/services/youtube_service.py`: YouTube Data API upload/analytics.

## Cài đặt chạy local / Local run

1. Cài Python 3.11+.
2. Cài dependency:
   ```bash
   pip install -r requirements.txt
   ```
3. Tạo OAuth Desktop App trong Google Cloud.
4. Bật **YouTube Data API v3**.
5. Lưu `client_secret.json` vào `data/client_secret.json` **hoặc** cấu hình đường dẫn trong Settings / biến môi trường `AIYS_GOOGLE_CLIENT_SECRET`.
6. Cài FFmpeg và bảo đảm `ffmpeg` có trên `PATH`, hoặc nhập đường dẫn đầy đủ trong Settings.
7. Chạy:
   ```bash
   python main.py
   ```

## Cấu hình / Configuration

Xem `config.example.json`. Có thể nhập cấu hình trong Settings hoặc qua biến môi trường:

- `AIYS_GOOGLE_CLIENT_SECRET`
- `AIYS_AI_ENDPOINT`
- `AIYS_AI_API_KEY`
- `AIYS_AI_MODEL`
- `AIYS_VOICE_ENDPOINT`
- `AIYS_VOICE_API_KEY`
- `AIYS_VOICE_ID`
- `AIYS_FFMPEG_PATH`
- `AIYS_OUTPUT_DIR`
- `AIYS_LOCALE`
- `AIYS_LOG_LEVEL`

> Không commit `client_secret.json`, OAuth tokens hoặc API key thật.

## Voice/TTS boundary

V5 **không giả vờ** tích hợp provider nếu chưa có API contract/credential thật.

- App có adapter + settings + authorization gate.
- Nếu chưa cấu hình provider hợp lệ, UI sẽ báo rõ rằng người dùng cần tự cung cấp provider chính thức.
- Render TTS theo từng câu subtitle chỉ được bật khi adapter/provider thực tế khai báo hỗ trợ.

## Windows build / Packaging

### Dùng bản `.exe` (không cần cài Python)

1. Vào tab **Actions** → workflow **Windows Build EXE**.
2. Mở run thành công và tải artifact `AIYouTubeStudio-windows`.
3. Giải nén file ZIP.
4. Chạy trực tiếp `AIYouTubeStudio.exe`.

Khi chạy lần đầu, app tự tạo:

- `data/studio.db`
- `data/logs/`
- `data/outputs/`
- `data/config.example.json` (copy từ template nếu chưa có)

### Build thủ công trên Windows (cho developer)

```bash
pip install -r requirements.txt -r requirements-build.txt
python build_windows.py
```

Kết quả build nằm trong `dist/AIYouTubeStudio/` với file chạy chính `AIYouTubeStudio.exe`.

### Ghi chú đóng gói

- Không đóng gói `client_secret.json`.
- Không đóng gói token hoặc API key thật.
- `config.example.json` và README được đưa vào build để người dùng có template cấu hình.
- CI build chạy trên `windows-latest` để tạo artifact `.exe` thật.

## V4 compatibility checklist

- [x] Quản lý nhiều Google/YouTube account.
- [x] OAuth chính thức + lấy channel ID/tên kênh.
- [x] Project manager (topic/script/title/description/tags/media/voice/thumbnail/subtitle/video).
- [x] AI script adapter.
- [x] Voice/TTS adapter + quyền sử dụng voice.
- [x] FFmpeg video assembly.
- [x] Tạo/parse/validate SRT + VTT.
- [x] Thumbnail brief/studio flow.
- [x] Upload YouTube thật (private/unlisted/public + publishAt schedule).
- [x] Analytics snapshot + upload history.
- [x] Safety center + human approval gate trước upload.
- [x] Backward compatible DB migration cho project dữ liệu cũ.

## Kiểm thử / Tests

Chạy test:

```bash
python -m unittest discover -s tests -v
```

## Troubleshooting

- **Missing OAuth client file**: kiểm tra `google_client_secret`.
- **FFmpeg chưa cài**: cấu hình `ffmpeg_path` trong Settings.
- **Safety blocked**: kiểm tra duplicate title, quyền voice/media, hoặc metadata nguy hiểm.
- **Upload bị từ chối**: kiểm tra hạn mức API, trạng thái project đã `approved`, và `publishAt` có hợp lệ không.
- **TTS chưa chạy**: đây là adapter an toàn; cần provider thật và xác nhận quyền sử dụng voice.

## Giới hạn thực tế / Real limitations

- AI/TTS/thumbnail generation ngoài phần adapter vẫn phụ thuộc credential và API contract bên ngoài.
- OAuth token hiện vẫn là local SQLite storage theo khả năng kiến trúc hiện tại; không có secure vault riêng.
- Channel selection theo mô hình account/channel đã kết nối trong app; nếu cần workflow đa-channel sâu hơn từ cùng một Google identity thì cần mở rộng thêm UI/API flow.

## Safety scope

Project này cố ý **không** triển khai:

- fake views / likes / subscribers / comments
- comment spam / engagement spam
- bypass CAPTCHA / rate limit / restriction / enforcement
- lưu hoặc yêu cầu mật khẩu Google
- voice/media usage không có quyền rõ ràng
