import streamlit as st
import edge_tts
import pysrt
import os
import subprocess
import asyncio
import tempfile

st.set_page_config(page_title="Home Server TTS", page_icon="🏠")
st.title("🏠 Home Server: SRT to Audio (Unlimited)")

# --- CẤU HÌNH LINUX (DOCKER) ---
# Không cần đường dẫn file .exe, gọi trực tiếp lệnh hệ thống
def get_duration(file_path):
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
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", 
        f"anullsrc=r=24000:cl=mono", "-t", str(duration_sec), 
        "-q:a", "2", output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def process_tts(srt_content, voice, status_text, progress_bar):
    with tempfile.TemporaryDirectory() as temp_dir:
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
        current_cursor = 0.0
        total_subs = len(subs)

        for index, sub in enumerate(subs):
            prog = (index / total_subs)
            progress_bar.progress(prog)
            status_text.text(f"Đang xử lý câu {index+1}/{total_subs}...")

            text = sub.text_without_tags.strip()
            if not text: continue

            target_start = (sub.start.hours * 3600) + (sub.start.minutes * 60) + sub.start.seconds + (sub.start.milliseconds / 1000.0)
            
            gap = target_start - current_cursor
            if gap > 0.05:
                silence_file = os.path.join(temp_dir, f"sil_{index}.mp3")
                generate_silence(gap, silence_file)
                concat_list.append(f"file '{silence_file}'")
                current_cursor += gap
            
            tts_file = os.path.join(temp_dir, f"tts_{index}.mp3")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tts_file)
            
            duration = get_duration(tts_file)
            concat_list.append(f"file '{tts_file}'")
            current_cursor += duration

        with open(file_list_txt, "w", encoding="utf-8") as f:
            for line in concat_list:
                f.write(line.replace("\\", "/") + "\n")

        status_text.text("Đang gộp file (Finalizing)...")
        cmd_merge = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", file_list_txt, 
            "-c:a", "libmp3lame", "-q:a", "2",
            final_output_path
        ]
        subprocess.run(cmd_merge)

        with open(final_output_path, "rb") as f:
            return f.read()

# --- GIAO DIỆN ---
uploaded_file = st.file_uploader("Upload file .SRT", type=['srt'])
voice_option = st.selectbox("Chọn giọng đọc:", 
                            ["vi-VN-HoaiMyNeural (Nữ)", "vi-VN-NamMinhNeural (Nam)"])
voice_code = voice_option.split(" ")[0]

if st.button("🚀 BẮT ĐẦU CHUYỂN ĐỔI"):
    if uploaded_file:
        status_text = st.empty()
        progress_bar = st.progress(0)
        try:
            mp3_data = asyncio.run(process_tts(uploaded_file.getvalue(), voice_code, status_text, progress_bar))
            progress_bar.progress(100)
            status_text.success("✅ Đã xong!")
            st.download_button("📥 Tải File MP3", mp3_data, file_name="output.mp3", mime="audio/mp3")
        except Exception as e:
            st.error(f"Lỗi: {e}")