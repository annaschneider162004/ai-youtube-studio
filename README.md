# AI YouTube Studio V5

Desktop app Python/PySide6 cho workflow sản xuất video YouTube an toàn:

**Project → Script → Voice/TTS → Subtitle → Video Assembly → Thumbnail → Safety Check → Human Approval → Upload/Schedule**

This repository now contains an executable-oriented V5 codebase instead of only the archived V4 zip.

## Tính năng chính / Key features

- Giao diện desktop PySide6, ưu tiên tiếng Việt.
- Google OAuth + YouTube Data API chính thức, không lưu mật khẩu Google.
- Project Manager lưu topic, script, title, description, tags, media, thumbnail, SRT/VTT/TXT source, video, voice profile/provider, trạng thái workflow, progress và lỗi gần nhất.
- Voice Studio mới: nhập text tiếng Việt, chọn provider/voice profile, preview/generate WAV/MP3, upload sample cho voice cloning khi đã xác nhận quyền sử dụng.
- Pipeline chạy nền cho các bước script/voice/subtitle/dubbing/video/safety/approval/upload.
- Cancel/retry/log cho từng task; job đang chạy dở được đánh dấu failed rõ ràng khi app mở lại.
- Subtitle service hỗ trợ tạo SRT, parse/validate SRT + VTT; Voice Studio hỗ trợ dùng `.txt`, `.srt`, `.vtt` để render theo từng câu/timestamp.
- Safety Center chặn fake engagement, bypass language, title trùng, thiếu xác nhận voice/media rights.
- FFmpeg assembly có kiểm tra FFmpeg, file input/output, progress message, mux audio mới vào video và xuất track WAV/MP3 an toàn.
- Upload/Schedule qua YouTube Data API với lịch sử upload.
- Backup/restore SQLite database ngay trong Settings.
- Script build Windows một lệnh bằng PyInstaller, tạo `AIYouTubeStudio.exe`.

## Kiến trúc / Architecture

- `main.py`: entrypoint ứng dụng desktop.
- `app/db.py`: SQLite + migration nhẹ + state cho project/pipeline.
- `app/ui/main_window.py`: giao diện chính V5.
- `app/services/ai.py`: adapter AI provider.
- `app/services/voice.py`: adapter TTS/voice, validation sample/output, subtitle dubbing timeline và authorization gate.
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
- `AIYS_VOICE_HTTP_TIMEOUT`
- `AIYS_FFMPEG_PATH`
- `AIYS_OUTPUT_DIR`
- `AIYS_LOCALE`
- `AIYS_LOG_LEVEL`

> Không commit `client_secret.json`, OAuth tokens hoặc API key thật.

## Voice Studio / Voice-TTS boundary

V5 **không giả vờ** tích hợp provider nếu chưa có API contract/credential thật. Voice Studio mới giữ nguyên nguyên tắc đó nhưng bổ sung luồng chạy được và trung thực hơn:

- **Local/offline adapter**: dùng **Windows SAPI** cho bản `.exe`/Windows khi máy có PowerShell + `System.Speech`; không cần API key, không nhúng model weights, không hỗ trợ voice cloning.
- **HTTP/API adapter**: cấu hình qua `AIYS_VOICE_ENDPOINT`, `AIYS_VOICE_API_KEY`, `AIYS_VOICE_ID` hoặc Settings; app chỉ gửi request khi endpoint được cấu hình rõ ràng.
- **Authorization gate bắt buộc**: voice/TTS và đặc biệt là voice cloning chỉ chạy khi người dùng tick xác nhận họ sở hữu hoặc được ủy quyền sử dụng voice/mẫu giọng.
- **Upload sample**: kiểm tra định dạng, kích thước, thời lượng; không commit sample thật vào repo.
- **Subtitle dubbing**: `.srt`/`.vtt` render theo từng cue/timestamp, giữ khoảng lặng, cảnh báo audio dài hơn segment và hỗ trợ fit bằng `speed` hoặc `trim`. `.txt` được chia câu tuần tự để tạo track dubbing không timestamp.
- Nếu provider chưa cấu hình hoặc không hỗ trợ tính năng nào đó, UI sẽ báo lỗi hướng dẫn thay vì tạo audio giả.

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
- Không đóng gói model weights lớn, voice sample thật hoặc secret cho provider voice.
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
- **TTS chưa chạy**: kiểm tra provider đã cấu hình hay chưa. Local/offline chỉ hỗ trợ Windows SAPI; HTTP/API cần endpoint/voice id thật.
- **Voice cloning bị chặn**: cần upload sample hợp lệ và tick xác nhận quyền sở hữu/ủy quyền giọng nói.
- **Dubbing lệch timestamp**: chọn `fit strategy = speed` hoặc `trim`, đồng thời kiểm tra FFmpeg/ffprobe đã cài.

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
