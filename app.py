import streamlit as st
import edge_tts
import pysrt
import os
import subprocess
import asyncio
import tempfile
import shutil

st.set_page_config(page_title="Home Server TTS (Auto-Sync)", page_icon="⚡")
st.title("⚡ TTS Auto-Sync: Khớp thời gian tuyệt đối")

# --- CẤU HÌNH HỆ THỐNG ---
def get_duration(file_path):
    """Lấy độ dài file âm thanh bằng ffprobe"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", 
        "format=duration", "-of", 
        "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.check_output(cmd).decode().strip()
        return float(result)
    except:
        return 0.0

def generate_silence(duration_sec, output_path):
    """Tạo khoảng lặng"""
    if duration_sec <= 0: return
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", 
        f"anullsrc=r=24000:cl=mono", "-t", str(duration_sec), 
        "-q:a", "2", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def change_speed(input_path, output_path, speed_factor):
    """
    Tăng tốc độ file âm thanh bằng bộ lọc atempo của ffmpeg.
    speed_factor > 1.0 là tăng tốc.
    """
    # FFmpeg atempo filter chỉ hỗ trợ từ 0.5 đến 2.0.
    # Nếu cần nhanh hơn 2.0 (hiếm gặp), ta phải chain filter (nhưng ở đây làm đơn giản trước)
    if speed_factor > 2.0: speed_factor = 2.0 
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter:a", f"atempo={speed_factor}",
        "-vn", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def srt_time_to_seconds(t):
    return (t.hours * 3600) + (t.minutes * 60) + t.seconds + (t.milliseconds / 1000.0)

async def process_tts(srt_content, voice, rate_str, status_text, progress_bar):
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Lưu file SRT
        srt_path = os.path.join(temp_dir, "input.srt")
        with open(srt_path, "wb") as f:
            f.write(srt_content)

        try:
            subs = pysrt.open(srt_path, encoding='utf-8')
        except:
            subs = pysrt.open(srt_path)

        file_list_txt = os.path.join(temp_dir, "mylist.txt")
        final_output_path = os.path.join(temp_dir, "output.mp3")
        concat_list = []
        
        # Con trỏ thời gian hiện tại của file audio tổng
        current_cursor = 0.0
        total_subs = len(subs)

        for index, sub in enumerate(subs):
            # Update UI
            prog = (index / total_subs)
            progress_bar.progress(prog)
            
            text = sub.text_without_tags.strip()
            if not text: continue

            # --- TÍNH TOÁN THỜI GIAN ---
            start_time = srt_time_to_seconds(sub.start)
            end_time = srt_time_to_seconds(sub.end)
            allowed_duration = end_time - start_time # Thời gian cho phép của câu này
            
            # 1. Xử lý Khoảng lặng (Nếu câu này bắt đầu muộn hơn con trỏ hiện tại)
            gap = start_time - current_cursor
            if gap > 0.02: # Chỉ chèn nếu gap đáng kể (>20ms)
                silence_file = os.path.join(temp_dir, f"sil_{index}.mp3")
                generate_silence(gap, silence_file)
                concat_list.append(f"file '{silence_file}'")
                current_cursor += gap
            
            # 2. Tạo Audio gốc (Raw TTS)
            raw_tts_file = os.path.join(temp_dir, f"tts_raw_{index}.mp3")
            # Thêm tham số rate (tốc độ đọc cơ bản)
            communicate = edge_tts.Communicate(text, voice, rate=rate_str)
            await communicate.save(raw_tts_file)
            
            raw_duration = get_duration(raw_tts_file)
            
            # 3. Xử lý "Co dãn" (Auto-Fit)
            final_tts_file = os.path.join(temp_dir, f"tts_final_{index}.mp3")
            
            # Nếu đọc chậm hơn phụ đề -> Tăng tốc
            # Thêm 0.1s vào allowed_duration để tránh cắt quá sát gây mất chữ cuối
            if raw_duration > (allowed_duration + 0.1):
                speed_factor = raw_duration / allowed_duration
                # Giới hạn speed tối đa để không bị méo tiếng quá mức (max 1.7x)
                if speed_factor > 1.7: speed_factor = 1.7
                
                status_text.text(f"Câu {index+1}: Dài quá ({raw_duration:.1f}s > {allowed_duration:.1f}s) -> Tua nhanh x{speed_factor:.2f}")
                change_speed(raw_tts_file, final_tts_file, speed_factor)
                
                # Cập nhật lại duration sau khi tua
                actual_duration = get_duration(final_tts_file)
            else:
                # Nếu vừa hoặc ngắn hơn -> Giữ nguyên
                shutil.move(raw_tts_file, final_tts_file)
                actual_duration = raw_duration

            concat_list.append(f"file '{final_tts_file}'")
            current_cursor += actual_duration

        # --- GỘP FILE ---
        with open(file_list_txt, "w", encoding="utf-8") as f:
            for line in concat_list:
                f.write(line.replace("\\", "/") + "\n")

        status_text.text("Đang render file cuối cùng...")
        cmd_merge = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", file_list_txt, 
            "-c:a", "libmp3lame", "-q:a", "2",
            final_output_path
        ]
        subprocess.run(cmd_merge)

        with open(final_output_path, "rb") as f:
            return f.read()

# --- GIAO DIỆN NGƯỜI DÙNG ---
uploaded_file = st.file_uploader("Upload file .SRT", type=['srt'])

col1, col2 = st.columns(2)
with col1:
    voice_option = st.selectbox("Giọng đọc:", 
                                ["vi-VN-HoaiMyNeural (Nữ)", "vi-VN-NamMinhNeural (Nam)"])
with col2:
    # Cho phép chỉnh tốc độ đọc cơ bản
    base_rate = st.slider("Tốc độ đọc cơ bản:", -50, 50, 0, format="%d%%")

# Format rate string cho Edge TTS (ví dụ: "+10%")
rate_str = f"{base_rate:+d}%"
voice_code = voice_option.split(" ")[0]

if st.button("🚀 BẮT ĐẦU XỬ LÝ"):
    if uploaded_file:
        status_text = st.empty()
        progress_bar = st.progress(0)
        try:
            mp3_data = asyncio.run(process_tts(uploaded_file.getvalue(), voice_code, rate_str, status_text, progress_bar))
            progress_bar.progress(100)
            status_text.success("✅ Đã xử lý xong! File đã được khớp timeline.")
            st.download_button("📥 Tải Audio Đã Sync", mp3_data, file_name="synced_output.mp3", mime="audio/mp3")
        except Exception as e:
            st.error(f"Lỗi: {e}")
    else:
        st.warning("Vui lòng upload file SRT trước!")
