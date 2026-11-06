# Kịch bản nghiệm thu bài 7

Chuẩn bị mô phỏng warehouse, robot undock, AMCL đúng vị trí, Nav2 active; mở node điều hướng và micro theo README. Ghi lại âm thanh nói, transcript, status, robot và đường Nav2 trên màn hình.

| ID | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| M01 | Mở `segmented_map.png` và MarkerArray trong RViz | Có ba vùng A/B/C, đích nằm trên sàn trống |
| V01 | Nói “Đi đến khu vực A” | Transcript đúng, ROUTE A, robot đến A, SUCCEEDED |
| V02 | Nói “Đi đến khu vực B” | Robot đến B, không chạm tường/kệ |
| V03 | Robot ở B; nói “Di chuyển từ khu vực A đến khu vực C” | ARRIVED A trước, sau đó ARRIVED C; không bỏ qua A |
| V04 | Gắn alias `phòng thí nghiệm` cho B, restart node; nói “Đi đến phòng thí nghiệm” | Nhận alias và gửi đích B |
| E01 | Nói “Đi đến khu vực D” | INVALID_COMMAND, không có goal mới |
| E02 | Nói “Đi từ A đến khu vực D” | Từ chối cả câu, robot không bắt đầu đi A |
| E03 | Khi đang đi A → B, nói “dừng lại” | CANCELING rồi STOPPED; không tiếp tục B |
| E04 | Khi đang đi, nói lệnh đi C | BUSY, hành trình cũ tiếp tục, không nhận C |
| E05 | Đầu vào im lặng hoặc confidence <0,65 | Không publish command; log yêu cầu nói lại |
| E06 | Nav2 chưa mở, gửi câu hợp lệ | NOT_READY, không xếp hàng để tự chạy sau |
| E07 | `--goal-timeout 1`, gửi đích xa | Yêu cầu hủy; không gửi các đích tiếp theo |
| E08 | Đặt vật cản trên đường trong Gazebo | Nav2 cập nhật costmap, tránh vật cản hoặc báo thất bại; không va chạm |
| E09 | Sửa bản đồ sau khi phân vùng rồi khởi động node | Từ chối hash cũ, yêu cầu phân vùng lại |
| X01 | “Đi từ phòng A qua phòng C rồi đến phòng B” | Đến A, C, B theo thứ tự |

Với V01–V04, mỗi câu thử ít nhất 5 lần và ghi số lần nhận đúng/tổng, số lần đến đúng/tổng, thời gian hoàn thành. Chưa điền số đo nếu chưa thực sự chạy. Cần ít nhất ba câu khác nhau đi qua micro để nghiệm thu yêu cầu giọng nói; nhập chữ và fake action test không thay thế bước này.

Video đề xuất: mở bản đồ phân vùng → nói ba câu điều hướng và quan sát robot → thử vùng D → thử hủy → thử vật cản. Để thấy thứ tự A → B, giữ màn hình status với hai bản tin ARRIVED tương ứng. Không dùng video test giả lập action làm bằng chứng robot chạy trên Gazebo.
