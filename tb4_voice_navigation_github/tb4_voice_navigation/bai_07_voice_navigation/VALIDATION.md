# Kết quả kiểm chứng — 06/11/2026

## Cập nhật sau phiên điều khiển giọng nói thành công

Người dùng đã xác nhận hệ thống hoạt động. Đã lưu snapshot log phiên mới vào `results/voice_session_asr.log` và `results/voice_session_navigation.log`; bảng trích tự động tại `results/voice_session_summary.json`. Ba tên “phòng học”, “phòng thí nghiệm”, “hành lang” đều có trong log ASR. Tám lượt điều hướng được trích gồm bốn lượt SUCCEEDED (A một lượt, B ba lượt) và bốn lượt STOPPED do người dùng hủy. Chưa có ARRIVED C trong snapshot; không tính các lượt hủy là lỗi hoặc suy ra tỷ lệ thành công từ 4/8. Log xác nhận CANCELING → STOPPED bằng giọng nói; chưa đo độ trễ ASR toàn tuyến hay dừng cơ khí. Báo cáo chi tiết Word/PDF ghi rõ phạm vi bằng chứng mới này.

Phần bên dưới ghi lại kết quả và các giới hạn tại từng thời điểm phát triển trước phiên mới, vì vậy các câu “chưa thử micro” hoặc “cần restart” bên dưới là trạng thái lịch sử, được cập nhật bởi mục này. Chưa có tập âm thanh gán nhãn để đo độ chính xác ASR, thử vật cản động chuẩn hóa, video hoặc URL GitHub Public đính kèm.

## Nhật ký kiểm chứng trong quá trình triển khai

- `python3 -m unittest discover -s bai_07_voice_navigation/tests -v`: **27/27 đạt**. Có 14 test logic/bản đồ, 6 test giao tiếp ROS action thật với server Nav2 giả lập (ROS_DOMAIN_ID 87) và 7 test grammar/confidence/mức âm thanh/bộ lọc.
- Sau phản hồi ASR nhận các từ không liên quan, đã bật grammar điều hướng theo cấu hình vùng; giữ `[unk]` và vùng D để từ chối yêu cầu không hợp lệ, bỏ cả câu grammar nếu có từ ngoài vocabulary model. Thêm partial, `--listen-only`, mức âm thanh và bỏ cảnh báo im lặng. Model tiếng Việt nạp được grammar và PCM im lặng không tạo lệnh; vẫn cần thử lại bằng giọng người dùng để đánh giá mức cải thiện.
- Đã tạo từ bản đồ gốc ba vùng A/B/C, ảnh nhãn uint16 và ảnh tô màu. Kiểm tra đích hợp lệ, clearance 0,35 m, liên thông, ô unknown/vật cản, đổi tọa độ với origin xoay, hash bản đồ thay đổi.
- Test parser gồm câu đơn, từ A đến B, nhiều điểm A → C → B, tên ngữ nghĩa, không dấu, hủy, vùng không có và câu mơ hồ.
- Test action gồm thứ tự A → B chỉ sau SUCCEEDED; vùng không tồn tại không gửi goal; failure/rejection không chạy tiếp; BUSY; cancel và timeout hủy phần còn lại.
- `colcon build --symlink-install --packages-select tb4_assignment`: **thành công** sau bổ sung dependency action/marker.
- Venv bài 7 import được ROS, OpenCV, Vosk, ReportLab. Model `vosk-model-small-vn-0.4` từ bài 5 nạp thành công; decode 1 giây PCM im lặng trả văn bản rỗng.
- **Gazebo headless, Nav2 thật:** mở `navigation.launch.py gui:=false rviz:=false auto_undock:=true`, localization/navigation active và undock SUCCEEDED. Gửi câu chữ “Đi đến khu vực A” qua `/voice_nav/command`: khoảng cách feedback giảm từ 4,21 m, robot đến A và trả ARRIVED/SUCCEEDED sau khoảng 41 giây. Trong lúc chạy, gửi “Đi đến khu vực D” bằng `voice_input.py` chế độ text: INVALID_COMMAND, hành trình A tiếp tục. Đây là smoke test điều hướng bằng chữ; chưa phải demo micro hoặc thử vật cản động.
- Log đã lưu tại `results/automated_tests.log`, `results/gazebo_navigation.log`, `results/gazebo_bringup_excerpt.log` (file cuối là trích đoạn bringup, không phải log đầy đủ).

Đây chưa phải số liệu độ chính xác ASR với người nói. Chưa có video nghiệm thu, chưa đo tỷ lệ nhận đúng ba câu bằng micro. Chưa thử B/C và tránh vật cản động trên Gazebo; fake Nav2 server chỉ xác minh giao tiếp/state machine. Chưa xuất bản repository GitHub vì máy không có Git CLI và chưa có remote đích.

Các lệnh chạy lại, thiết bị micro và kịch bản nghiệm thu nằm trong README/TEST_CASES. Không ghi nhãn các thử nghiệm thủ công chưa thực hiện là “đạt”.

Kiểm tra phiên launch đang chạy: hai node cùng RMW/domain; gửi thử vùng D nhận INVALID_COMMAND ở node điều hướng. Log micro nhận các mẩu rời và nhiều câu confidence thấp. Đo 3 giây PCM trực tiếp (không lưu âm thanh): RMS -10,2 dBFS, clipping 0,35%, 92,2% năng lượng dưới 150 Hz, đỉnh 35,3 Hz. Thêm high-pass Butterworth bậc 4, 150 Hz; kiểm thử giảm tín hiệu 35 Hz >40 dB, giữ tín hiệu 500 Hz, giữ trạng thái qua chunk và bypass. Chưa xác minh lại độ chính xác giọng người sau thay đổi; cần restart voice_input.

Lần thử giọng nói tiếp theo: nhận được tiền tố “đi đến khu vực” nhưng đích cuối đổi A/bê/dê và confidence 0,30–0,57; các câu bị loại đúng theo ngưỡng, không gửi goal. Bổ sung alias mặc định phòng học=A, phòng thí nghiệm=B, hành lang=C và khu vực một/hai/ba, kiểm tra parser và vocabulary model hỗ trợ. Giảm volume nguồn micro mặc định từ 1,00 xuống 0,65 do log ghi clipping khi nói; đây không phải số đo độ chính xác ASR sau sửa. Muốn hoàn nguyên: wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 1.0. Cần restart cả hai node để nạp alias.
