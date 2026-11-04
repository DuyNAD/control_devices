# Quy tắc thao tác không chạm

Bộ quy tắc điều khiển điện thoại và laptop bằng một tay, không chạm màn hình, thông qua camera nhận diện bàn tay. Các mốc thời gian và ngưỡng là giá trị khởi điểm, cần chỉnh lại khi thử thực tế.

## Quy tắc chung

### Nhận diện

- Nhận diện cả 5 ngón tay (cái, trỏ, giữa, áp út, út) là 5 con trỏ riêng biệt. Mỗi ngón có định danh, vị trí và trạng thái riêng; các cử chỉ được xây dựng trên 5 con trỏ này.
- Nhận diện theo khung xương 21 khớp của bàn tay. Trạng thái co, duỗi của ngón được tính từ góc khớp trong không gian 3D.
- Một ngón nhảy vị trí bất thường trong thoáng chốc được coi là đọc nhầm và giữ vị trí cũ, để không ghi nhầm con trỏ của ngón đó.
- Chỉ một tay điều khiển: chọn tay gần màn hình nhất và bỏ qua các tay khác. Tay trông lớn nhất trong khung hình được coi là gần nhất.
- Tay khác phải lớn hơn rõ rệt trong khoảng 300 ms mới được chuyển sang, và không chuyển khi đang thực hiện thao tác. Tay quá nhỏ, tức ở quá xa, thì bị bỏ qua.
- Đầu ngón trỏ điều khiển con trỏ trên màn hình.

### Bật và tắt

- Xòe bàn tay, giữ yên 1 giây để bật.
- Bỏ tay khỏi khung hình 2 giây thì tự tắt.

### Chống nhận nhầm

- Chụm khi khoảng cách hai đầu ngón dưới 25% chiều rộng lòng bàn tay; thả khi trên 40%.
- Kiểu chụm phải ổn định khoảng 150 ms mới được xác nhận, tính theo ngón nào gần ngón cái hơn.
- Khóa con trỏ khoảng 100 ms đầu khi chụm, để động tác chụm không làm con trỏ lệch.
- Làm mượt con trỏ bằng bộ lọc như One Euro.
- Hướng di chuyển rõ trước sẽ được khóa đến khi thả tay.
- Mất dấu tay giữa thao tác thì hủy, không coi là đã thả.

### Sử dụng

- Luôn có phản hồi theo từng trạng thái bằng hình ảnh, âm thanh hoặc rung.
- Chỉ cần cử động tay trong một vùng nhỏ là con trỏ đi hết màn hình.
- Hành động nguy hiểm như xóa, gửi hoặc thanh toán cần thêm một bước xác nhận.
- Có tùy chọn chọn tay thuận.
- Nên đặt điện thoại trên giá đỡ cố định.

## Điện thoại

| # | Thao tác | Cử chỉ | Điều kiện phân biệt | Khi nắm tay để hủy |
|---|---|---|---|---|
| 1 | Lướt | Chụm cái + giữa, kéo theo hướng muốn lướt, rồi buông hai ngón để dừng | Hất nhanh rồi buông thì nội dung trôi tiếp; chụm lại cái + giữa để cố định | Dừng lướt và cố gắng đưa về vị trí ban đầu |
| 2 | Nhấn | Giữ yên ngón trỏ khoảng 400 ms, rồi rời đi | Đã hết vòng 1 và rời đi trước khi hết vòng 2 | Không gửi lệnh nhấn |
| 3 | Nhấn giữ | Giữ yên ngón trỏ khoảng 800 ms | Đã hết vòng 2 | Hủy nhấn giữ |
| 4 | Nhấn giữ và kéo | Sau khi hoàn thành nhấn giữ, di chuyển tay, rồi giữ yên 800 ms để thả | Có di chuyển sau khi hết vòng 2 | Không thả, đối tượng về vị trí cũ |
| 5 | Phóng to, thu nhỏ | Chụm cái + trỏ, đưa tay lên để phóng to, xuống để thu nhỏ | Di chuyển theo chiều dọc | Cố gắng đưa về mức ban đầu |
| 6 | Undo, redo | Chụm cái + trỏ, đưa tay sang trái để chọn undo, sang phải để chọn redo, rồi thả để thực hiện | Di chuyển theo chiều ngang | Không thực hiện lệnh nào |

### Lướt

- Kéo chậm rồi buông: nội dung dừng ngay tại chỗ.
- Hất nhanh rồi buông: nội dung trôi tiếp theo đà.
- Chụm lại khi đang trôi: nội dung được cố định ngay. Nếu vẫn giữ chụm và kéo tiếp, thao tác trở thành một lần lướt mới.

### Nhấn và nhấn giữ

- Mỗi vòng tròn khoảng 400 ms và chỉ chạy khi con trỏ nằm yên trong một vùng nhỏ.
- Lệnh nhấn chỉ được gửi khi ngón trỏ rời đi, để vẫn chuyển tiếp được thành nhấn giữ ở vòng 2.
- Sau mỗi lần nhấn, con trỏ phải rời khỏi vùng đó thì vòng tròn mới được chạy lại.
- Sau khi hết vòng 2, nếu vẫn giữ yên thêm 800 ms thì hệ thống thả tại chỗ.
- Khi đang kéo, giữ yên 800 ms sẽ thả; vòng tròn hiển thị để báo trước.

### Phóng to, thu nhỏ

- Tâm phóng là vị trí con trỏ lúc bắt đầu chụm.
- Có thể giả lập hai điểm chạm đối xứng quanh tâm phóng để ứng dụng nhận đây là thao tác hai ngón bình thường.

### Undo, redo

- Lệnh chỉ chạy sau khi thả tay, và mỗi lần chụm chỉ chạy một lệnh.
- Trong lúc còn chụm, có thể đổi giữa trái và phải nhiều lần. Lệnh chạy theo vị trí của tay lúc thả.
- Màn hình hiện rõ lệnh đang chọn.
- Thả tay ở gần điểm bắt đầu thì không chạy lệnh nào.
- Điện thoại không có lệnh undo dùng chung cho mọi ứng dụng, nên phải xử lý riêng theo từng ứng dụng và một số ứng dụng có thể không hỗ trợ.

### Nắm tay để hủy

- Nắm tay là cử chỉ hủy, áp dụng cho tất cả thao tác trên điện thoại.
- Sau khi hủy, phải mở tay ra thì mới bắt đầu được thao tác mới.
- Lệnh nhấn đã gửi thì không hủy được nữa.
- Sau khi thả tay, chờ khoảng 150 ms rồi mới chạy lệnh, vì khi chuyển từ chụm sang nắm tay, hai ngón có thể tách ra trong giây lát và trông giống như đang thả.
- Hủy lướt và phóng to phải gửi thêm thao tác ngược lại, nên một số ứng dụng có thể không về đúng vị trí hoặc mức ban đầu.

### Ghi chú khi viết code

Chụm cái + giữa rồi buông mà chưa di chuyển thì gửi tín hiệu hủy chạm thay vì "nhấc ngón lên". Nếu không, điện thoại có thể hiểu đó là một lần nhấn và mở nhầm mục. Đây chỉ là xử lý trong code, không phải một cử chỉ: nhấn trên điện thoại vẫn chỉ có một cách là giữ yên ngón trỏ.

## Laptop

| # | Thao tác | Cử chỉ | Điều kiện phân biệt |
|---|---|---|---|
| 1 | Di chuyển con trỏ | Rê tay, không chụm | Đầu ngón trỏ điều khiển con trỏ |
| 2 | Chạm | Chỉ ngón trỏ, gập ngón giữa, áp út và út, giữ yên khoảng 1 giây | Đang chỉ tay và đã hết vòng 1 |
| 3 | Chạm 2 lần | Vẫn chỉ tay, tiếp tục giữ yên đến khoảng 2 giây | Đang chỉ tay và đã hết vòng 2 |
| 4 | Kéo và thả | Chụm cái + trỏ, giữ yên đến khi có báo, di chuyển, rồi thả | Giữ trên 700 ms trước khi di chuyển |
| 5 | Cuộn | Chụm cái + trỏ, kéo chậm lên hoặc xuống, rồi thả | Di chuyển theo chiều dọc |
| 6 | Vuốt | Chụm cái + trỏ, hất nhanh sang trái hoặc phải, rồi thả | Di chuyển nội dung theo chiều ngang |
| 7 | Phóng to, thu nhỏ | Chụm cái + giữa, đưa tay lên để phóng to, xuống để thu nhỏ | Di chuyển theo chiều dọc; tâm phóng là vị trí con trỏ lúc chụm |
| 8 | Chuột phải | Chụm cái + giữa rồi thả nhanh | Giữ dưới 300 ms, gần như không di chuyển |
| 9 | Undo, redo | Chụm cái + giữa, hất sang trái để undo, sang phải để redo, rồi thả | Hất theo chiều ngang; mỗi lần chụm chỉ một lệnh (Ctrl+Z / Ctrl+Y) |

Undo, redo trên laptop dùng cái + giữa vì chụm cái + trỏ rồi hất ngang đã là vuốt, nên khác với điện thoại.

### Lệnh gửi cho Windows

| Thao tác | Lệnh | Âm thanh |
|---|---|---|
| Kéo và thả | Giữ chuột trái từ lúc bắt đầu di chuyển đến lúc thả | Báo khi sẵn sàng kéo và khi thả |
| Cuộn | Con lăn dọc: đưa tay lên thì cuộn lên | Không |
| Vuốt | Con lăn ngang, nội dung đi theo hướng hất tay | Có |
| Phóng to, thu nhỏ | Ctrl + con lăn: đưa tay lên thì phóng to | Không |
| Chuột phải | Chuột phải tại vị trí con trỏ lúc chụm | Có |
| Undo, redo | Ctrl+Z, Ctrl+Y | Có, mỗi lệnh một âm riêng |

- Hủy khi đang kéo, bằng nắm tay hoặc mất dấu tay: gửi Esc rồi thả chuột tại vị trí ban đầu. Khi app dừng giữa lúc kéo cũng vậy, để chuột trái không bị giữ.
- Mỗi lần hủy phát một âm trầm.

### Chạm và chạm 2 lần

- Chỉ tư thế chỉ ngón trỏ mới chạm được: ngón trỏ duỗi, ngón giữa, áp út và út gập, ngón cái ở đâu cũng được. Bung tay, nắm tay và các tư thế ở giữa không tạo lệnh chạm, dù giữ yên bao lâu.
- Tư thế chỉ tay phải ổn định khoảng 300 ms thì vòng tròn mới chạy. Đổi sang tư thế khác là hủy vòng đang chạy.
- Chuyển từ tư thế khác sang chỉ tay thì vòng tròn chạy luôn, không cần di chuyển. Riêng ngay sau khi thả chụm hoặc mở nắm tay thì phải di chuyển trước, hoặc đổi sang tư thế khác hơn 400 ms rồi mới chỉ tay.
- Mỗi vòng tròn khoảng 1 giây và chỉ chạy khi con trỏ nằm yên trong một vùng nhỏ. Thời gian dài để người dùng dừng lại suy nghĩ không bị tính là chọn.
- Hết vòng 1 thì gửi lệnh chạm ngay, tại vị trí đã giữ yên, không cần di chuyển.
- Chạm phát một tiếng bíp, chạm 2 lần phát hai tiếng bíp với tiếng sau cao hơn. Không có tiếng nghĩa là lệnh chưa được gửi.
- Vẫn giữ yên đến hết vòng 2 thì gửi thêm chạm 2 lần. Muốn chỉ chạm một lần thì rời đi trước khi hết vòng 2.
- Sau khi hết vòng 2, và sau khi bật, thả chụm hoặc mở tay khỏi nắm tay, con trỏ phải rời khỏi vùng đó thì vòng tròn mới được chạy lại. Con trỏ tự về theo tay trong khoảng 400 ms sau khi thả chụm không được tính là rời đi, nên dừng tay đọc sau khi cuộn sẽ không tạo click.
- Mất dấu tay, bắt đầu chụm hoặc nắm tay trước khi hết một vòng thì lệnh của vòng đó không được gửi. Lệnh đã gửi thì không hủy được.

### Nắm tay

- Nắm tay là khi cả 4 ngón trỏ, giữa, áp út và út cùng co vào lòng bàn tay trong khoảng 150 ms. Tay được coi là đã mở khi có ít nhất 2 ngón không còn co.
- Nắm tay hủy thao tác đang làm, không coi là đã thả, và giữ yên con trỏ.
- Sau khi nắm tay, phải mở tay ra thì mới bắt đầu được thao tác mới.
