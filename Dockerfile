# Sử dụng Python bản nhẹ (Slim)
FROM python:3.10-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt FFmpeg và các thư viện hệ thống cần thiết
# (Lệnh này tự động tải bản FFmpeg tương thích với ARM)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào
COPY app.py .

# Mở cổng 8501 (Cổng mặc định của Streamlit)
EXPOSE 8501

# Lệnh chạy ứng dụng
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]